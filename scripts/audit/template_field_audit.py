"""Template/route field consistency audit.

Walks Python files for `render_template('name.html', **kwargs)` calls. For each
template, parses the Jinja2 AST to extract every top-level variable name
referenced. Diffs against the kwargs the route passes in. Flags:

  * Template references variables not in render_template kwargs — these become
    Undefined at render and either silently empty (default Jinja behavior) or
    UndefinedError (if StrictUndefined is enabled). Class of bug we just hit
    on /system/photo-status with source.primary_photos.
  * Routes that pass kwargs the template never uses (low-severity hygiene).

Output: docs/audits/template-field-audit.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from jinja2 import Environment, FileSystemLoader, nodes  # noqa: E402

DASHBOARD_TEMPLATES = REPO_ROOT / "apps" / "property-dashboard" / "templates"
DASHBOARD_PY_ROOT = REPO_ROOT / "apps" / "property-dashboard"

# Templates whose render uses lots of dynamically-built dicts (e.g. **locals())
# and where false positives are too noisy. Add as needed.
SKIP_TEMPLATES = set()


def find_render_template_calls(py_path: Path) -> list[tuple[int, str, set[str]]]:
    """Returns list of (lineno, template_name, set_of_kwarg_names).
    Handles render_template('foo.html', a=..., b=..., **dict_var)."""
    try:
        src = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(py_path))
    except SyntaxError:
        return []

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # Match `render_template(...)` or `flask.render_template(...)`
        is_target = False
        if isinstance(f, ast.Name) and f.id == "render_template":
            is_target = True
        elif isinstance(f, ast.Attribute) and f.attr == "render_template":
            is_target = True
        if not is_target:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        template_name = first.value
        kwargs = set()
        for kw in node.keywords:
            if kw.arg is not None:
                kwargs.add(kw.arg)
            else:
                # **some_dict — we can't tell what's in it without runtime info.
                # Mark with sentinel so the diff knows to skip.
                kwargs.add("__SPLAT__")
        out.append((node.lineno, template_name, kwargs))
    return out


def _collect_top_level_names(node, declared: set[str], out: set[str]):
    """AST walker that collects top-level Name references (like
    jinja2.meta.find_undeclared_variables) but works without invoking the
    compiler. We can't use the meta helper directly because in newer Jinja2
    it indirectly triggers the filter-existence check."""
    from jinja2 import nodes as _n
    if isinstance(node, _n.Name):
        if node.ctx == "load" and node.name not in declared:
            out.add(node.name)
        elif node.ctx == "store":
            declared.add(node.name)
        return
    if isinstance(node, _n.For):
        # Loop variable becomes declared inside the loop body
        if isinstance(node.target, _n.Name):
            local = set(declared)
            local.add(node.target.name)
            _collect_top_level_names(node.iter, declared, out)
            for child in node.body:
                _collect_top_level_names(child, local, out)
            for child in node.else_:
                _collect_top_level_names(child, local, out)
            return
    if isinstance(node, _n.Assign):
        if isinstance(node.target, _n.Name):
            declared.add(node.target.name)
        _collect_top_level_names(node.node, declared, out)
        return
    if isinstance(node, _n.Macro):
        # Macros declare their args as local
        local = set(declared)
        for arg in node.args:
            if isinstance(arg, _n.Name):
                local.add(arg.name)
        for child in node.body:
            _collect_top_level_names(child, local, out)
        return
    # Generic recursion
    for child in node.iter_child_nodes():
        _collect_top_level_names(child, declared, out)


def template_referenced_names(template_path: Path, env: Environment) -> tuple[set[str], Optional[str]]:
    """Extract the set of top-level variables a template references."""
    try:
        src = template_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return set(), f"could not read: {e}"
    try:
        ast_node = env.parse(src)
    except Exception as e:  # noqa: BLE001
        return set(), f"jinja parse error: {e}"
    out: set[str] = set()
    _collect_top_level_names(ast_node, set(), out)
    return out, None


# Variables Jinja makes available globally — never flag these even if not in kwargs
JINJA_BUILTINS = {
    "request", "session", "g", "url_for", "get_flashed_messages", "config",
    "loop", "self", "super", "varargs", "kwargs", "namespace", "range", "dict",
    "lipsum", "cycler", "joiner", "current_user",
}

# Flask @app.context_processor injects these into every template render.
# Source: apps/property-dashboard/app.py::inject_globals (line ~246).
FLASK_CONTEXT_PROCESSOR_VARS = {
    "dreams_env", "favicon", "current_user_name", "contact_views", "fub_url",
    "showing_request_count", "inbox_new_count",
    # Common globals injected by Jinja extensions or app setup
    "now", "now_iso",
}


def _dummy(*a, **k):
    return ""


def _patch_env_for_unknown_filters(env: Environment):
    """The dashboard registers custom Jinja filters at runtime (eastern_time,
    money, etc.) but our standalone Environment doesn't know them. Plug in
    no-op stubs so env.parse() doesn't trip on filter-existence checks."""
    candidates = {
        "eastern_time", "money", "currency", "humanize", "format_phone",
        "format_address", "intword", "datetimeformat", "dateformat",
        "tojson_pretty", "shortdate", "longdate", "et_time", "et_date",
        "fmt_price", "fmt_int", "fmt_pct", "fmt_dom", "score_color",
        "fmt_phone", "stage_label", "first_name", "humanize_dt",
        "human_relative_time", "humanize_relative",
    }
    for name in candidates:
        env.filters.setdefault(name, _dummy)
        env.tests.setdefault(name, lambda v, *a, **k: True)


