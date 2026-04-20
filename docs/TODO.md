# myDREAMS Master To-Do List

*Exhaustive prioritized task list. Check off as completed.*

Last updated: April 19, 2026

---

## PRIORITY 1: Launch Blockers

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | **Photo architecture efficiency review** | Pending | localize_photo does per-file stat on every page view (should cache or trust DB); multiple writers with race conditions; no cleanup for sold/expired photos |
| 2 | **Supabase Auth email confirmation test** | Pending | SMTP configured but delivery untested after rate limit fix |
| 3 | **Google OAuth end-to-end test** | Pending | Configured in Supabase + client ID set, needs real login test |
| 4 | **Favicon: distinct icons per app** | Pending | PRD needs blue icon; public site vs dashboard should differ |
| 5 | **Remove frozen-data pivot banner** | Pending | Dashboard still shows JTH pivot banner |
| 6 | **FUB daily sync test** | Pending | Untested since PostgreSQL migration; fires at 10 UTC daily |

---

## PRIORITY 2: Post-Launch / Medium Priority

| # | Task | Status | Notes |
|---|------|--------|-------|
| 7 | **Mobile-responsive dashboard** | Pending | Dashboard works on desktop only |
| 8 | **PostGIS setup** | Pending | Radius search, polygon search; approved in plan |
| 9 | **JSONB feature search** | Pending | Structured feature queries on listing attributes |
| 10 | **Standardize error handling** | Pending | Inconsistent patterns across apps; str(e) leakage in 40+ responses |
| 11 | **Smart List surge smoothing** | Pending | 297/334 FUB contacts unbucketed; 150-contact Unresponsive spikes after bulk action plans. Eugy has ideas. |
| 12 | **Remove SQLite retry/yield patches** | Pending | No longer needed on PostgreSQL; dead code in sync engine and public_writes |
| 13 | **Archive old photo download scripts** | Pending | `apps/mlsgrid/download_photos.py`, `download_gallery.py`, `apps/navica/download_photos.py` replaced by PhotoManager |
| 14 | **Review unused database methods** | Pending | Some aggregation methods may be orphaned after PostgreSQL migration |
| 15 | **Showings & Collections data recovery** | Pending | Kevin Purucker's collection and all showings data gone from DEV and PRD; discovered 2026-03-22 |

---

## PRIORITY 3: Polish & UX

| # | Task | Status | Notes |
|---|------|--------|-------|
| 16 | **Dark mode support** | Pending | Eye comfort option |
| 17 | **Keyboard shortcuts** | Pending | Power user navigation |
| 18 | **Bulk actions interface** | Pending | Multi-select operations |
| 19 | **Ascending/descending sort on Collections** | Pending | Toggle for sort direction on Active Collections page |
| 20 | **Configurable address abbreviations** | Pending | Custom street suffix mappings for route planner (currently hardcoded in normalizeAddr()) |

---

## PRIORITY 4: Future Features

| # | Task | Status | Notes |
|---|------|--------|-------|
| 21 | **Branded property flyers** | Pending | Marketing materials |
| 22 | **Comparative market analysis** | Pending | CMA generation |
| 23 | **Client presentation decks** | Pending | Slide generation |
| 24 | **Add test suite** | Pending | `/tests/` has conftest + a few integration tests; needs broader coverage |
| 25 | **Settings page test plan** | Pending | Env vars, DB settings, secret masking, collapsible sections, save flow |

---

## Completed Items

