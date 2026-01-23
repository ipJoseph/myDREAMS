# myDREAMS Master To-Do List

*Exhaustive prioritized task list - check off as completed*

Last updated: January 23, 2026 (Admin Settings page added)

---

## 🔴 PRIORITY 1: High Impact / Low Effort (Quick Wins)

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 1 | **Score decay for inactive leads** | DONE | Phase 2 | 6-tier decay: 0%->5%->15%->30%->50%->70% |
| 2 | **Click-to-Call FUB deep links** | DONE | Phase 4 | Phone numbers link to FUB when fub_id available |
| 3 | **Remove unused `httpx` import** | DONE | Tech Debt | Removed from `property-dashboard/app.py` |
| 4 | **`ENABLE_STAGE_SYNC` review** | DONE | Tech Debt | Feature implemented in fub-core, disabled by default for safety |

---

## 🟠 PRIORITY 2: Core Phase 2 Features (Lead Scoring & Matching)

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 5 | **Unified Contact Workspace (Hearth Integration)** | DONE | Phase 1 | Central hub with tabs: Info, Requirements, Activity, Packages, Showings, Matches |
| 6 | **Intake-Driven Property Search** | DONE | Phase 1 | Search redfin_imports using intake criteria, multi-select for package creation |
| 7 | **Package Management in Workspace** | DONE | Phase 1 | Create packages from search, generate client links, track favorites |
| 8 | **Workflow Pipeline (Kanban View)** | DONE | Phase 4 | Drag-drop Kanban board with 10 stages, stage history, auto-inference |
| 9 | **Weighted buyer-property matching algorithm** | DONE | Phase 2 | 4-factor scoring: Price(30%), Location(25%), Size(25%), Recency(20%) |
| 9 | **Match score breakdown visualization** | DONE | Phase 2 | Visual bars showing contribution of each factor |
| 10 | **Lead requirements extraction from CRM notes** | DONE | Phase 2 | Regex parsing for price, beds, baths, acreage, counties, cities |
| 11 | **Stated requirements vs behavioral preferences** | DONE | Phase 2 | Blends stated (40%) + behavioral (60%) for matching |

---

## 🟡 PRIORITY 3: Automation & Reports (Phase 3)

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 9 | **Weekly market summary report** | DONE | Phase 3 | Monday 6:30 AM email with week-over-week stats |
| 10 | **Monthly lead activity report** | DONE | Phase 3 | 1st of month email with trends, hot/cooling leads |
| 11 | **New listing alerts for saved searches** | DONE | Phase 3 | Daily 8:00 AM digest to buyers with matching properties |
| 12 | **Historical price chart generation** | DONE | Phase 3 | Chart.js visualization on property detail page |
| 13 | **Customizable alert thresholds** | DONE | Phase 3 | `/admin/settings` page with DB-stored thresholds |

---

## 🟢 PRIORITY 4: Admin & Configuration

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 14 | **Admin settings page** | DONE | Phase 3 | `/admin/settings` with alert thresholds and report toggles |
| 15 | **Feature toggles UI** | DONE | Phase 3 | Toggle switches for alerts/reports in admin settings |
| 16 | **Automatic note push on property matches** | Pending | Phase 2 | Push matched properties to FUB notes |

---

## 🔵 PRIORITY 5: Polish & UX (Phase 4)

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 17 | **Mobile-responsive dashboard** | Pending | Phase 4 | Works on phone/tablet |
| 18 | **Dark mode support** | Pending | Phase 4 | Eye comfort option |
| 19 | **Keyboard shortcuts** | Pending | Phase 4 | Power user navigation |
| 20 | **Bulk actions interface** | Pending | Phase 4 | Multi-select operations |

---

