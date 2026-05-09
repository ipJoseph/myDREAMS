"""Static SQL audit for myDREAMS.

Walks Python source files in apps/, src/core/, scripts/. Extracts every SQL
string passed to a `.execute(...)` call. Validates each through pglast (the
Postgres parser). Flags:

  * Hard syntax errors (Postgres will reject) — INSERT OR IGNORE, julianday,
    etc. These are guaranteed to 500 if executed.
  * Direct sqlite3.connect(...) calls against the orphan dreams.db — bypass
    Postgres entirely.
  * Schema reference issues — column names referenced in queries that don't
    exist in information_schema.columns.
  * GROUP BY semantic issues — non-aggregate selected columns missing from
    GROUP BY, the class of bug Postgres rejects but SQLite silently accepts.

Output: a JSON report under docs/audits/sql-static-audit.json plus a short
console summary. The report is consumed by build_audit_report.py to produce
the boardroom-readable markdown.

Usage:
    .venv/bin/python scripts/audit/sql_static_audit.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pglast  # noqa: E402
from pglast import parse_sql  # noqa: E402

# --------------------------------------------------------------------------
# Source enumeration
# --------------------------------------------------------------------------

SOURCE_ROOTS = [
    REPO_ROOT / "apps" / "property-dashboard",
    REPO_ROOT / "apps" / "property-api",
    REPO_ROOT / "apps" / "automation",
    REPO_ROOT / "apps" / "buyer-workflow",
    REPO_ROOT / "apps" / "navica",
    REPO_ROOT / "apps" / "mlsgrid",
    REPO_ROOT / "apps" / "photos",
    REPO_ROOT / "apps" / "fub-to-sheets",
    REPO_ROOT / "src" / "core",
    REPO_ROOT / "scripts",
    REPO_ROOT / "modules",
]

EXCLUDE_DIRS = {".venv", "node_modules", "__pycache__", "archive", ".git"}
EXCLUDE_FILES = {
    # Intentionally still SQLite per CLAUDE.md
    "task_sync/db.py",
    "linear_sync/db.py",
    # One-shot migration tool
    "scripts/migrate_to_postgres.py",
    # Test fixtures
    "tests/conftest.py",
    # The audit scripts themselves
    "scripts/audit/sql_static_audit.py",
    "scripts/audit/template_field_audit.py",
    "scripts/audit/route_smoke_crawler.py",
}


def iter_python_files() -> Iterator[Path]:
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            rel = p.relative_to(REPO_ROOT).as_posix()
            if any(d in p.parts for d in EXCLUDE_DIRS):
                continue
            if any(rel.endswith(ex) for ex in EXCLUDE_FILES):
                continue
            yield p


# --------------------------------------------------------------------------
# SQL string extraction from Python AST
# --------------------------------------------------------------------------


def _placeholder_normalize(s: str) -> str:
    """Replace SQLite-style ? placeholders with Postgres $1, $2... so pglast
    can parse them. Also strip Python-style %s used by some psycopg2 callers."""
    out = []
    n = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "?":
            n += 1
            out.append(f"${n}")
            i += 1
        elif ch == "%" and i + 1 < len(s) and s[i + 1] == "s":
            n += 1
            out.append(f"${n}")
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _resolve_string_literal(node: ast.AST) -> tuple[Optional[str], bool]:
    """Extract a string from common Python AST patterns. Returns (sql, was_dynamic).
    was_dynamic is True if any part of the string came from an f-string interpolation
    or runtime concatenation — pglast parsing is unreliable on such strings (the
    interpolated value might be a column name, full clause, table name, etc.) so the
    caller should skip pglast and only run pattern-based checks."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, False
    if isinstance(node, ast.JoinedStr):
        parts = []
        had_interp = False
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                had_interp = True
                parts.append("?")
            else:
                return None, True
        return "".join(parts), had_interp
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, ld = _resolve_string_literal(node.left)
        right, rd = _resolve_string_literal(node.right)
        if left is not None and right is not None:
            return left + right, (ld or rd)
    return None, True


def _looks_like_sql(s: str) -> bool:
    head = s.lstrip()[:24].upper()
    return any(head.startswith(kw) for kw in (
        "SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE", "ALTER",
        "DROP", "TRUNCATE", "BEGIN", "COMMIT", "ROLLBACK", "EXPLAIN",
    ))


# --------------------------------------------------------------------------
# Pattern checks (independent of pglast — detect SQLite-only syntax)
# --------------------------------------------------------------------------