| Task | Completed | Notes |
|------|-----------|-------|
| Score decay for inactive leads | Jan 2026 | 6-tier decay multipliers |
| Click-to-Call FUB deep links | Jan 2026 | Phone numbers link to FUB when fub_id available |
| Remove unused httpx import | Jan 2026 | Cleaned up dead import |
| ENABLE_STAGE_SYNC review | Jan 2026 | Feature implemented in fub-core, disabled by default |
| Unified Contact Workspace | Jan 2026 | Central hub with tabs: Info, Requirements, Activity, Packages, Showings, Matches |
| Intake-Driven Property Search | Jan 2026 | Search using intake criteria, multi-select for package creation |
| Package Management in Workspace | Jan 2026 | Create packages from search, generate client links |
| Workflow Pipeline (Kanban View) | Jan 2026 | Drag-drop Kanban board with 10 stages |
| Weighted buyer-property matching | Jan 2026 | 4-factor scoring: Price(30%), Location(25%), Size(25%), Recency(20%) |
| Match score breakdown visualization | Jan 2026 | Visual bars showing contribution of each factor |
| Lead requirements extraction | Jan 2026 | Regex parsing for price, beds, baths, acreage, counties, cities |
| Stated vs behavioral preferences | Jan 2026 | Blends stated (40%) + behavioral (60%) for matching |
| Email deduplication | Jan 2026 | Contacts deduped by email |
| New contacts in daily email | Jan 2026 | Last 3 days with Today/Yesterday/N days ago |
| Action Management System | Jan 2026 | Contact actions, My Actions page, Scoring History |
| Enhanced Contacts Dashboard | Jan 2026 | Action Queue, Score Analysis, Insights, Trends tabs |
| Database Normalization | Jan 2026 | contact_daily_activity, contact_actions, scoring_runs tables |
| FUB Sync with Trend Evaluation | Jan 2026 | Scoring runs audit, trend detection, daily aggregation |
| Weekly market summary report | Jan 2026 | Monday 6:30 AM automated email |
| Monthly lead activity report | Jan 2026 | 1st of month automated email |
| New listing alerts for saved searches | Jan 2026 | Daily 8:00 AM buyer digest |
| PDF property packages | Jan 2026 | WeasyPrint HTML-to-PDF |
| Historical price charts | Jan 2026 | Chart.js on property detail page |
| Customizable alert thresholds | Jan 2026 | /admin/settings with DB-stored settings |
| Admin settings page | Jan 2026 | Toggle switches for alerts/reports |
| Automatic note push on property matches | Jan 2026 | FUB API integration to push notes |
| Realtor.com scraper | Jan 2026 | __NEXT_DATA__ + DOM extraction |
| Pursuits MVP (renamed to Collections) | Feb 2026 | Buyer-property portfolios, auto-match, Mission Control widget |
| Daily email report fix | Feb 2026 | Yesterday's activity window, two-pass reassignment detection |
| Navica cron schedule | Feb 2026 | Incremental/15min, nightly full, weekly sold, daily extras |
| Elevation enrichment (USGS EPQS) | Feb 2026 | All listings enriched; dashboard + public site display; daily cron |
| County GIS documents | Feb 2026 | Documents & County Records for 7 WNC counties |
| Filter persistence | Feb 2026 | sessionStorage preserves filters across detail page navigation |
| Flood zone enrichment (FEMA NFHL) | Feb 2026 | All listings enriched with flood_zone + flood_factor; weekly cron |
| View potential enrichment (USGS) | Feb 2026 | 8-point terrain sampling, 1-10 score; weekly cron |
| Historical MLS import | Feb 2026 | 54,329 total listings from Navica |
| Enrichment pipeline script | Feb 2026 | enrich_all.sh chains elevation/flood/views; resumable |
| DOM dynamic calculation fix | Feb 2026 | Compute from list_date for active listings |
| Collections bridge (Pursuits rename) | Feb 2026 | Renamed across all dashboard UI |
| Buyer activity tracking | Feb 2026 | buyer_activity table, logging on favorites/collections/searches |
| Showing request feature | Feb 2026 | Request/cancel API, buyer UI, agent email notification |
| Agent notifications (email) | Feb 2026 | Immediate showing alerts + daily activity digest |
| Saved search email alerts | Feb 2026 | Daily/weekly cron, filter matching, buyer email with property cards |
| PostgreSQL migration | Mar 2026 | SQLite replaced in PRD + DEV; pg_adapter.py drop-in replacement |
| PhotoManager module | Mar 2026 | Unified photo management: download, storage, adapters per MLS source |
| Photo gallery fill | Mar 2026 | 28,980 photo-ready listings on PRD |
| Supabase Auth integration | Mar 2026 | Replaced NextAuth + Flask dual-auth |
| Contact form + lead capture | Mar 2026 | public_writes.py: POST /api/public/contacts with dedup |
| Web lead inbox | Mar 2026 | Dashboard inbox with filter tabs, mark worked, duplicate detection |
| Voice search + NLP parser | Mar 2026 | Web Speech API input routed through /api/public/search/parse |
| Search filters redesign | Mar 2026 | County/city dropdowns, stats summary row, single-row layout |
| DEV/PRD environment parity | Apr 2026 | Both environments on PostgreSQL |
| FUB independence | Apr 2026 | Own API key, own lead pipeline, own scoring |
| FUB DEV tagging | Apr 2026 | Auto-tag DEV contacts with DEV_TEST, source "localhost" |
| DECISIONS.md | Mar 2026 | Canonical decision registry checked into git |

---

*This file is checked into the repo and will persist across Claude sessions.*
*Update status as tasks are completed.*
