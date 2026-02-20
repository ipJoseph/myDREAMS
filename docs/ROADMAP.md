# myDREAMS Roadmap

*Current Status & Future Development*

---

## Current Version: v1.0 (Production)

### Core Features (Completed)

| Feature | Status | Notes |
|---------|--------|-------|
| Property Scraping | Done | Zillow, Redfin, Realtor.com via Chrome Extension v3.9.16 |
| SQLite Database | Done | Canonical data store with WAL mode |
| Property API | Done | Flask REST API on port 5000 |
| Property Dashboard | Done | Flask web UI on port 5001 |
| Notion Sync | Done | Bi-directional property sync every 60s |
| IDX Validation | Done | MLS# validation with address fallback |
| IDX Portfolio | Done | Bulk portfolio creation on IDX site |
| Lead Management | Done | FUB to Google Sheets sync |

### Recent Additions (February 2026)

| Feature | Commit | Description |
|---------|--------|-------------|
| **Public Website (Next.js)** | - | `apps/public-site/` - SSR property search, listing detail with schema.org markup, area guides, contact forms |
| **Public API Endpoints** | - | `GET /api/public/listings`, `/listings/:id`, `/areas`, `/stats` - unauthenticated IDX-compliant endpoints |
| **Canopy MLS Integration** | - | `apps/mlsgrid/` - MLS Grid OData client, sync engine, cron sync for Canopy MLS (pending credentials) |
| **Multi-MLS Field Mapper** | - | `field_mapper.py` updated with agent phone fallback chain, StoriesTotal, dynamic source tagging |
| **Navica MLS First Sync** | `482b9eb` | 1,575 listings + 645 agents + 1,575 photos synced from Carolina Smokies MLS |
| **Mission Control v3** | - | Complete dashboard redesign with Intelligence Briefing Engine, Power Hour calling mode, and Command Center |
| **Briefing Card-Grid Dashboard** | `551b952` | Modular card-based Briefing tab: metric cards with drill-down, 2-column intelligence grid, Pipeline/Stats/Live Activity cards, mission card with badge strip |
| **Morning Brief Redesign** | `23ed535` | Briefing tab overhaul: Morning Pulse strip, alerts, enhanced overnight intel, value scores on cards, pipeline snapshot, Power Hour CTA |
| **Pipeline Framework** | - | `docs/PIPELINE_FRAMEWORK.md` - QUALIFY → CURATE → CLOSE → NURTURE canonical pipeline documentation |
| **Buyer Requirements Sync** | - | `templates/buyer_requirements.md` + sync scripts for markdown ↔ database sync |
| **Buyers Needing Work** | - | Dashboard section showing buyers with requirements but no recent property packages |

### Recent Additions (January 2026)

| Feature | Commit | Description |
|---------|--------|-------------|
| **Data Quality Dashboard** | - | `/data-quality` route showing coverage metrics, MLS Grid status, import history |
| **MLS Grid Integration** | - | `import_mlsgrid.py` script for Canopy MLS API (RESO Web API via MLS Grid) |
| **Data Quality Tracking** | - | `docs/DATA_QUALITY_TRACKING.md` with baseline audit and experiment tracking |
| NC OneMap Spatial Data | - | Flood zones, elevation, view potential, wildfire risk - enriches property data with NC geographic intelligence |
| Enhanced Property Ingest | - | PropStream expansion, Redfin change detection, daily CLI, changes dashboard, price drop alerts |
| IDX MLS Validation | `f157fb0` | Automatic validation with address fallback |
| On-Demand Validation | `016271b` | Validates properties when creating IDX portfolio |
| Redfin Scraper Fix | `f157fb0` | Fixed incorrect "Sold" status extraction |
| Dashboard Layout | `0917cba` | Reordered columns, IDX status badges |
| Default Search Names | `016271b` | YYMMDD.HHMM.ClientName format |

---

## Phase 1.5: Cloud Migration (In Progress)

### Phase 1 - Local Prep (Completed)
| Task | Status | Notes |
|------|--------|-------|
| Fix hardcoded paths | Done | Use `Path(__file__)` relative paths |
| API key authentication | Done | `DREAMS_API_KEY` env var, `X-API-Key` header |
| Dashboard basic auth | Done | `DASHBOARD_USERNAME/PASSWORD` env vars |
| Chrome extension API key | Done | Settings panel, stored in sync storage |
| Production URLs in manifest | Done | `wncmountain.homes` host permissions |
| Update .env.example | Done | Added auth variables |