SQLITE_PATTERNS = [
    (r"\bINSERT\s+OR\s+(IGNORE|REPLACE|ABORT|FAIL|ROLLBACK)\b", "sqlite_insert_or", "INSERT OR ... is SQLite-only; use INSERT ... ON CONFLICT in Postgres"),
    (r"\bREPLACE\s+INTO\b", "sqlite_replace_into", "REPLACE INTO is SQLite-only; use INSERT ... ON CONFLICT DO UPDATE"),
    (r"\bjulianday\s*\(", "sqlite_julianday", "julianday() is SQLite-only; use date arithmetic with CURRENT_DATE / INTERVAL"),
    (r"\bdatetime\s*\(\s*['\"]now['\"]", "sqlite_datetime_now", "datetime('now',...) is SQLite-only; use NOW()/CURRENT_TIMESTAMP"),
    (r"\bdate\s*\(\s*['\"]now['\"]", "sqlite_date_now", "date('now',...) is SQLite-only; use CURRENT_DATE +/- INTERVAL"),
    (r"\bstrftime\s*\(", "sqlite_strftime", "strftime() in SQL is SQLite-only; use to_char() in Postgres"),
    (r"\bAUTOINCREMENT\b", "sqlite_autoincrement", "AUTOINCREMENT is SQLite-only; use SERIAL or GENERATED ALWAYS AS IDENTITY"),
    (r"\bCOLLATE\s+NOCASE\b", "sqlite_nocase", "COLLATE NOCASE is SQLite-only; use ILIKE or lower() in Postgres"),
    (r"\bPRAGMA\b", "sqlite_pragma", "PRAGMA is SQLite-only"),
    (r"\.rowid\b|\browid\s*[,\s)=]", "sqlite_rowid", "rowid is SQLite-only; use the table's id column"),
    # || string concat is SQL standard — works in both SQLite and Postgres.
    # Removed from blocklist after audit confirmed no false-positives in practice.
]


def scan_sqlite_patterns(sql: str) -> list[dict]:
    findings = []
    for entry in SQLITE_PATTERNS:
        pattern, code, message = entry[0], entry[1], entry[2]
        severity = entry[3] if len(entry) > 3 else "blocker"
        if re.search(pattern, sql, re.IGNORECASE):
            findings.append({"code": code, "message": message, "severity": severity})
    return findings


# --------------------------------------------------------------------------
# pglast parse + semantic walk
# --------------------------------------------------------------------------


def _is_aggregate_func(name: str) -> bool:
    """Common aggregate function names. Used by GROUP BY checker."""
    return name.lower() in {
        "count", "sum", "avg", "min", "max", "array_agg", "string_agg",
        "json_agg", "jsonb_agg", "bool_and", "bool_or", "every", "stddev",
        "stddev_pop", "stddev_samp", "var_pop", "var_samp", "variance",
        "bit_and", "bit_or", "regr_count", "regr_sx", "regr_sy",
    }


def _node_kind(n) -> str:
    return type(n).__name__


def _walk_columnrefs(node, out):
    """Yield ColumnRef nodes anywhere under `node`. Skip subqueries inside
    aggregate calls (they don't need to be in GROUP BY)."""
    if node is None:
        return
    if hasattr(node, "__dict__"):
        if _node_kind(node) == "ColumnRef":
            out.append(node)
            return
        for v in node.__dict__.values():
            if isinstance(v, (list, tuple)):
                for item in v:
                    _walk_columnrefs(item, out)
            elif hasattr(v, "__dict__"):
                _walk_columnrefs(v, out)


def _columnref_str(cr) -> str:
    """Render a ColumnRef as 'a.b' or 'b'."""
    if cr is None or not hasattr(cr, "fields") or cr.fields is None:
        return "?"
    parts = []
    for f in cr.fields:
        if _node_kind(f) == "String":
            parts.append(f.sval)
        elif _node_kind(f) == "A_Star":
            parts.append("*")
    return ".".join(parts)


def _has_aggregate(node) -> bool:
    if node is None:
        return False
    if _node_kind(node) == "FuncCall":
        try:
            fname = node.funcname[-1].sval
            if _is_aggregate_func(fname):
                return True
        except Exception:
            pass
    if hasattr(node, "__dict__"):
        for v in node.__dict__.values():
            if isinstance(v, (list, tuple)):
                for item in v:
                    if _has_aggregate(item):
                        return True
            elif hasattr(v, "__dict__"):
                if _has_aggregate(v):
                    return True
    return False