## ⚪ PRIORITY 6: Infrastructure & Tech Debt

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 21 | **Add test suite** | Pending | Tech Debt | `/tests/` directory is empty - no tests |
| 22 | **Zillow scraper fix** | Pending | Tech Debt | Code exists but blocked by site |
| 23 | **Realtor.com scraper** | Pending | Tech Debt | Falls back to Redfin, not native |
| 24 | **Standardize error handling** | Pending | Tech Debt | Inconsistent patterns across apps |
| 25 | **Review unused database methods** | Pending | Tech Debt | Some aggregation methods may be orphaned |

---

## 📦 PRIORITY 7: Future / Package Generation

| # | Task | Status | Category | Notes |
|---|------|--------|----------|-------|
| 26 | **PDF property packages** | DONE | Phase 3 | WeasyPrint HTML-to-PDF, download from dashboard |
| 27 | **Branded property flyers** | Pending | Phase 3 | Marketing materials |
| 28 | **Comparative market analysis** | Pending | Phase 3 | CMA generation |
| 29 | **Client presentation decks** | Pending | Phase 3 | Slide generation |

---

## Completed Items

| # | Task | Completed | Notes |
|---|------|-----------|-------|
| 1 | Score decay for inactive leads | Jan 23, 2026 | 6-tier decay multipliers |
| 2 | Click-to-Call FUB deep links | Jan 23, 2026 | Phone numbers link to FUB |
| 3 | Remove unused httpx import | Jan 23, 2026 | Cleaned up dead import |
| 4 | ENABLE_STAGE_SYNC review | Jan 23, 2026 | Feature confirmed implemented, disabled by default |
| 5 | Buyer-property matching algorithm | Jan 23, 2026 | 4-factor weighted scoring in contact detail |
| 6 | Match score breakdown visualization | Jan 23, 2026 | Visual bars for Price/Location/Size/Recency |
| 8 | Stated vs behavioral preferences | Jan 23, 2026 | 60/40 blend for matching |
| - | Email deduplication | Jan 23, 2026 | New contacts deduped by email (FUB data quality) |
| - | New contacts in daily email | Jan 23, 2026 | Shows last 3 days with Today/Yesterday/N days ago |
| - | Action Management System | Jan 23, 2026 | Contact actions, My Actions page, Scoring History |
| - | Enhanced Contacts Dashboard | Jan 22, 2026 | Action Queue, Score Analysis, Insights, Trends tabs |
| - | Database Normalization | Jan 22, 2026 | contact_daily_activity, contact_actions, scoring_runs tables |
| - | FUB Sync with Trend Evaluation | Jan 22, 2026 | Scoring runs audit, trend detection, daily aggregation |
| - | Metrics dropdown | Jan 23, 2026 | Navigation menu on main dashboard |
| 10 | Lead requirements extraction from notes | Jan 23, 2026 | Regex parsing for price, beds, baths, acreage, counties, cities |
| - | Requirements consolidation (Phase 5) | Jan 23, 2026 | Multi-source merge with confidence scoring |
| - | Source comparison UI | Jan 23, 2026 | Compare intake vs behavioral vs notes values |
| - | Agent override capability | Jan 23, 2026 | Override any requirement field with confidence 1.0 |
| 9 | Weekly market summary report | Jan 23, 2026 | Monday 6:30 AM automated email |
| 10 | Monthly lead activity report | Jan 23, 2026 | 1st of month automated email |
| 11 | New listing alerts | Jan 23, 2026 | Daily 8:00 AM buyer digest |
| 26 | PDF property packages | Jan 23, 2026 | WeasyPrint generation with dashboard download |
| 12 | Historical price charts | Jan 23, 2026 | Chart.js on property detail page with price history |
| 13 | Customizable alert thresholds | Jan 23, 2026 | `/admin/settings` page with DB-stored settings |
| 14 | Admin settings page | Jan 23, 2026 | Toggle switches for alerts/reports, number inputs for thresholds |
| 15 | Feature toggles UI | Jan 23, 2026 | Boolean toggles for all automation features |

---

*This file is checked into the repo and will persist across Claude sessions.*
*Update status as tasks are completed.*