### Phase 2 - VPS Setup (Ready)
| Task | Status | Notes |
|------|--------|-------|
| Create systemd services | Done | `deploy/systemd/mydreams-*.service` |
| Create Caddyfile | Done | `deploy/Caddyfile` with subdomains |
| Create setup script | Done | `deploy/scripts/setup-vps.sh` |
| Create deploy script | Done | `deploy/scripts/deploy.sh` |
| Create backup script | Done | `deploy/scripts/backup.sh` with B2 |
| Deployment guide | Done | `docs/DEPLOYMENT.md` |

**Next: Provision VPS and run setup script**

### Phase 3 - DNS & SSL
- [ ] Transfer DNS to Cloudflare
- [ ] Create A records for api/app/leads subdomains
- [ ] Configure Caddy reverse proxy

### Phase 4 - Migration
- [ ] Export and transfer SQLite database
- [ ] Update Chrome extension to production URL
- [ ] Test end-to-end property capture

### Phase 5 - Cron & Backup
- [ ] Set up cron jobs (FUB sync, property monitor)
- [ ] Configure daily backup to Backblaze B2
- [ ] Set up UptimeRobot monitoring

---

## Phase 2: Lead Scoring & Matching (In Progress)

### Lead Scoring System
- [x] Multi-dimensional scoring: Heat, Value, Relationship, Priority
- [x] Behavioral signal processing from CRM activities (intent signals)
- [x] Daily priority contact list generation
- [x] Score decay for inactive leads (6-tier decay multipliers)

### Unified Dashboard
- [x] Contacts list view with filtering by stage/heat
- [x] Contact detail view with scores and activity stats
- [x] Unified dashboard home with property + contact overview
- [x] SQLite as single source of truth for contacts

### Buyer-Property Matching
- [x] Contact-property relationship table (contact_properties)
- [x] Linked properties in contact detail view
- [x] Weighted matching algorithm (4-factor: Price 30%, Location 25%, Size 25%, Recency 20%)
- [x] Stated requirements vs. behavioral preferences (60/40 blend)
- [x] Match score breakdown visualization (visual bars per factor)

### Enhanced FUB Data Architecture (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| Score history table | Done | `contact_scoring_history` - daily snapshots |
| Communications table | Done | `contact_communications` - individual calls/texts |
| Events table | Done | `contact_events` - website visits, property views |
| Trend calculation | Done | Warming/cooling/stable based on score delta |
| Activity timeline | Done | Combined communications + events on contact detail |
| Trend mini-chart | Done | 7-day heat score visualization |
| Trend indicators | Done | Column on contacts list |

### Action Management System (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| contact_actions table | Done | Persistent actions that survive FUB syncs |
| contact_daily_activity table | Done | Aggregated daily stats for trend queries |
| scoring_runs table | Done | Audit trail for sync runs |
| Actions UI on contact detail | Done | Add/complete actions with modal |
| My Actions page (`/actions`) | Done | Dashboard of all pending actions |
| Scoring History page | Done | `/system/scoring-runs` audit view |
| Metrics dropdown | Done | Navigation menu on main dashboard |
| Backfill script | Done | Historical daily activity from events |

### CRM Integration Enhancements
- [x] Follow Up Boss activity sync to SQLite (fub-to-sheets)
- [x] Intent signals: repeat views, high favorites, activity burst, sharing
- [x] Activity timeline in dashboard (communications + events)
- [x] Score trend tracking and visualization
- [x] **Email tracking from FUB API** - Now fetches emails and includes in relationship scoring
- [x] Lead requirements extraction from CRM notes (regex parsing for price, beds, baths, acreage, counties, cities)
- [x] Automatic note push on property matches (FUB API integration)

---

## Phase 3: Automation & Monitoring (Completed)

### Property Monitoring
- [x] Price change detection (logged to SQLite)
- [x] Status change alerts (logged to SQLite)
- [x] VPS deployment scripts (`vps_setup.sh`, `run_monitor.sh`)
- [x] New listing alerts for buyers (matches to contact_requirements)
- [x] Historical price chart generation (Chart.js on property detail page)

