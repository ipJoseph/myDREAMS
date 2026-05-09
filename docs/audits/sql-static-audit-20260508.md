# myDREAMS — Production Readiness Audit

**Date:** 2026-05-08 → 2026-05-09
**Owner:** Joseph Williams
**Author:** Claude (autonomous engineering session, post-incident)
**Scope:** Application-layer SQL compatibility, template/handler consistency, and runtime route stability after the 2026-04-20 PostgreSQL migration.

---

## Executive Summary

Following a string of customer-facing 5xx errors traced to incomplete SQLite→PostgreSQL migration patterns, we built and deployed a three-layer audit pipeline:

1. **Static SQL analyzer** (pglast / Postgres' own parser) over every Python `execute()` call
2. **Jinja template field analyzer** that diffs `render_template(..., **kwargs)` against template variable references
3. **Runtime smoke crawler** over every `app.url_map` GET route with real production IDs

**Result of the audit + fixes performed in this session:**

| Layer | Findings before | Findings after | Status |
|---|---|---|---|
| Static SQL syntax (Postgres-rejecting) | **17 unique blockers** | **1** (legacy SQLite-only script, not user-facing) | ✅ |
| Template field consistency | **46 missing kwargs** | **0** | ✅ |
| Runtime route 5xx (75 routes crawled) | **8** | **0** | ✅ |

The audit tooling now lives in `scripts/audit/` and can be run on demand or wired to CI. The fixes have been deployed to production through normal git push → systemctl restart cycles.

---

## What was broken

The 2026-04-20 PostgreSQL migration was complete at the **data plane** (cron sync engines, `pg_adapter`) but incomplete at the **application plane**. Application code retained five categories of SQLite-only patterns that worked under SQLite's permissive mode but Postgres rejects:

| Pattern | Example | Postgres behavior | Count fixed |
|---|---|---|---|
| `INSERT OR IGNORE` | upsert in dashboard, automation rules | Syntax error | 8 |
| `julianday()`, `date('now', ...)`, `datetime('now', ...)` | DOM calculation, "today's events" filters | Function does not exist | 8 |
| `rowid` | display order renumbering in package_properties | Column does not exist | 4 |
| `LIKE 'foo%'` in psycopg2-bound SQL | gallery filter | `%` interpreted as format directive | 1 |
| GROUP BY with non-aggregate selected columns | dashboard list views, contact pages | GroupingError | 4 |
| HAVING using SELECT aliases | Mission Control overnight narrative | UndefinedColumn | 1 |
| Double-quoted string literal | `"9999-12-31"` ORDER BY sentinel | Treated as identifier → UndefinedColumn | 2 (5 routes affected) |
| `sqlite3.connect()` against the orphan `data/dreams.db` | buyer_report, tour_schedule, brochure_generator | Reads stale data, never sees Postgres updates | 6 functions |
| Two-arg `round(double, int)` | data-quality dashboard | Function overload doesn't exist; needs `::numeric` cast | 1 |

In addition, two **non-SQL** classes of bug surfaced during the audit:

- **Render-template kwargs out of sync with templates.** Two `route_planner.html` callers were missing `standalone`, `pre_selected_ids`, `saved_route_data`, `showing_id`, `showing_name`. Default Jinja silently renders these as empty strings; in this codebase several of those paths produce broken JS. Fixed.
- **Template field names lagging behind SQL refactors.** `photo_status.html` referenced `source.primary_photos` and `source.pending` after the SQL had been renamed to `primary_local` and `pending_status`. Caught by the runtime crawler.

---

## Methodology

### Why pglast (libpg_query)

`pglast` is the Python binding for `libpg_query` — Postgres' own server-side parser, repackaged as a standalone library. **If pglast accepts SQL, Postgres will too.** Used in production by pganalyze, sqlfluff (Postgres dialect), and others. Current version 7.13 (March 2026) supports Python 3.13.

The alternatives we considered and rejected:

- **regex-only grep** (what `audit/scan_sqlite_isms.sh` did): catches known patterns, misses everything else. Misses GROUP BY semantics entirely.
- **sqlfluff**: dialect-aware linting but slower and less accurate for our use case (extracting + validating embedded SQL).
- **Bandit + Semgrep**: focused on security, not syntactic compatibility.
- **pgsanity**: legacy project, builds on the same libpg_query but unmaintained vs pglast.

### Static SQL analyzer (`scripts/audit/sql_static_audit.py`)

```
walk apps/, src/core/, scripts/  (excluding intentionally-SQLite paths)
  for each Python file:
    parse with ast
    for each `*.execute(<sql>, ...)` call:
      extract the SQL string (literal, f-string, str+str concat)
      run regex pattern check for SQLite-only constructs
      if pure literal:
        normalize ? -> $1, $2, ...
        run pglast.parse_sql()
        on accept: walk AST for GROUP BY / HAVING semantic violations
        on reject: report Postgres syntax error
      mark as "advisory" (not blocker) when the call lives in a function
      that early-returns under is_postgres() — these are SQLite-only by design
```

Output: `docs/audits/sql-static-audit.json` with finding-level detail.

### Template field analyzer (`scripts/audit/template_field_audit.py`)

For each `render_template('foo.html', **kwargs)` call, parse the Jinja template AST and walk for top-level variable references. Diff against the kwargs the route passes. Anything in template but not in kwargs (and not a Jinja built-in or Flask context-processor variable) is flagged.

Notable engineering: the standard `jinja2.meta.find_undeclared_variables` indirectly invokes the compiler in newer Jinja2 versions, which validates filter existence and dies on custom filters like `eastern_time`. We bypassed by walking the AST manually with `nodes.iter_child_nodes()`.

### Runtime smoke crawler (`scripts/audit/route_smoke_crawler.py`)

Imports the dashboard Flask app, enumerates `app.url_map.iter_rules()`, and hits every GET route with admin Basic Auth using known-real PRD IDs (one collection, one contact, one listing, one share token). Records HTTP status, elapsed time, body excerpt for 5xx responses.

This catches what static analysis can't:

- Schema drift: column referenced doesn't exist at execution time
- Logic bugs: right syntax, wrong runtime path
- Empty-result-set edge cases (template can't handle a None field)
- The "I refactored the SQL, forgot to update the template" class of bug

---

## Findings & fixes

### Static SQL audit — final state

```
Scanned 126 Python files
Total findings: 76

CODE                             SEV        COUNT
sql_dynamic_unresolvable         advisory   68    (non-literal SQL — manual review needed)
sqlite_autoincrement             blocker    4     (3 are gated by is_postgres() return; 1 real)
pg_syntax                        blocker    4     (same as above — same locations, dual-flag)
```

**Real remaining blockers: 1** (`scripts/parse_tmo_reports.py:276` — a legacy SQLite-only TMO ingestion script flagged in CLAUDE.md as still-pending migration. Not user-facing.)

**Resolved blockers (17 unique locations):**

| File | Line | Pattern | Fix |
|---|---|---|---|
| `apps/automation/rules/activity_burst.py` | 29 | `datetime('now', '-1 day')` | `NOW() - INTERVAL '1 day'` |
| `apps/automation/rules/new_lead.py` | 29 | `datetime('now', ? \|\| ' hours')` | `NOW() - (? \|\| ' hours')::interval` |
| `apps/automation/smart_collections.py` | 348, 464 | `INSERT OR IGNORE` | `INSERT INTO` (UUID PK so OR IGNORE was a no-op) |
| `apps/buyer-workflow/app.py` | 190 | `date("now")` | `CURRENT_DATE` |
| `apps/buyer-workflow/monitor_properties.py` | 246 | `julianday('now') - julianday(list_date)` | `(CURRENT_DATE - list_date::date)` |
| `apps/mlsgrid/reconciliation.py` | 245 | `date('now', '-30 days')` | `CURRENT_DATE - INTERVAL '30 days'` |
| `src/core/database.py` | 1020 | `INSERT OR IGNORE INTO system_settings` | `INSERT INTO ... ON CONFLICT (key) DO NOTHING` |
| `src/core/database.py` | 2061 | `INSERT OR IGNORE INTO lead_activities` | `INSERT INTO` |
| `src/core/database.py` | 3635 | `INSERT OR IGNORE INTO pursuit_properties` | `INSERT INTO ... ON CONFLICT (id) DO NOTHING` |
| `src/core/database.py` | 4730, 4795 | `COALESCE(due_date, "9999-12-31")` | single-quoted (was being read as a column name) |
| `src/core/database.py` | 7011, 7069, 7074 | `DATE('now', 'weekday 1', '-7 days')` | `date_trunc('week', CURRENT_DATE)` arithmetic |
| `apps/property-dashboard/app.py` | 3729 | smart-collections GROUP BY pp.id only | added u.id, l.id, etc. |
| `apps/property-dashboard/app.py` | 7752 | `ROUND(AVG(...), 1)` on double precision | cast to `::numeric` |
| `apps/property-dashboard/app.py` | 7795 | `DATE(created_at)` on listings | `DATE(captured_at::timestamp)` |

### Template field audit — final state

```
Templates referenced from render_template: 45
Findings: 0
```

**Resolved (2 unique routes):**

| Route | Template | Missing kwargs | Fix |
|---|---|---|---|
| `/buyer-collections/<id>/route-planner` (line 2812) | `route_planner.html` | `standalone` | added `standalone=False` |
| `/tour-planner` (line 3318) | `route_planner.html` | `pre_selected_ids`, `saved_route_data`, `showing_id`, `showing_name` | added all four |

### Runtime smoke crawl — final state

```
Routes total: 81, crawled: 75, skipped: 6 (destructive POST routes)
  2xx: 67   3xx: 3   4xx: 5   5xx: 0
Findings: 0
```

The 5 4xx responses are 404s where our smoke-test path-parameter substitutions don't match real records (e.g., `/expenses/1` when no report id 1 exists) — not bugs, just smoke-crawl coverage gaps. The 6 skipped routes are destructive POST endpoints (delete-collection, etc.) that we deliberately don't crawl.

**Resolved 5xx routes (8):**

| Route | Root cause |
|---|---|
| `/smart-collections` | GROUP BY pp.id only; needed l.id/l.first_name/l.last_name |
| `/contacts/<id>` | `"9999-12-31"` double-quoted ORDER BY sentinel |
| `/actions` | same `"9999-12-31"` double-quote |
| `/api/contacts/<id>/actions` | same |
| `/api/actions/pending` | same |
| `/contacts/<id>/workspace` | same |
| `/data-quality` | `round(double, int)` overload missing in PG; also `created_at` column missing on listings |
| `/system/photo-status` | template field names lagging SQL refactor + slow `find`/`du` over 28k photos timing out the request |

---

## What's NOT covered by this audit

Honest accounting of remaining gaps:

1. **Dynamically-built SQL strings** (68 sites flagged as `sql_dynamic_unresolvable`). The analyzer can't extract SQL constructed at runtime via concatenation or external variables. These need eyeball review. A future iteration could use Bandit's `b608` constant-propagation approach to resolve more of them.

2. **Logic correctness inside successful 200s.** A route can return HTTP 200 with wrong data. The smoke crawl proves "doesn't crash"; it doesn't prove "displays correctly." Next layer would be selectors or snapshot-based UI tests on key flows.

3. **POST endpoints.** The crawler only hits GET routes. POST handlers (create/update/delete) need their own integration tests. Several were exercised manually during the session (Create Collection, Save As, Mark Ready to Send, Add Property, Remove Property) and now work, but there's no automated coverage.

4. **The 1 remaining blocker** (`scripts/parse_tmo_reports.py:276`) is in a legacy SQLite-only TMO ingestion script. It's flagged in CLAUDE.md's "NOT OK" list and predates this audit. Not user-facing. Will be addressed when TMO ingestion is ported off SQLite (separate work item).

5. **Cross-MLS data conflicts** (the 1299 Black Forest case). When the same listing is in two MLSs and they disagree on status, our current dedup tie-breaker is MLS-priority based. Should be augmented with "most-recently-modified wins." Tracked separately for the post-incident assessment.

6. **The orphan `/opt/mydreams/data/dreams.db`** (905 MB on PRD). Still present, still being touched by un-migrated code paths (sync_engine raw `sqlite3.connect`, `download_photos.py`). The user-facing impact has been eliminated by the read-path migrations in this audit (buyer_report, tour_schedule, brochure_generator now read Postgres). The file itself is tomorrow's cleanup. See `MEMORY.md` → `project_pg_migration_incomplete.md`.

---

## Re-running the audit

```bash
cd /home/bigeug/myDREAMS

# Static SQL audit (no DB connection needed)
.venv/bin/python scripts/audit/sql_static_audit.py

# Template field consistency
.venv/bin/python scripts/audit/template_field_audit.py

# Runtime smoke crawl (requires PRD admin creds + import-able dashboard app)
CRAWL_USER=admin CRAWL_PASSWORD=$(grep ^DASHBOARD_PASSWORD /opt/mydreams/.env | cut -d= -f2 | tr -d '"') \
  .venv/bin/python scripts/audit/route_smoke_crawler.py
```

Each writes a JSON report to `docs/audits/`. Output is pure-text and diffable; commit the JSON files alongside changes to track regressions over time.

---

## Recommended next steps

In priority order:

1. **Wire the audit suite to CI** (pre-merge gate). The static + template analyzers are fast (<5s combined) and have zero infra dependencies. Block any PR where `sql_static_audit.py` or `template_field_audit.py` find new blockers.
2. **Resolve the 68 `sql_dynamic_unresolvable` findings** with manual review. Most are likely fine; the few that aren't would otherwise lurk until a user trips them.
3. **Migrate `parse_tmo_reports.py` and the other CLAUDE.md "NOT OK" SQLite-only paths off `sqlite3.connect`.** Then delete `/opt/mydreams/data/dreams.db`.
4. **Backfill POST route smoke tests.** A second pass on `route_smoke_crawler.py` that POSTs to known-safe endpoints with synthetic-but-valid payloads (e.g., create-collection, then delete-collection in a teardown).
5. **Address the cross-MLS dedup tie-breaker.** Augment `DEDUP_CONDITION` in `src/core/listing_service.py` so the row with the freshest `modification_timestamp` wins on ties (the 1299 Black Forest case).

---

## Audit artifacts (for reference)

- `scripts/audit/sql_static_audit.py` — 487 lines
- `scripts/audit/template_field_audit.py` — 251 lines
- `scripts/audit/route_smoke_crawler.py` — 231 lines
- `docs/audits/sql-static-audit.json` — machine-readable static findings
- `docs/audits/template-field-audit.json` — machine-readable template findings
- `docs/audits/route-smoke-crawl.json` — machine-readable crawl results
- This document — `docs/audits/sql-static-audit-20260508.md`

---

## Commits in this audit (chronological)

| Commit | Summary |
|---|---|
| `50feeff` | audit + fixes: SQLite-isms across automation/buyer-workflow/mlsgrid/dashboard |
| `0af1d20` | fix: 8 routes 500 found by smoke crawler |
| `bcae836` | fix: smart-collections template syntax, data-quality column, photo-status timeout |
| `c8adfcc` | perf(photo-status): tighten subdir find/du timeout 6s → 3s |

All deployed to PRD and verified by re-running the smoke crawler.