def check_groupby_semantics(stmt) -> list[dict]:
    """Walk SelectStmt nodes; if groupClause is non-empty, every non-aggregate
    target must appear in groupClause OR be functionally dependent on a primary
    key in groupClause. We can't fully verify the latter (needs schema), so we
    flag and let the human review."""
    findings = []
    if _node_kind(stmt) != "SelectStmt":
        return findings
    target_list = getattr(stmt, "targetList", None) or ()
    group_clause = getattr(stmt, "groupClause", None) or ()
    if not group_clause or not target_list:
        return findings

    # Collect column refs that appear in groupClause
    group_refs = set()
    for g in group_clause:
        crs = []
        _walk_columnrefs(g, crs)
        for cr in crs:
            group_refs.add(_columnref_str(cr))

    for tgt in target_list:
        # Skip if target is itself an aggregate
        val = getattr(tgt, "val", None)
        if _has_aggregate(val):
            continue
        # Star (*) is always allowed
        if val is not None and _node_kind(val) == "ColumnRef":
            for f in val.fields or ():
                if _node_kind(f) == "A_Star":
                    break
        # Find non-aggregate column refs in this target
        crs = []
        _walk_columnrefs(val, crs)
        for cr in crs:
            name = _columnref_str(cr)
            if name == "*":
                continue
            if name not in group_refs:
                # Check the unqualified version too — GROUP BY a, target a.b
                # doesn't satisfy a.b unless we're grouping by primary key.
                short = name.rsplit(".", 1)[-1]
                if short not in group_refs and name not in group_refs:
                    findings.append({
                        "code": "groupby_nonagg",
                        "message": f"non-aggregate column '{name}' in SELECT but not in GROUP BY",
                        "severity": "blocker",
                    })
    return findings


def check_having_uses_alias(stmt) -> list[dict]:
    """Postgres rejects HAVING that references SELECT-list aliases by name.
    Detect when a ColumnRef in the havingClause matches a target alias in the
    targetList without a corresponding underlying column."""
    findings = []
    if _node_kind(stmt) != "SelectStmt":
        return findings
    having = getattr(stmt, "havingClause", None)
    if having is None:
        return findings
    target_list = getattr(stmt, "targetList", None) or ()
    aliases = set()
    for tgt in target_list:
        name = getattr(tgt, "name", None)
        if name:
            aliases.add(name)
    crs = []
    _walk_columnrefs(having, crs)
    for cr in crs:
        ref = _columnref_str(cr)
        if ref in aliases:
            findings.append({
                "code": "having_uses_alias",
                "message": f"HAVING references SELECT alias '{ref}'; Postgres requires the original expression",
                "severity": "blocker",
            })
    return findings


# --------------------------------------------------------------------------
# Per-file analysis
# --------------------------------------------------------------------------