**Data Source Status:**
| Source | Status | Notes |
|--------|--------|-------|
| Navica (RESO API) | Pending | Awaiting Carolina Smokies board auth, code ready in `apps/navica/` |
| Redfin | Archived | Retired, code in `archive/pre-navica-2026-02-19/` |
| Zillow | Archived | Was broken, code archived |
| Realtor.com | Working | Dedicated scraper with __NEXT_DATA__ + DOM extraction |

### Automated Reports (January 2026)
- [x] Daily priority call list email
- [x] Property changes in daily email report
- [x] Today's Changes section on dashboard
- [x] Weekly market summary (Monday 6:30 AM email with week-over-week stats)
- [x] Monthly lead activity report (1st of month, includes trends and stage transitions)
- [x] New listing alerts (Daily 8:00 AM digest to buyers with matching properties)
- [x] Customizable alert thresholds (`/admin/settings` with DB-stored thresholds)

### Automation Infrastructure (January 2026)
| Task | Status | Notes |
|------|--------|-------|
| apps/automation/ directory | Done | Shared automation infrastructure |
| Email service | Done | Jinja2 templated HTML emails |
| Weekly market summary | Done | Cron job with market_snapshots table |
| Monthly lead report | Done | Activity aggregation, pipeline analysis |
| New listing alerts | Done | Buyer matching with deduplication |
| PDF packages | Done | WeasyPrint HTML-to-PDF generation |
| Alert log table | Done | Prevents duplicate notifications |
| Market snapshots table | Done | Week-over-week comparison data |

### Properties Viewed Feature (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| Contact property summary | Done | Aggregated view history per contact |
| Who else is viewing | Done | Shows other contacts viewing same property |
| Properties Viewed UI | Done | Table on contact detail page |
| View count tracking | Done | Count of views per property |
| Favorited/Shared status | Done | Icons for favorites and shares |

### Configuration Page
- [x] Admin settings page for dashboard (`/admin/settings`)
- [ ] Configurable sync intervals
- [ ] API key management
- [ ] User preferences storage
- [x] Feature toggles (toggle switches for alerts/reports)

### Package Generation
- [x] PDF showing packages (WeasyPrint with agent branding)
- [ ] Branded property flyers
- [ ] Comparative market analysis
- [ ] Client presentation decks

---

## Phase 4: Scale & Polish (Future)

### Performance
- [ ] Property search optimization
- [ ] Batch Notion sync for large datasets
- [ ] Database indexing review
- [ ] Memory usage optimization

### User Experience
- [ ] Dark mode support
- [ ] Keyboard shortcuts
- [ ] Bulk actions interface
- [ ] Mobile-responsive dashboard

### Click-to-Call / FUB Dialer Integration (Done)
Deep-link phone numbers in dashboard to FUB contact pages for dialing.
- [x] Add FUB person ID to contact records (already have from sync)
- [x] Make phone numbers clickable links: `https://app.followupboss.com/2/people/{id}`
- [x] Implement in contact list and contact detail views
- [x] Calls logged automatically in FUB timeline

### Infrastructure
- [ ] Backup automation
- [ ] Log rotation
- [ ] Health monitoring
- [ ] Configuration validation

---

## Property Database "Bulletproof" Plan (NEW)

Goal: Make the property database a reliable single source of truth with automated data feeds.

### Current State (Baseline Audit 2026-01-31)
| Metric | Coverage | Notes |
|--------|----------|-------|
| MLS Number | 32.8% | Critical gap - need MLS Grid API |
| Photos | 11.2% | Low - need MLS photos + enhanced scraping |
| Coordinates | 82.0% | Good - NC OneMap working |
| Agent Info | 98.2% | Good |
| Parcel Link | 86.4% | Good |

### API Access Research
| Source | API? | Automation Potential |
|--------|------|---------------------|
| Canopy MLS | YES | MLS Grid (RESO Web API) - contact data@canopyrealtors.com |
| Carolina Smokies MLS | UNCLEAR | May need manual exports |
| PropStream | NO | Excel export only |
| NC OneMap | YES | Already integrated (95.7% coverage) |