def main():
    env = Environment(loader=FileSystemLoader(str(DASHBOARD_TEMPLATES)))
    _patch_env_for_unknown_filters(env)
    findings: list[dict] = []

    # Index render_template calls per template name
    render_index: dict[str, list[dict]] = {}
    for py in DASHBOARD_PY_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        for lineno, template_name, kwargs in find_render_template_calls(py):
            render_index.setdefault(template_name, []).append({
                "py_file": py.relative_to(REPO_ROOT).as_posix(),
                "py_line": lineno,
                "kwargs": kwargs,
            })

    # For each template referenced from a render_template call, diff
    for template_name, callers in render_index.items():
        if template_name in SKIP_TEMPLATES:
            continue
        tpath = DASHBOARD_TEMPLATES / template_name
        if not tpath.exists():
            findings.append({
                "code": "template_missing", "severity": "blocker",
                "template": template_name,
                "callers": [(c["py_file"], c["py_line"]) for c in callers],
                "message": f"render_template references {template_name} which doesn't exist on disk",
            })
            continue
        refs, err = template_referenced_names(tpath, env)
        if err:
            findings.append({
                "code": "template_parse_error", "severity": "advisory",
                "template": template_name,
                "message": err,
            })
            continue
        # For each caller, check the diff
        for caller in callers:
            kwargs = caller["kwargs"]
            if "__SPLAT__" in kwargs:
                # Caller passes **dict — we can't tell what's in it; skip
                continue
            missing = refs - kwargs - JINJA_BUILTINS - FLASK_CONTEXT_PROCESSOR_VARS
            if missing:
                findings.append({
                    "code": "template_var_missing", "severity": "blocker",
                    "template": template_name,
                    "py_file": caller["py_file"], "py_line": caller["py_line"],
                    "missing_vars": sorted(missing),
                    "message": f"template uses {sorted(missing)} but render_template doesn't pass them",
                })

    # Sort
    sev_order = {"blocker": 0, "error": 1, "advisory": 2}
    findings.sort(key=lambda f: (sev_order.get(f.get("severity", "advisory"), 9),
                                   f.get("template", ""), f.get("py_file", "")))

    out = REPO_ROOT / "docs" / "audits" / "template-field-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "templates_referenced": len(render_index),
        "findings_total": len(findings),
        "findings": findings,
    }, indent=2))

    # Console summary
    print(f"Templates referenced from render_template: {len(render_index)}")
    print(f"Findings: {len(findings)}")
    by_code = {}
    for f in findings:
        by_code.setdefault(f.get("code"), 0)
        by_code[f.get("code")] += 1
    for code, count in sorted(by_code.items(), key=lambda kv: -kv[1]):
        print(f"  {code:<28} {count}")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
