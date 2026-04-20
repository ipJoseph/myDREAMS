# myDREAMS Master To-Do List

*Exhaustive prioritized task list. Check off as completed.*

Last updated: April 20, 2026 (post-audit)

---

## P0: Pre-Launch Hardening (from 2026-04-20 Audit)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | **Replace str(e) in HTTP responses** | Pending | 13 instances in dashboard leaking internal errors to users |
| 2 | **Remove time.sleep() from route handlers** | Pending | 3 instances blocking all concurrent requests (public_writes.py, user.py) |
| 3 | **Add Cache-Control headers to photo endpoint** | Pending | Photos are immutable once downloaded; no caching headers currently |
| 4 | **Fix 3 files still using sqlite3.connect()** | Pending | buyer-workflow/app.py, automation/smart_collections.py, vendor-directory/app.py |
| 5 | **Remove __pycache__ from git** | Pending | 21 dirs, 84 .pyc files committed; add to .gitignore |
| 6 | **Archive orphaned scripts and dead apps** | Pending | ~15 orphaned scripts, vendor-directory, buyer-workflow, fub-to-sheets backup |
| 7 | **Pin next-auth to stable version** | Pending | Currently on 5.0.0-beta.30 |

---

## PRIORITY 1: Launch Blockers

| # | Task | Status | Notes |
|---|------|--------|-------|
| 8 | **Photo architecture efficiency review** | Partial | Hot-path per-file stat replaced with 60s dir-scan cache. Race conditions + sold-photo cleanup deferred |
| 9 | **Supabase Auth email confirmation test** | Blocked | Supabase returns 500 "Error sending confirmation email"; SMTP creds need rotation |
| 10 | **Google OAuth end-to-end test** | Partial | Provider configured, Supabase→Google redirect works; needs manual browser click-through |
| 11 | **Favicon: distinct icons per app** | Done | Dashboard uses mountain silhouette; public-site keeps house. Env-aware dev/prd already wired |
| 12 | **Remove frozen-data pivot banner** | Done | Removed 4 template includes + deleted partial |
| 13 | **FUB daily sync test** | Done | Ported 3 SQLite-only code paths to PostgreSQL; sync runs cleanly |
| 14 | **Add GitHub Actions CI** | Done | pytest + ruff + next build on push; `.github/workflows/ci.yml` |

---

## PRIORITY 2: Structural Refactor (from Audit)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 15 | **Split property-dashboard/app.py into blueprints** | Pending | 8,555 lines, 153 routes in one file |
| 16 | **Decompose DREAMSDatabase into service classes** | Pending | 7,318 lines, 163 methods (God class); split into Contact/Property/Activity/Pursuit/Analytics services |
| 17 | **Standardize all get_db() calls** | Pending | 10 different implementations; 3 still hardcode sqlite3 |
| 18 | **Add Alembic for database migrations** | Pending | Currently ad-hoc ALTER TABLE; need version-controlled schema |
| 19 | **Add Sentry for error monitoring** | Pending | Replace str(e) responses with tracked error reports |
| 20 | **Move route-level raw SQL into service methods** | Pending | admin.py, public.py, public_writes.py bypass DREAMSDatabase |
| 21 | **Remove SQLite compatibility layer** | Pending | pg_adapter was a bridge; divorce SQLite fully, use native PostgreSQL |

---

## PRIORITY 3: Post-Launch / Medium

| # | Task | Status | Notes |
|---|------|--------|-------|
| 22 | **Mobile-responsive dashboard** | Pending | Desktop only |
| 23 | **PostGIS setup** | Pending | Radius/polygon search |
| 24 | **JSONB feature search** | Pending | Structured feature queries |
| 25 | **Smart List surge smoothing** | Pending | Eugy has ideas |
| 26 | **Showings & Collections data recovery** | Pending | Discovered 2026-03-22 |
| 27 | **Cloudflare CDN for photos** | Pending | 166 GB on local disk; needs CDN before scale |
| 28 | **Celery + Redis for background tasks** | Pending | Replace time.sleep() and thread-based patterns |
| 29 | **Expand test coverage to 50%+** | Pending | Currently 32 tests / 270 routes (12%) |

---

## PRIORITY 4: Polish & UX

| # | Task | Status | Notes |
|---|------|--------|-------|
| 30 | **Dark mode support** | Pending | Eye comfort option |
| 31 | **Keyboard shortcuts** | Pending | Power user navigation |
| 32 | **Bulk actions interface** | Pending | Multi-select operations |
| 33 | **Ascending/descending sort on Collections** | Pending | Toggle sort direction |
| 34 | **Configurable address abbreviations** | Pending | Route planner street suffix mappings |

---

## PRIORITY 5: Future Features

| # | Task | Status | Notes |
|---|------|--------|-------|
| 35 | **Branded property flyers** | Pending | Marketing materials |
| 36 | **Comparative market analysis** | Pending | CMA generation |
| 37 | **Client presentation decks** | Pending | Slide generation |
| 38 | **Pydantic request validation** | Pending | Type-safe parsing, auto-docs |
| 39 | **OpenAPI/Swagger documentation** | Pending | Flask-RESTX or Flasgger |

---

## Completed Items

| Task | Completed | Notes |
|------|-----------|-------|
| Score decay for inactive leads | Jan 2026 | 6-tier decay multipliers |
| Click-to-Call FUB deep links | Jan 2026 | Phone numbers link to FUB |
| Unified Contact Workspace | Jan 2026 | Central hub with tabs |
| Workflow Pipeline (Kanban View) | Jan 2026 | Drag-drop with 10 stages |
| Weighted buyer-property matching | Jan 2026 | 4-factor scoring |
| Weekly market summary report | Jan 2026 | Monday 6:30 AM email |
| Monthly lead activity report | Jan 2026 | 1st of month email |
| New listing alerts | Jan 2026 | Daily 8:00 AM buyer digest |
| PDF property packages | Jan 2026 | WeasyPrint generation |
| Historical price charts | Jan 2026 | Chart.js on property detail |
| Admin settings page | Jan 2026 | Toggle switches for alerts/reports |
| Collections bridge (Pursuits rename) | Feb 2026 | Renamed across dashboard |
| Buyer activity tracking | Feb 2026 | buyer_activity table |
| Showing request feature | Feb 2026 | Request/cancel API, agent email |
| Elevation enrichment (USGS) | Feb 2026 | All listings enriched |
| Flood zone enrichment (FEMA) | Feb 2026 | flood_zone + flood_factor |
| View potential enrichment | Feb 2026 | 8-point terrain sampling |
| Historical MLS import | Feb 2026 | 54,329 total listings |
| PostgreSQL migration | Mar 2026 | SQLite replaced in PRD + DEV |
| PhotoManager module | Mar 2026 | Unified photo management |
| Photo gallery fill | Mar 2026 | 28,980 photo-ready on PRD |
| Supabase Auth integration | Mar 2026 | Replaced NextAuth + Flask dual-auth |
| Contact form + lead capture | Mar 2026 | public_writes.py with dedup |
| Voice search + NLP parser | Mar 2026 | Web Speech API |
| Search filters redesign | Mar 2026 | County/city dropdowns, stats row |
| DEV/PRD PostgreSQL parity | Apr 2026 | Both on PostgreSQL, SQLite archived |
| FUB independence | Apr 2026 | Own API key, own pipeline |
| FUB DEV tagging | Apr 2026 | DEV_TEST tag, source "localhost" |
| Full codebase audit | Apr 2026 | See docs/audits/20260420.Audit.myDREAMS.md |

---

*This file is checked into the repo and will persist across Claude sessions.*