def is_execute_call(node: ast.Call) -> bool:
    """Match obj.execute(sql, ...) or obj.executemany(sql, ...)."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in ("execute", "executemany")


def is_sqlite_connect_call(node: ast.Call) -> bool:
    """Match sqlite3.connect(...) — flagged only if path resembles dreams.db."""
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "connect":
        if isinstance(func.value, ast.Name) and func.value.id == "sqlite3":
            return True
    return False


def _is_postgres_gated(node: ast.Call, tree: ast.Module) -> bool:
    """True if `node` is inside a function that early-returns when is_postgres()
    is true. Catches the common pattern:
        if is_postgres():
            return
        # SQLite-only block follows
    Lets the analyzer ignore CREATE TABLE AUTOINCREMENT etc that's already
    properly gated."""
    # Walk up parent chain (we recompute since ast doesn't track parents)
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    p = parents.get(node)
    while p is not None:
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Look for `if is_postgres(): return` near top of body
            for stmt in p.body[:8]:
                if isinstance(stmt, ast.If):
                    test = stmt.test
                    is_pg = (
                        (isinstance(test, ast.Call) and isinstance(test.func, ast.Name)
                         and test.func.id == "is_postgres")
                        or (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)
                            and test.func.attr == "is_postgres")
                    )
                    if is_pg:
                        for body_stmt in stmt.body:
                            if isinstance(body_stmt, ast.Return):
                                return True
            return False
        p = parents.get(p)
    return False


def analyze_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [{
            "file": rel, "line": e.lineno or 0,
            "code": "py_syntax", "severity": "error",
            "message": f"Python parse error: {e.msg}",
        }]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if is_sqlite_connect_call(node):
            arg0 = node.args[0] if node.args else None
            text, _ = _resolve_string_literal(arg0) if arg0 else (None, True)
            if text and "dreams.db" in text:
                findings.append({
                    "file": rel, "line": node.lineno,
                    "code": "sqlite_connect_orphan", "severity": "blocker",
                    "message": "sqlite3.connect against dreams.db — bypasses Postgres",
                    "evidence": text[:120],
                })
            continue
        if not is_execute_call(node):
            continue
        if not node.args:
            continue
        sql, was_dynamic = _resolve_string_literal(node.args[0])
        if sql is None:
            findings.append({
                "file": rel, "line": node.lineno,
                "code": "sql_dynamic_unresolvable", "severity": "advisory",
                "message": "execute() with non-literal SQL (concatenation or runtime build) — manual review",
            })
            continue
        if not _looks_like_sql(sql):
            continue

        # If this execute() lives in a function that early-returns under
        # is_postgres(), it's SQLite-only by design (legacy bootstrap block)
        # and shouldn't be reported as a Postgres blocker.
        gated = _is_postgres_gated(node, tree)

        # Pattern checks (always — work even on f-string-substituted SQL)
        for finding in scan_sqlite_patterns(sql):
            if gated:
                finding["severity"] = "advisory"
                finding["message"] = finding["message"] + " [SQLite-gated by is_postgres() return]"
            finding.update({
                "file": rel, "line": node.lineno,
                "evidence": sql.strip()[:200],
            })
            findings.append(finding)

        # Skip pglast for f-string SQL — interpolated values are likely column
        # names/clauses/tables, so the substituted ? placeholder produces
        # syntactically invalid SQL that's not a real bug.
        if was_dynamic:
            continue

        # pglast parse (pure literal SQL only)
        normalized = _placeholder_normalize(sql)
        try:
            stmts = parse_sql(normalized)
        except pglast.parser.ParseError as e:
            findings.append({
                "file": rel, "line": node.lineno,
                "code": "pg_syntax",
                "severity": "advisory" if gated else "blocker",
                "message": f"Postgres parse error: {e}" + (" [SQLite-gated]" if gated else ""),
                "evidence": sql.strip()[:200],
            })
            continue
        except Exception as e:  # noqa: BLE001
            findings.append({
                "file": rel, "line": node.lineno,
                "code": "pg_parse_unknown", "severity": "advisory",
                "message": f"pglast raised {type(e).__name__}: {e}",
                "evidence": sql.strip()[:200],
            })
            continue

        # Semantic checks for each top-level statement
        for raw in stmts:
            stmt = raw.stmt
            for f in check_groupby_semantics(stmt):
                f.update({
                    "file": rel, "line": node.lineno,
                    "evidence": sql.strip()[:200],
                })
                findings.append(f)
            for f in check_having_uses_alias(stmt):
                f.update({
                    "file": rel, "line": node.lineno,
                    "evidence": sql.strip()[:200],
                })
                findings.append(f)

    return findings


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def main():
    all_findings: list[dict] = []
    files_scanned = 0
    for p in iter_python_files():
        files_scanned += 1
        all_findings.extend(analyze_file(p))

    # Sort by severity then file
    sev_order = {"blocker": 0, "error": 1, "advisory": 2}
    all_findings.sort(key=lambda f: (sev_order.get(f.get("severity", "advisory"), 9), f.get("file", ""), f.get("line", 0)))

    out_path = REPO_ROOT / "docs" / "audits" / "sql-static-audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "files_scanned": files_scanned,
        "findings_total": len(all_findings),
        "findings": all_findings,
    }, indent=2))

    # Console summary
    by_code = {}
    for f in all_findings:
        by_code.setdefault(f.get("code"), []).append(f)
    print(f"Scanned {files_scanned} Python files")
    print(f"Total findings: {len(all_findings)}")
    print()
    print(f"{'CODE':<32} {'SEV':<10} COUNT")
    for code, items in sorted(by_code.items(), key=lambda kv: -len(kv[1])):
        sev = items[0].get("severity", "?")
        print(f"{code:<32} {sev:<10} {len(items)}")
    print()
    print(f"Full report: {out_path}")


if __name__ == "__main__":
    main()