### Implementation Progress
- [x] Baseline data quality audit (`docs/DATA_QUALITY_TRACKING.md`)
- [x] MLS Grid integration script (`scripts/import_mlsgrid.py`) (archived)
- [x] Data quality dashboard (`/data-quality` route)
- [x] **Navica MLS API integration** (`apps/navica/`) with RESO API access (awaiting board auth)
- [x] **Database cleanup for Navica** (Feb 2026): dropped `properties` table + 17 legacy tables, all code migrated to `listings`, DB reduced 23MB to 6.5MB
- [x] **Retired legacy importers**: Redfin, Apify, PropStream importers archived
- [ ] Carolina Smokies board authorization for Navica API access
- [ ] First Navica sync (incremental + nightly full sync via `apps/navica/cron_sync.py`)
- [ ] Rebuild price/status change tracking from Navica ModificationTimestamp

See: `docs/DATA_QUALITY_TRACKING.md` for full details.

---

## Known Issues & Tech Debt

| Issue | Priority | Status |
|-------|----------|--------|
| ~~Multiple extension versions in repo~~ | Low | Done - moved to archive/ |
| ~~Backup files scattered~~ | Low | Done - archive/ created |
| ~~Email tracking not implemented~~ | High | Done - Added email fetching from FUB API |
| **Low MLS# coverage (32.8%)** | High | Navica API will resolve (awaiting board auth) |
| **Low photo coverage (11.2%)** | High | Navica API provides photos directly |
| ~~Zillow scraper blocked~~ | Low | Retired, Navica replaces all scrapers |
| ~~Realtor.com scraper not implemented~~ | Low | Done - Dedicated scraper with __NEXT_DATA__ + DOM extraction |
| Inconsistent error handling | Medium | Standardize patterns |
| Missing unit tests | Medium | Add test coverage |

---

## Linear ↔ FUB Task Sync (February 2026)

Linear integration for task management with buyer journey phase tracking.

### Core Sync Engine
| Task | Status | Notes |
|------|--------|-------|
| Linear GraphQL client | Done | Teams, issues, projects, labels, milestones |
| FUB task client | Done | CRUD operations, person/deal queries |
| Bidirectional sync | Done | FUB → Linear and Linear → FUB |
| Completion sync | Done | Complete in one system → complete in other |
| Person labels | Done | Track buyer across teams/phases |
| Team routing | Done | DEVELOP (Qualify+Curate), TRANSACT (Acquire+Close) |

### Project Templates (Approach D)
| Task | Status | Notes |
|------|--------|-------|
| Template definitions | Done | QUALIFY, CURATE, ACQUIRE, CLOSE |
| Project factory | Done | Create projects from templates |
| Milestone creation | Done | Predefined milestones per phase |
| Issue population | Done | Pre-populated tasks per milestone |
| Duplicate detection | Done | Skip if project exists for person/phase |
| CLI commands | Done | create-qualify, create-curate, create-acquire, create-close |
| Database tracking | Done | project_instances, project_milestones tables |

### Future Enhancements
- [ ] Automatic project creation on FUB deal stage change
- [ ] Progress sync (completed issues → project progress)
- [ ] Seller journey templates (LIST, MARKET, NEGOTIATE, CLOSE)
- [ ] Webhook-based sync (real-time instead of polling)

---

## Rollback Points

| Commit | Date | Description |
|--------|------|-------------|
| `016271b` | Jan 17, 2026 | Current stable - default search names |
| `0917cba` | Jan 17, 2026 | Pre-validation - dashboard layout only |
| `f157fb0` | Jan 17, 2026 | IDX validation + scraper fix |

---

---

## Strategic Discussion Queued

**Platform Architecture Discussion** - See [PLATFORM_ARCHITECTURE_DISCUSSION.md](PLATFORM_ARCHITECTURE_DISCUSSION.md)

The tension between personal workflow optimization vs. building a configurable platform for others. Topics include:
- Data architecture abstraction
- CRM-agnostic design
- Plugin/adapter patterns
- Configuration vs. code trade-offs

---

## Contributing

1. Check this roadmap before starting new features
2. Update status when completing items
3. Add rollback points for significant changes
4. Document architectural decisions in ARCHITECTURE.md

---

*Roadmap maintained by Joseph & Claude*
*Last updated: February 19, 2026 - Navica migration: database cleanup, legacy importers archived*
