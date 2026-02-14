# Changelog

All notable changes to myDREAMS are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Power Hour Queue Preview Panel** — Right-side panel showing full call queue during Power Hour
  - Source selector: switch between DREAMS Priority and 7 FUB Smart Lists (New Leads, Priority, Hot, Warm, Cool, Unresponsive, Timeframe Empty)
  - Compact/Detail view toggle: names-only or names + stage/heat/timeframe info
  - Live status tracking: completed (strikethrough), current (blue highlight), upcoming
  - Click-to-jump: click any upcoming contact to skip directly to them
  - Auto-scroll keeps current contact in view
  - Responsive: stacks below main content on narrow screens
  - New API endpoint `/api/power-hour/fub-queue/<list>` fetches and formats FUB contacts for Power Hour
- **End of Day Report** (`/eod`) — Daily accountability page that closes the loop on Mission Control
  - "Did I Do the Work?" — Stat grid (calls, reached, VMs, texts, appointments, selling time) with disposition breakdown bar
  - "What Moved Today?" — Score movers split into warming/cooling with delta badges, pipeline snapshot
  - "What Are My Leads Doing?" — Property views by contact, high-intent signals (favorites/shares)
  - "What Fell Through the Cracks?" — High-priority contacts not reached today, red-tinted accountability cards
  - "Tomorrow's Setup" — Top 5 priority contacts with intelligence briefings, week-over-week trend indicator
  - All sections collapsible, empty states with friendly messages
  - Sidebar nav item with checkmark icon after Dashboard
- **Comprehensive Settings page** (`/admin/settings`) — Shows all 60+ .env vars alongside DB settings
  - 12 categorized collapsible sections: FUB, Email, Scoring, Integrations, Scraping, IDX, Task Sync, Linear, Performance, Exclusions, Agent Info, System
  - .env settings displayed read-only with lock icon, monospace values, and secret masking (last 4 chars)
  - DB settings remain fully editable with existing toggle/number/text controls
  - Environment badge (DEV/PRD) and source legend at top of page
  - Automation Rules callout card linking to dedicated `/admin/automation` page
  - Expand/Collapse all buttons for quick navigation
- **Smart Lists comparison page** (`/smart-lists`) — FUB live lists vs DREAMS scoring, side by side
  - Left panel: live FUB smart list counts fetched on-demand via API
  - Right panel: DREAMS-computed lists from local scoring (heat, relationship, priority)
  - Comparison strip per list: shows overlap count, FUB-only, DREAMS-only
  - Expandable rows reveal contacts on each side with outlier markers
  - Outlier contacts (appearing on only one side) get colored dot + click-to-reveal explanation
  - FUB-only reasons: "Not synced to DREAMS", "Heat score is 28 (threshold: 70)", etc.
  - DREAMS-only reasons: "DREAMS heat=72 qualifies as Hot — FUB uses different activity rules", etc.
  - All 7 team lists: New Leads, Priority, Hot, Warm, Cool, Unresponsive, Timeframe Empty
  - `FUBClient.fetch_smart_lists()` and `fetch_smart_list_people()` added to fub-core
- **Mission Control v3** (`home_v3.html`) — Complete dashboard redesign: launchpad, not newspaper
  - **Intelligence Briefing Engine** (`intelligence.py`) — Auto-generated one-sentence briefings for every contact
    - 8 prioritized rules: Activity Burst, New Lead, Warming Trend, Going Cold, Follow-Up Due, High Intent, Needs Properties, Default
    - Each briefing includes category, urgency level, and suggested conversation opener
  - **Morning Briefing mode** (default) — Three sections:
    - "While You Were Away" — Names and actions, not counts ("Sarah Chen viewed 4 properties")
    - "Today's Mission" — Contacts in 3 urgency groups (Act Now / Follow Up / Touch Base) with intelligence briefings
    - "Pipeline Pulse" — Pipeline as sentences with names, prices, and next actions
  - **Power Hour mode** — Focused calling with flashcard-style contact cards
    - Pre-serialized contacts (no server round-trips between calls)
    - Disposition buttons: Called, Left VM, Texted, No Answer, Appointment, Skip
    - Keyboard shortcuts: 1-5 for dispositions, 0/S to skip
    - Live scoreboard: reached, VMs, appointments, elapsed time
    - Session data persists in `power_hour_sessions` / `power_hour_dispositions` tables
  - **Command Center mode** — Working dashboard for throughout the day
    - Expandable contact cards with full detail on click
    - Live activity feed (polls every 60s): who's viewing what, right now
    - Compact pipeline strip with today's stats
  - **Keyboard shortcuts**: B (Briefing), P (Power Hour), C (Command Center)
  - **API endpoints**: `/api/power-hour/start`, `/disposition`, `/end`, `/api/live-activity`
  - **New DB methods**: `get_morning_briefing_contacts()`, `get_overnight_narrative()`, `get_pipeline_narrative()`, `get_todays_call_stats()`, `get_live_activity_feed()`
  - **Safe rollback**: `/?v2=1` serves the existing v2 dashboard unchanged
  - **New tables**: `power_hour_sessions`, `power_hour_dispositions`

- **Contact Group Separation** — Scored leads vs pond watchlists are now distinct
  - New `contact_group` column on `leads` table: `scored`, `brand_new`, `hand_raised`, `agents_vendors`, `warm_pond`
  - Only contacts assigned to the agent are scored; pond contacts imported with zero scores
  - Dashboard views replaced: My Leads, Brand New, Hand Raised, Warm Pond, Agents/Vendors, All
  - Pond views sort by last activity (not priority score)
  - Call list, hottest leads, pipeline, and going-cold all filter to scored contacts only
  - FUB client tags `_contact_group` during fetch for proper group assignment
  - Fixed LEADS_COLUMNS whitelist — `assigned_user_id`, `assigned_user_name`, and 7 other columns were silently stripped from every upsert

- **Daily Dashboard v2** (`home_v2.html`) — Redesigned home page optimized for morning workflow
  - Overnight summary cards: new leads, price drops, status changes, going cold (with "quiet night" fallback)
  - Embedded call list with 5 tabs (Priority, New, Hot, Follow-Up, Going Cold) — no page navigation needed
  - Keyboard shortcuts: press 1-5 to switch call list tabs
  - Hottest leads panel (top 8 by heat score with activity details)
  - Send properties panel (buyers with matching properties)
  - Compact pipeline bar: Leads → Buyers → Properties → Pursuits → Contracts
  - Active deals panel (stage badges, values, addresses from FUB)
  - Buyers needing properties panel (days since last package, criteria summary)
  - Rollback: `/?v2=0` loads original dashboard; `home.html` untouched
- **Automation Rules Engine** — Code-defined rules with DB-configurable thresholds that act on behavioral signals
  - 5 initial rules: Activity Burst, Going Cold, Hot Lead, Warming Lead, New Lead
  - Each rule evaluates conditions, checks per-contact cooldowns, and dispatches actions (email alerts, FUB tasks)
  - `automation_log` table tracks all rule firings with cooldown enforcement
  - CLI runner: `python -m apps.automation.run_rules` (supports `--dry-run`, `--rule`, `--verbose`)
  - Admin UI at `/admin/automation` with per-rule toggles, threshold config, and activity log viewer
  - `create_task()` added to `fub_core.FUBClient` for FUB task creation
  - 18 new `system_settings` entries (category: automation) for rule configuration
  - Navigation link added to dashboard menu

### Changed
- **Production Gunicorn Switch** - Replaced Flask development server with gunicorn for production
  - 2 sync workers with 120s timeout for PDF/import operations
  - `preload_app = True` ensures background threads (Notion sync, IDX validation) start once in master
  - Services bind to `127.0.0.1` only (Caddy handles external traffic)
  - Shared config at `deploy/gunicorn.conf.py`
  - Deploy script now auto-copies service files and runs `daemon-reload`
  - Local dev (`python app.py`) continues to work unchanged

### Security
- **SQL Injection Prevention** (`src/core/database.py`)
  - Added column whitelists (PROPERTIES_COLUMNS, LEADS_COLUMNS) to `upsert_property_dict()` and `upsert_contact_dict()`
  - Dictionary keys from API requests are now validated against known table columns before SQL interpolation
  - Invalid columns are logged and stripped rather than injected into queries
- **JS Injection Fix** (`services/idx_validation_service.py`)
  - Address values now escaped via `json.dumps()` before interpolation into `page.evaluate()` JavaScript
- **Debug Mode Guarded** (all 4 Flask apps)
  - Changed hardcoded `debug=True` to `os.getenv('FLASK_DEBUG')` — disabled by default
  - Affects: property-api, property-dashboard, buyer-workflow, redfin-importer
- **Auth Bypass Warnings** (property-api, property-dashboard)
  - Added CRITICAL log when auth env vars are missing in production (`DREAMS_ENV=prd`)
  - Added WARNING log for development mode
- **Hardcoded Secret Removed** (`.claude/settings.local.json`)
  - Replaced plaintext Apify API token with env var reference `$APIFY_TOKEN`
- **CORS Restricted** (`property-api/app.py`)
  - Replaced wildcard `*` with allowlist: dashboard + localhost (configurable via `CORS_ALLOWED_ORIGINS` env var)
- **Photos Route Auth** (`property-dashboard/app.py`)
  - Added `@requires_auth` to `/photos/<path:filename>` route

### Added
- **FUB List Dashboard Page** (`/fub-list`)
  - Grouped call list organized by heat tier (New Leads, Hot, Warm, Cool, Unresponsive, Timeframe Empty)
  - Click name → DREAMS contact page, click phone → FUB contact for dialing
  - Added FUB List + Call List navigation links to all dashboard templates

### Fixed
- **Scoring Guards: False Attribution Prevention** (`fub_to_sheets_v2.py`)
  - Fixed critical data integrity issue where stale RealGeeks cookies inflated scores for opted-out contacts
  - Barbara O'Hara incident: 30 false property views from stale cookie showed her as #1 most active
  - **Guard 1 - Stage filter**: Skip IDX events from Trash stage contacts
  - **Guard 2 - Tag filter**: Skip events from Unsubscribed/DNC/Do Not Contact tagged contacts
  - **Guard 3 - Anomaly detection**: Flag people with 15+ events/day and zero inbound communication
  - **Guard 4 - Score neutralization**: Zero out event-based stats for suspicious attribution
  - Guards applied across full pipeline: `build_person_stats`, `compute_daily_activity_stats`, `sync_events_to_sqlite`

- **Pipeline Infrastructure & Buyer Requirements** (`docs/PIPELINE_FRAMEWORK.md`, `scripts/`, `templates/`)
  - **QUALIFY → CURATE → CLOSE → NURTURE Pipeline Documentation**
    - Canonical pipeline reference with phase definitions and exit criteria
    - Google Drive folder structure conventions
    - FUB stage mapping for each phase
    - Database integration points
  - **Markdown-Based Buyer Requirements** (`templates/buyer_requirements.md`)
    - YAML frontmatter for machine-parseable sync with database
    - Human-readable sections for agents to fill in
    - Syncs bidirectionally with `intake_forms` table
  - **Sync Scripts** (`scripts/sync_requirements_to_drive.py`, `scripts/sync_requirements_from_drive.py`)
    - Export intake forms to markdown files in client folders
    - Import markdown frontmatter back to database
    - Preserves manual edits outside frontmatter
  - **Dashboard Integration** - "Buyers Needing Property Work" section on home page
    - Shows buyers with active requirements but no recent property packages
    - Quick links to property search and workspace
    - New database method `get_buyers_needing_property_work()`

- **Linear Project Templates for Buyer Journey** (`modules/linear_sync/templates.py`)
  - **Approach D Implementation**: Each buyer journey phase becomes a project from a template
  - **Four Phase Templates**:
    - **QUALIFY**: 3 milestones, 10 issues (lead qualification)
    - **CURATE**: 3 milestones, 10 issues (property search)
    - **ACQUIRE**: 2 milestones, 8 issues (offer/negotiation)
    - **CLOSE**: 5 milestones, 22 issues (contract to closing)
  - **Project Factory** (`project_factory.py`):
    - Instantiate projects from templates with milestones and pre-populated issues
    - Automatic person label creation and application
    - Duplicate detection (skip if project exists for person/phase)
    - Support for property address in ACQUIRE/CLOSE phases
  - **Enhanced Linear API** (`linear_client.py`):
    - Project milestones: create, get, update, delete
    - Extended project operations with description and state
    - Issue creation with project_milestone_id attachment
  - **Database Tracking** (`db.py`):
    - `project_instances` table - tracks projects per person/phase
    - `project_milestones` table - caches milestone data
    - Query methods for person journey, active projects, stats
  - **CLI Commands**:
    - `templates` - Show available templates with issues
    - `create-qualify/curate/acquire/close` - Create projects from templates
    - `list-projects` - Show all active project instances

- **Linear ↔ FUB Task Sync** (`modules/linear_sync/`)
  - Bidirectional task synchronization between Linear and Follow Up Boss
  - **Process Group Architecture** - Teams mapped to buyer journey phases:
    - **DEVELOP team**: Lead development (Qualify + Curate phases)
    - **TRANSACT team**: Active deals (Acquire + Close phases)
    - **GENERAL team**: Admin, marketing, operations
  - **FUB → Linear**: Tasks auto-sync to issues with:
    - Team routing based on deal stage
    - Person labels for cross-team journey tracking
    - Projects in TRANSACT for concrete deals
    - Priority mapping from FUB task types
  - **Linear → FUB**: Create FUB tasks from Linear issues with:
    - Person label lookup for contact association
    - Task type inference from Linear labels
  - **Linear GraphQL Client** - Full API support:
    - Teams, workflow states, labels, projects, issues
    - Create/update/complete operations
    - Updated-since queries for efficient polling
  - **Sync Engine** - Change detection, anti-loop protection, completion sync
  - **Poller Service** - Async polling with configurable intervals
  - **Setup Wizard** - Auto-configure teams and labels from Linear workspace
  - **CLI Interface** - `python -m modules.linear_sync <command>`
  - **Bridge Database** - SQLite tables for issue mapping, team config, person labels, sync state, audit logs
  - **Systemd Integration** - Service file for production deployment
  - Configuration: `LINEAR_API_KEY`, `LINEAR_POLL_INTERVAL`, team IDs

- **Todoist ↔ FUB Task Sync** (`modules/task_sync/`)
  - Bidirectional task synchronization between Todoist and Follow Up Boss
  - **FUB → Todoist**: Tasks auto-sync with person name, deal stage, and project routing
  - **Todoist → FUB**: Create FUB tasks from Todoist with person context:
    - `@fub:12345` - Direct FUB person ID in task content
    - `[Person Name]` - Search FUB by name (e.g., "Call back [John Smith]")
    - Project-based - Tasks in pipeline-stage projects auto-link to deals
  - **FUB Client** - Full task API support (CRUD, completion, deal/pipeline queries, person search)
  - **Todoist Client** - Unified API v1 support (REST + Sync endpoints)
  - **Sync Engine** - Change detection, anti-loop protection, last-write-wins conflict resolution
  - **Poller Service** - Async polling with configurable intervals via `.env`
  - **CLI Interface** - `python -m modules.task_sync <test|status|sync-once|sync-all|sync-todoist|run>`
  - **Bridge Database** - SQLite tables for task mapping, sync state, and audit logs
  - **Systemd Integration** - Service files for dev and production deployment
  - Configuration: `FUB_POLL_INTERVAL`, `TODOIST_POLL_INTERVAL`, `DEAL_CACHE_REFRESH`

- **Active Deals Dashboard Section** - Shows active pipeline deals on home dashboard
  - Stage-colored card borders (Pending=blue, Offer=orange, Contract=yellow, New=green)
  - Deal value and property address display
  - Quick links: View Deal, Call, Email
  - Filters out Closed and Terminated stages

- **Enhanced Todoist Task Display** - Richer task context on dashboard
  - Deal stage, value, and property address in task metadata
  - Direct link to FUB Deal page on tasks with associated deals
  - Todoist tasks grouped by project with color indicators

- **Home Dashboard Redesign** - Action-oriented morning briefing reflecting the three-step sales framework
  - **Today's Priority Actions** - Three-column layout for Calls, Follow-ups, and Send Properties
    - Prioritized by score with contact details and quick links
    - Direct FUB integration links for each contact
  - **Pipeline Snapshot** - Visual dual-input funnel showing the sales flow
    - LEADS → BUYERS → PURSUITS → CONTRACTS
    - Properties feed into Pursuits as the property source
    - 7-day delta indicators for trend awareness
    - Counts for need-intake buyers and pipeline value
  - **Hottest Leads** - Top 5 by heat score with color-coded indicators
    - Shows activity metrics (properties viewed, saved, last activity)
  - **Overnight Changes** - Grouped by type for quick scanning
    - New Leads, Price Drops, Status Changes, Going Cold sections
  - **Active Pursuits** - Buyer + Property portfolio view
    - Criteria summary, property counts, new matches indicator
    - "Send Update" and "View Buyer" actions
  - **New Data Model** - Pursuits table for buyer-property relationships
    - `pursuits` table linking buyers to property portfolios
    - `pursuit_properties` table tracking property status in pursuit
  - **Documentation** - `docs/SALES_FLOW.md` documenting the dual-input funnel model
  - **Database Methods** - New query functions for dashboard data
    - `get_pipeline_snapshot()` - Stage counts with deltas
    - `get_todays_actions()` - Calls, follow-ups, buyers needing properties
    - `get_overnight_changes()` - Recent leads, price drops, status changes
    - `get_hottest_leads()` - Top leads by heat score
    - `get_active_pursuits()` - Active buyer-property portfolios

- **Property Database "Bulletproof" Plan** - Foundation for reliable single source of truth
  - **MLS Grid Integration** (`scripts/import_mlsgrid.py`)
    - Full RESO Web API client for Canopy MLS data
    - OAuth2 authentication with long-term tokens
    - Field mapping from RESO data dictionary to myDREAMS schema
    - Incremental sync support (only changed records since last run)
    - Media/photos extraction with proper attribution
    - Rate limiting (0.6s delay, respects 2 req/sec limit)
    - Supports `--full`, `--incremental`, `--status`, `--dry-run`, `--test` flags
    - Sync state persistence in `data/mlsgrid_sync_state.json`
  - **Data Quality Dashboard** (`/data-quality`)
    - Listings coverage metrics (MLS#, photos, coords, agent info)
    - Parcels spatial enrichment status
    - Data source breakdown by MLS source
    - Photo source and review status
    - City-level coverage visualization
    - Recent import history (30 days)
    - MLS Grid API status panel
    - Recommended action items
    - API endpoint (`/api/data-quality`) for programmatic access
  - **Data Quality Tracking** (`docs/DATA_QUALITY_TRACKING.md`)
    - Baseline audit (32.8% MLS#, 11.2% photos, 82% coords)
    - API availability matrix (Canopy MLS, PropStream, NC OneMap)
    - Data flow architecture diagram
    - Gap analysis with resolution paths
    - Experiment tracking template
    - Implementation plan phases
  - Navigation link in Metrics dropdown on home page

- **Photos Dashboard Redesign** - MLS-style property listing view
  - Horizontal property cards with photo on left, details on right
  - Geospatial data section (elevation, flood zone, view potential, slope, aspect, wildfire risk)
  - Filters: county, min/max price, sort options (newest, price, beds, acreage, elevation)
  - View tabs: Verified, Pending, All
  - Color-coded indicators for geospatial risk factors

- **Property System Architecture Reset** - Normalized two-table schema (parcels + listings)
  - **New Schema Design** - Clean separation of immutable parcel data from transactional listing data:
    - `parcels` table: Physical land data (APN, county, coordinates, owner info, tax values, spatial data)
    - `listings` table: MLS/listing data (status, price, beds/baths, photos, agent info)
    - `contact_listings` junction table: Lead-property relationships with workflow tracking
    - `listing_photos` audit table: Photo verification with confidence scoring
    - `enrichment_queue` table: Priority-based photo/data enrichment queue
  - **Photo Verification System** (`scripts/enrich_photos_verified.py`):
    - Multi-factor matching (address, price, beds/baths, coordinates)
    - Confidence scoring with auto-accept (>=90%), accept-with-note (70-89%), review queue (50-69%), reject (<50%)
    - Audit trail in `listing_photos` table
    - Rate limiting to avoid aggregator blocking
  - **PropStream Importer Updates** (`scripts/import_propstream.py`):
    - Added `--reset` flag to clear existing data for fresh imports
    - Denormalizes address fields to listings for fast queries
    - Populates both parcels and listings tables
  - **Database Migration** (`scripts/migrate_property_schema_v2.py`):
    - Adds spatial columns to parcels (flood_zone, elevation, view_potential, wildfire_risk)
    - Adds photo verification columns to listings (photo_source, photo_confidence, photo_verified_at)
    - Creates `properties_v2` view for backwards compatibility
  - **Dashboard Compatibility**:
    - Updated to use `properties_v2` view (falls back to `properties` if view missing)
    - Listings gallery now uses denormalized address fields (faster queries)
  - **Data Pipeline** (for e2e testing later):
    1. PropStream import → parcels + listings baseline
    2. NC OneMap enrichment → coordinates + spatial data
    3. Photo verification → verified photos with confidence scores

- **NC OneMap Spatial Data Integration** - Enrich properties with geographic intelligence
  - **Spatial Data Service** (`src/services/spatial_data_service.py`) - Core service for NC OneMap API queries
    - Flood zone queries (FEMA flood hazard areas with risk scoring)
    - Elevation data via USGS National Map API
    - Wildfire risk assessment
    - View potential calculation for mountain properties
  - **Database Schema** - New spatial columns on `properties` table:
    - `flood_zone`, `flood_zone_subtype`, `flood_factor` (1-10 risk score), `flood_sfha`
    - `elevation_feet`, `slope_percent`, `aspect`
    - `view_potential` (1-10 mountain view score)
    - `wildfire_risk`, `wildfire_score`
    - `spatial_enriched_at` timestamp
  - **Batch Enrichment Script** (`scripts/enrich_spatial.py`)
    - Enrich all properties with spatial data
    - Supports `--limit`, `--county`, `--force`, `--dry-run` flags
    - Rate limiting (0.5s default) to respect API limits
  - **Interactive Map View** (`/properties/map`)
    - Leaflet.js-powered property map with marker clustering
    - Filter sidebar (status, county, price range)
    - Property popups with spatial badges
    - Toggle for high view potential properties
  - **Property Detail Enhancement**
    - Spatial data badges (flood zone, elevation, views, wildfire risk)
    - Property Analysis sidebar section with spatial grid
    - Mini-map with property location (click to open Google Maps)
  - Data sources: NC OneMap (flood zones), USGS National Map (elevation)

- **Contact View Filtering** - Dashboard now defaults to showing your contacts only
  - **View switcher dropdown** on home and contacts pages
  - **Available views**: My Leads (default), Team, Ponds, Agents, All Contacts
  - **My Leads**: Shows contacts assigned to you (341 for Joseph)
  - **Ponds**: Shows contacts in Ava Cares pond (104 contacts)
  - **Team**: All team contacts except ponds
  - **Agents**: Contacts with Agents/Vendors/Lenders stage (75 contacts)
  - **All**: Complete database view (458 contacts)
  - View selection persists when navigating between pages

- **Lead Reassignment Tracking** - Track leads that get reassigned away (round-robin timeout, transfers)
  - **New database columns**: `reassigned_at`, `reassigned_from_user_id`, `reassigned_reason`
  - **Detection during sync**: Automatically detects when leads disappear from your FUB assignments
  - **"Leads Reassigned" section in daily email**: Shows leads lost in last 7 days with reason
  - **PRD sync frequency doubled**: Now syncs at 6am AND 6pm to catch fast-moving round-robin leads
  - **Fix**: FUB API field mapping (`assignedUserId` instead of `ownerId`)

- **Property Deduplication & Provenance Tracking** - Prevent duplicate imports and track data freshness
  - **UPSERT on redfin_id** - Unique constraint prevents Redfin-to-Redfin duplicates on re-import
  - **Provenance columns** - Track data origin and freshness:
    - `first_seen_at` - When property was first imported
    - `first_seen_source` - Original data source (redfin, propstream)
    - `listing_last_seen_at` - Last time property appeared in Redfin feed
    - `delisted_at` - When property was marked as off-market
  - **Delisting detection** - Properties not seen in feed for 3+ days marked OFF_MARKET
  - **Migration**: `apps/apify-importer/migrations/001_dedup_tracking.sql`
  - Backfilled 13,815 existing records with provenance data
- **My Leads Assignment Tracking** - Track lead assignments with full history
  - **Database tables**: `fub_users` (team member cache), `assignment_history` (assignment changes)
  - **FUB client extension**: `fetch_users()`, `fetch_current_user()` methods
  - **Assignment sync in FUB sync**: Tracks `ownerId` changes and logs to history
  - **My Leads page** (`/my-leads`) - Dashboard view of leads assigned to you:
    - Stats cards: Currently assigned, received (30d), transferred out (30d)
    - Filter tabs: Current, All History, Previously Mine
    - Assignment history per lead with expand/collapse
    - Links to contact detail and FUB
  - **Initial sync script**: `scripts/sync_assignments.py` - Backfill existing assignments
  - **Navigation**: Added to Metrics dropdown menu on home dashboard
  - Config: `FUB_MY_USER_ID` in `.env` sets your user ID (default: 8 for Joseph Williams)
- **Unified Property Database Architecture** - Consolidated property data into single dreams.db
  - Migrated 1,858 properties from redfin_imports.db into dreams.db (103 merged, 1,755 new)
  - Smart merge logic: matches by MLS# first, then normalized address
  - Source tracking with `sources_json` column (e.g., `["redfin_csv", "propstream"]`)
  - Updated importers (redfin_csv_importer.py, propstream_importer.py) to write directly to dreams.db
  - Added 45+ new columns for PropStream data (owner info, financials, condition, liens)
  - One-time migration script: `scripts/migrate_redfin_to_dreams.py`
  - Benefits: No cross-database JOINs, consistent property matching, unified change tracking
- **Enhanced Property Data Ingest System** - Hybrid property data system using PropStream and Redfin
  - **PropStream Importer Expansion** - 8 new column mappings for comprehensive property data:
    - Prior sale history (date, amount)
    - Condition ratings (bathroom, kitchen)
    - Foreclosure factor
    - Lien details (type, date, amount)
  - **Change Detection for Redfin CSV** - Automatic tracking of property changes:
    - Price changes with percentage calculation
    - Status changes (Active, Pending, Sold)
    - Days on market updates
    - New listing detection
    - All changes logged to `property_changes` table
  - **Daily Import CLI** (`apps/redfin-importer/daily_import.py`) - Unified command for daily operations:
    - `--redfin` flag for CSV imports with change detection
    - `--propstream` flag for bulk Excel imports
    - `--report` flag for change summaries
    - `--since` parameter for flexible date ranges
  - **Property Changes Dashboard** (`/properties/changes`) - Visual change tracking:
    - Summary cards for price drops, new listings, status changes
    - Tabbed view by change type
    - Filter by county and time period (1-30 days)
    - Direct links to Redfin listings
  - **Price Drop Alerts** - Enhanced automation for buyer notifications:
    - `send_price_drop_alerts()` function in `new_listing_alerts.py`
    - Configurable minimum drop percentage (default 5%)
    - Lower match threshold for price drops (default 50 vs 60 for new listings)
    - FUB note push for matched price drops
    - New settings: `price_drop_alerts_enabled`, `price_drop_match_threshold`, `min_price_drop_pct`
- **Realtor.com Scraper** - Dedicated property scraper for Realtor.com (Chrome extension v3.9.27)
  - Extracts from `__NEXT_DATA__` JSON embedded in page
  - DOM fallback for robust data extraction
  - Property detail and search results scraping
  - Full field support: price, beds, baths, sqft, lot size, agent info, MLS, photos
  - Integrated with existing extension architecture (`window.RealtorScraper`)
- **Admin Settings Page** - Configurable alert thresholds and automation behavior at `/admin/settings`
  - **System Settings Database** - New `system_settings` table for persistent configuration
    - Key-value storage with type conversion (string, integer, float, boolean, json)
    - Category grouping (alerts, reports, general)
    - Audit trail with updated_at and updated_by fields
  - **Alert Settings** - Configurable parameters for new listing alerts:
    - Match threshold (0-100%) - minimum score to trigger alerts
    - Lookback hours - how far back to check for new listings
    - Max properties per email - limit properties in single alert
    - New listing alerts enabled toggle
    - Global alerts master switch
  - **Report Settings** - Toggle switches for scheduled reports:
    - Weekly market summary (Monday 6:30 AM)
    - Monthly lead report (1st of month 7:00 AM)
  - **Admin UI** - Clean settings interface with:
    - Toggle switches for boolean settings
    - Number inputs for thresholds with validation
    - Category grouping (Alerts, Reports)
    - Success/error feedback on save
  - **Database Helper** - `get_db_setting()` function in automation config
    - Reads from database with fallback to environment variables
    - Automatic type conversion based on setting type
  - Routes: GET/POST `/admin/settings`, GET/PUT `/api/admin/settings`
  - Database methods: `get_setting()`, `set_setting()`, `get_all_settings()`
  - All automation scripts updated to check enabled flags before running
- **FUB Note Push on Property Matches** - Automatic CRM integration when properties match buyers
  - **FUBClient.create_note()** - New method to POST notes to FUB API `/notes` endpoint
  - **Automatic Trigger** - When new listing alerts match a buyer, push note to their FUB contact
  - **Note Content** - Formatted summary with property details, price, specs, match score, and URLs
  - **Toggle Setting** - `fub_note_push_enabled` in admin settings (Integrations category)
  - **Stats Tracking** - `notes_pushed` count in alert run statistics
  - Graceful fallback if FUB_API_KEY not set or fub_core not installed
- **Automation & Reports (Phase 3)** - Scheduled automation features for market intelligence and client engagement
  - **Weekly Market Summary** - Monday 6:30 AM email with week-over-week market statistics:
    - Market snapshots captured to `market_snapshots` table
    - Active listings, new listings, price trends, days on market
    - County-by-county breakdown for WNC tracked counties
    - Key insights generation with notable listings
  - **New Listing Alerts** - Daily 8:00 AM digest emails to buyers:
    - Matches new properties to buyer requirements from `contact_requirements`
    - Match scoring based on price, beds, baths, location, size, acreage
    - Deduplication via `alert_log` table to prevent duplicate alerts
    - Configurable match threshold (default 60%)
  - **Monthly Lead Report** - 1st of month 7:00 AM lead activity summary:
    - Pipeline stage overview and transitions
    - Month-over-month engagement comparison
    - Hot leads (warming up) and cooling leads (need attention)
    - New leads added during the month
  - **PDF Property Packages** - Generate branded PDF packages for buyers:
    - WeasyPrint HTML-to-PDF conversion
    - Cover page with agent branding and client name
    - Property pages with photos, specs, details, features
    - Agent contact page with branding
    - Download button added to package detail page
  - New directory: `apps/automation/` with shared infrastructure
  - Shared email service: `email_service.py` with Jinja2 templates
  - HTML email templates: `weekly_summary.html`, `listing_alert.html`, `monthly_report.html`, `property_package.html`
  - Database tables: `alert_log`, `market_snapshots`
  - Dashboard route: GET `/contacts/<id>/packages/<id>/pdf` for PDF download
  - Cron jobs: `weekly_market_summary.py`, `new_listing_alerts.py`, `monthly_lead_report.py`
- **Historical Price Charts** - Property detail page with price history visualization:
  - Chart.js line chart showing price changes over time
  - Property detail page with photo gallery, stats, and details
  - Recent changes sidebar (price drops, status changes)
  - Interested contacts sidebar showing who has viewed/favorited
  - Links to external listings (Redfin, Zillow, IDX)
  - Database method: `get_property_price_history()` queries initial price, price changes
  - Routes: GET `/properties/<id>` (detail page), GET `/api/properties/<id>/price-history`
  - Dashboard links: Property addresses now link to detail page
- **Requirements Consolidation (Phase 5)** - Multi-source requirements merging with confidence tracking
  - **Consolidated Requirements** - Merges data from multiple sources with per-field confidence:
    - Intake forms (0.9 base confidence)
    - Behavioral analysis (0.7 base confidence, scaled by data volume)
    - Note parsing (0.6 base confidence)
    - Agent overrides (1.0 confidence, always wins)
  - **Note Parsing** - Regex extraction of requirements from FUB notes:
    - Price ranges ($300k-$500k, budget of $400,000, etc.)
    - Beds/baths (3 bed, 2 bath, etc.)
    - Acreage (5 acres, 10+ acres, etc.)
    - Counties (Buncombe, Henderson, etc.)
    - Cities (Asheville, Black Mountain, etc.)
  - **Source Comparison UI** - Collapsible table comparing values across all sources
  - **Agent Override** - Click "Override" on any field to set a manual value
  - **Data Completeness Meter** - Visual indicator of how much data we have
  - **Confidence Bars** - Per-field confidence indicators with color coding
  - **Refresh Button** - Re-consolidate from all sources on demand
  - Database tables: `contact_requirements`, `requirements_changes`
  - API endpoints:
    - GET `/api/contacts/<id>/requirements` - Get consolidated requirements
    - POST `/api/contacts/<id>/requirements/override` - Override a field
    - POST `/api/contacts/<id>/requirements/refresh` - Re-consolidate
    - GET `/api/contacts/<id>/requirements/changes` - Audit trail
- **Workflow Pipeline (Phase 4)** - Kanban-style pipeline for contact workflow management
  - **Pipeline View** (`/pipeline`) - Drag-and-drop Kanban board with 10 workflow stages:
    - New Lead, Requirements Discovery, Active Search, Reviewing Options
    - Showing Scheduled, Post-Showing, Offer Pending, Under Contract, Closed, Nurture
  - **Workflow Database Table** - `contact_workflow` table tracking current stage, stage history, and transitions
  - **Stage Transition API** - POST to `/api/contacts/<id>/workflow/stage` to move contacts between stages
  - **Auto-Stage Inference** - Automatically infer appropriate stage based on contact activity
  - **Bulk Initialize** - Initialize workflow records for all existing contacts
  - Contact cards show priority score, heat score, and days since activity
  - Pipeline link added to Contacts page navigation
- **Unified Contact Workspace (Phase 1 - Hearth Integration)** - Central hub for buyer management
  - **Contact Workspace** (`/contacts/<id>/workspace`) - Tabbed interface with:
    - Info tab: Contact details, scores, intent signals, actions
    - Requirements tab: Intake forms with inline editing + behavioral inference
    - Activity tab: Timeline of communications and events
    - Packages tab: Property packages for this contact
    - Showings tab: Scheduled and past showings
    - Matches tab: AI-suggested properties
  - **Intake Form Editor** - Create/edit buyer requirements inline in workspace
  - **Property Search** (`/contacts/<id>/search`) - Search redfin_imports database using intake criteria
    - Grid view with multi-select checkboxes
    - Floating action bar for package creation
    - Search based on stated requirements OR behavioral preferences
  - **Package Creation** - Create packages from selected search results
    - Auto-generates shareable client links
    - Shows client favorites and showing requests
  - **"Open Workspace" button** - Added to contact detail page header for quick access
  - New templates: `contact_workspace.html`, `property_search_results.html`, `package_detail.html`
  - Migrated intake form functionality from buyer-workflow to property-dashboard
- **Buyer-Property Matching (Phase 2)** - Intelligent property recommendations on contact detail
  - **Weighted Multi-Factor Scoring** - 4 factors with configurable weights:
    - Price fit (30%): Blends stated + behavioral price preferences
    - Location (25%): Matches cities from viewed properties
    - Size (25%): Meets bedroom/bathroom requirements
    - Recency (20%): Newer listings score higher
  - **Behavioral Preference Inference** - Analyzes contact_events to infer:
    - Price range (10th-90th percentile of viewed properties)
    - Preferred cities from viewed properties
    - View and favorite counts
    - Confidence score based on data volume
  - **Stated vs Behavioral Blend** - 60% behavioral + 40% stated preferences
  - **Visual Score Breakdown** - Colored bars showing contribution of each factor
  - **Inferred Preferences Display** - Shows what we learned from their behavior
  - API endpoint: `/api/contacts/<id>/matches`
  - Refresh button to regenerate matches
- **Score Decay for Inactive Leads** - 6-tier time-based decay multipliers
  - 0-7 days: No decay (1.0x)
  - 8-14 days: 5% decay (0.95x)
  - 15-30 days: 15% decay (0.85x)
  - 31-60 days: 30% decay (0.70x)
  - 61-90 days: 50% decay (0.50x)
  - 90+ days: 70% decay (0.30x)
  - Based on ANY activity (website visits, property views, etc.)
- **Click-to-Call FUB Deep Links** - Phone numbers link to FUB contact page
  - Available when fub_id present on contact
  - Shows FUB icon with link in contacts, actions, and detail pages
- **Metrics Dashboard Dropdown** - Quick access to system pages from main dashboard
  - Links to Actions and Scoring History pages
  - Hover dropdown with proper gap bridging
- **New Contacts in Daily Email** - Shows contacts added in last 3 days
  - Formatted with "Today", "Yesterday", "N days ago" labels
  - Deduplicated by email (handles FUB duplicate records)

### Fixed
- **Email Deduplication** - New contacts list now dedupes by email address
  - Addresses FUB data quality issue where contacts appear twice with different fub_ids
  - Keeps the most complete record (prefers one with phone number)

### Removed
- Unused `httpx` import from property-dashboard/app.py

- **Action Management System** - Full task tracking for contacts
  - **Contact Actions UI** - Actions section on contact detail page with add/complete functionality
  - **My Actions Page** (`/actions`) - Dashboard view of all pending actions across contacts
    - Grouped by: Overdue, Due Today, Upcoming, No Due Date
    - Quick action buttons (Call, Email) with contact info
    - Mark complete with animated removal
  - **Scoring Runs History** (`/system/scoring-runs`) - Audit trail of FUB sync runs
    - Shows run time, status, source, stats (processed/scored/new/updated)
    - Duration and expandable config snapshots for debugging
  - API endpoints for CRUD operations on actions
  - Navigation links added to all dashboard pages

- **Enhanced Contacts Dashboard** - Merged best features from Apps Script dashboard
  - **Action Queue Tab** - Prioritized leads grouped by urgency tier (Immediate Contact, High Value Warm, Nurture Opportunities, Re-engagement)
  - **Score Analysis Tab** - Distribution charts for Priority/Heat/Value/Relationship scores with visual breakdown
  - **Strategic Insights Tab** - AI-style actionable recommendations (High-Value Cold Leads, Leads Stuck in Pipeline, High-Intent Quiet Leads, Perfect Prospects)
  - **Trends Tab** - Activity pattern visualization (Active/Warm/Cold/Stale distribution)
  - **Suggested Action per Contact** - Color-coded badges showing recommended next action based on scores
  - Tabbed interface with counts for quick navigation
  - Direct call/email buttons in Action Queue
  - Contact chips linking to detail pages from Insights

- **Database Normalization** - New tables for improved data architecture
  - **contact_daily_activity** - Aggregated daily stats per contact for efficient trend queries
  - **contact_actions** - Persistent action tracking that survives FUB syncs (replaces overwritten next_action fields)
  - **scoring_runs** - Audit trail for when/how scoring runs occurred
  - Backfill script to populate historical daily activity from existing events (1800+ records)
  - Full database methods for all new tables (CRUD operations, aggregations, stats)

- **Enhanced FUB Sync with Trend Evaluation** - Major refactor of fub_to_sheets_v2.py
  - **Scoring Runs Audit Trail** - Every sync now tracked with timing, counts, config snapshot, and status
  - **Trend Evaluation** - Compares current scores to 7-day average, detects warming/cooling/stable
  - **Trend Alerts** - Logs significant score changes (>20 point heat delta)
  - **Daily Activity Aggregation** - Auto-populates contact_daily_activity after each sync
  - **Action Migration** - One-time migration of next_action fields to persistent contact_actions table
  - **Config Snapshot** - Scoring weights captured with each run for debugging/auditing
  - **Error Handling** - Failed runs properly recorded with error messages

- **Buyer Workflow Search Results Enhancement** - Improved property selection for package creation
  - Selection checkboxes on each property card with Select All toggle
  - Address now links directly to Redfin listing (removed redundant Redfin button)
  - MLS# opens Canopy MLS directly with authenticated session (one-time login required)
  - Selected count displays in header and Create Package button
  - Package creation now adds only selected properties instead of all results
  - "Fetch Photos" button to trigger photo scraping for missing property photos
  - API endpoints: `/api/mls/open/<mls#>`, `/api/photos/scrape`, `/api/photos/status`
- **Redfin CSV Importer** - Bulk property import from Redfin CSV exports
  - `apps/redfin-importer/` module with 4 components
  - `wnc_zip_county.py` - ZIP to County lookup for 100+ Western NC ZIP codes
  - `redfin_csv_importer.py` - CSV parser with field mapping, deduplication, MLS merging
  - `redfin_page_scraper.py` - Playwright scraper for agent info and engagement metrics
  - `redfin_auto_download.py` - Automated Redfin search + download + import pipeline
  - Separate database (`data/redfin_imports.db`) to avoid disrupting main DREAMS
  - Supports multi-county downloads with price filters
  - NC County codes for URL construction (Macon, Jackson, Swain, Cherokee, etc.)
- **Top Priority Contacts Enhancement** - Added contact info to home dashboard
  - Phone number with tel: link
  - Email with Gmail compose URL (authuser=Joseph@JonTharpHomes.com)
  - FUB link with icon matching detail page style
- **Status Dot Colors** - Updated visual indicators
  - Sold: changed to red
  - Contingent: changed to grey
- **Dashboard Favicon** - Stylish house/moon icon for browser tab
  - Red gradient favicon for DEV environment (`DREAMS_ENV=dev`)
  - Blue gradient favicon for PRD environment (`DREAMS_ENV=prd`)
  - SVG format for crisp display at any size
  - Embodies "dream of home ownership" with house, moon, and stars motif
- **Zillow Photo Extraction** - Property monitor now captures photos from Zillow listings
  - Implemented `_extract_photo()` for `ZillowPlaywrightScraper`
  - Extracts from NEXT_DATA JSON, og:image meta tag, Zillow CDN URLs
  - Handles multiple Zillow JSON structures (media, hdpData, responsivePhotos)
  - Properties from both Redfin AND Zillow now get photos during daily monitor
- **IDX Automation Improvements** - Reliable login and save search functionality
  - Added browserless.io cloud browser support for headless VPS environments
  - Added IPRoyal residential proxy support to bypass datacenter IP blocking
  - Added `SKIP_PROXY` env var for localhost (home IP not blocked)
  - Added `FORCE_LOCAL_BROWSER` env var to bypass browserless.io
  - Debug screenshots at each login step for troubleshooting
  - Login verification with credential fill confirmation
  - Graceful handling of browser disconnect during save (form submission)
  - Fixed race condition in progress polling (was showing stale "complete" status)
  - DEV: browser navigates to saved searches page and stays open 30s for verification
  - Completion modal shows actual property count and "View Saved Searches" link
  - Auto-opens IDX saved searches page in new browser tab on completion
  - Fixed 30s timeout caused by `networkidle` wait (now uses `load` state)
  - Fixed save dialog name not being filled (target modal, clear before fill)
  - Removed blocking alert() that caused browserless.io disconnect
  - DEV uses local browser (fast), PRD uses browserless.io + proxy
  - **Fully working on both DEV and PRD**
- **Git Workflow Documentation** - Added to CLAUDE.md
  - DEV vs PRD environment paths documented
  - SSH git commands for PRD using `git -C /opt/mydreams`
  - Full deploy workflow example
- **Client Portfolio Password Protection** - Shareable portfolio links for clients
  - Simple password protection on `/client/<name>` route
  - Clean login form with Jon Tharp Homes branding
  - Portfolio URL with embedded key copied to clipboard when creating IDX portfolio
  - Password: `dreams2026`
- **FUB Phone Integration** - Quick access to Follow Up Boss contacts
  - Phone numbers on contacts list link directly to FUB contact page
  - Contact detail page has FUB icon next to phone number
  - URL format: `JonTharpTeam.followupboss.com/2/people/view/{fub_id}`
- **Chrome Extension v3.9.24** - UI improvements and bug fixes
  - Renamed "Scraping" to "Collecting Data" (less litigious terminology)
  - "Deep Scrape" → "Deep Capture"
  - Completion message: "✓ Complete! X properties selected. Y saved for [user]"
  - Smaller popout window (520x780) to fit content
  - Faster initialization - event listeners setup first
  - Fixed tab detection for reliable popout communication
- **Chrome Extension v3.9.20** - Fixed UI freezing and performance improvements
  - Disabled background property existence checks (caused freezes)
  - Interaction-aware pausing for any remaining async operations
  - Fixed popout window losing connection to source tab
- **Chrome Extension v3.9.18** - Fixed Chrome Web Store submission
  - Removed unused `scripting` permission that caused rejection
- **IDX Photo Support** - Property photos from IDX site
  - `photo_url` column in `idx_property_cache` table
  - Photo scraping in `populate_idx_cache.py`
  - Fallback mechanism: properties without Notion photos display IDX photos
  - `enrich_properties_with_idx_photos()` function in dashboard
- **IDX Cache Cron Jobs** - Automated MLS# → Address lookup
  - `run_idx_cache.sh` wrapper script for local cron
  - `run_idx_cache_prd.sh` wrapper script for PRD cron
  - Runs twice daily (6:30 AM and 6:30 PM) on both local and PRD
  - Processes up to 100 uncached MLS numbers per run
- **Contacts Page Enhancements** - Improved lead management UI
  - Threshold sliders for Hot Leads and High Value metric cards
  - Views, Favorites, Shares columns in contacts table
  - Search box with real-time filtering (name, email, phone)
  - Clickable metric cards for quick filtering
- **Selected Property Count** - Shows count of selected properties below total on dashboard
- **Range Slider Component** - Added to shared design system
  - `.dreams-slider` base class with grey track
  - Color variants: `dreams-slider-red`, `dreams-slider-green`, `dreams-slider-blue`
  - CSS variable `--slider-percent` for fill position
  - Cross-browser support (Webkit + Firefox)
- Shared CSS design system (`shared/css/dreams.css`)
- Archive folder for deprecated code
- CHANGELOG.md for tracking releases
- **Properties Viewed Section** - Contact detail page enhancement
  - `get_contact_property_summary()` - Aggregated property view history per contact
  - `get_property_interested_contacts()` - "Who else is viewing" feature
  - Properties Viewed table with view counts, favorite/share status
  - Links to other contacts viewing same properties
- **Property Changes Tracking** - Monitor and report property changes
  - `property_changes` table for tracking price/status changes
  - Property monitor logs changes to SQLite database
  - Today's Changes section on dashboard home
  - Property changes included in daily email report
  - Filter tabs for price vs status changes
- **VPS Property Monitor Setup** - Deployment scripts for production
  - `run_monitor.sh` - Cron-ready monitor execution script
  - `vps_setup.sh` - One-command VPS setup for Playwright
  - PRD cron configured: daily 5am EST (10:00 UTC)
- **Enhanced FUB Data Architecture** - Activity history, scoring trends, proper relational tables
  - `contact_scoring_history` table for tracking score snapshots over time
  - `contact_communications` table for individual call/text records
  - `contact_events` table for website visits, property views, favorites
  - Daily scoring history with trend calculation (warming/cooling/stable)
  - Activity timeline on contact detail view (communications + events)
  - Score trend mini-chart with 7-day average and delta
  - Trend indicator column on contacts list
- **Cloud Migration Phase 1** - Authentication & portable paths
  - API key authentication for Property API (`X-API-Key` header)
  - Basic auth for Property Dashboard admin routes
  - Chrome extension API key support in settings
  - Production URL support (`wncmountain.homes`) in manifest
  - Updated `.env.example` with new auth variables
- **Cloud Migration Phase 2** - Deployment infrastructure
  - systemd service files for API and Dashboard
  - Caddyfile for reverse proxy with subdomains
  - VPS setup script (`setup-vps.sh`)
  - Deployment script (`deploy.sh`)
  - Backup script with B2 support (`backup.sh`)
  - Comprehensive deployment guide (`docs/DEPLOYMENT.md`)
- **Platform Unification** - Contacts integration and unified dashboard
  - Contacts API endpoints (`/api/v1/contacts/*`)
  - SQLite contacts schema with FUB activity stats and scoring fields
  - Contact-property relationship table for linking saved/matched properties
  - Unified dashboard home with property + contact overview
  - Contacts list view with filtering by stage/heat
  - Contact detail view with scores, activity stats, intent signals
  - FUB-to-Sheets SQLite sync (parallel output alongside Sheets)

### Changed
- **Property Dashboard Code Quality** - Comprehensive code review and cleanup
  - Consolidated 4 duplicate `get_unique_*` functions into single `get_unique_values(properties, key)`
  - Extracted duplicate status count logic into `calculate_status_counts()` helper
  - Replaced `print()` statements with proper `logging` module
  - Made debug screenshots conditional via `DEBUG_SCREENSHOTS` env var
  - Added named timeout constants with rationale (TIMEOUT_JS_RENDER, TIMEOUT_PANEL_APPEAR, etc.)
  - Fixed JavaScript string escaping using `json.dumps()` for safety in `page.evaluate()` calls
  - Added return type hints to key functions (`fetch_properties`, `calculate_metrics`, etc.)
  - Added typing imports to app.py
- **Address Links Prioritize IDX** - Property addresses now link to team IDX site
  - If MLS number exists → link to `smokymountainhomes4sale.com/property/{mls}`
  - If no MLS but have source URL → link to Redfin/Zillow
  - Removed Notion links entirely (not user-facing)
- **SQLite as Source of Truth** - Dashboard now reads from SQLite instead of Notion
  - `fetch_properties()` queries SQLite database directly
  - Notion becomes secondary sync destination for external sharing
  - Eliminates data inconsistency issues between sources
- **Contacts Table Sorting** - Column headers now sortable, matching dashboard pattern
  - Uses shared CSS classes (`sorted-asc`, `sorted-desc`)
  - 3-state cycle: ascending → descending → original order
- Moved old extension versions (v1, v2) to `archive/`
- Updated ARCHITECTURE.md with actual color values
- **Path Portability** - Replaced hardcoded `/home/bigeug/` paths with `Path(__file__)` relative paths
  - `apps/property-dashboard/app.py`
  - `apps/property-dashboard/idx_automation.py`
  - `apps/property-api/services/idx_validation_service.py`
  - `apps/property-monitor/monitor_properties.py`
- **CSS Consolidation** - Removed ~700 lines of duplicate inline CSS
  - `dashboard.html` - Now uses dreams.css classes
  - `lead_dashboard.html` - Now uses dreams.css classes
  - `fub_dashboard_enhanced.html` - Updated colors to DREAMS palette
  - Added contact/lead stage badge styles to dreams.css
- **Dashboard Routing** - Reorganized URLs
  - `/` now shows unified dashboard home
  - `/properties` shows property list (formerly `/`)
  - `/contacts` shows contacts list (new)

### Fixed
- **Deprecated Async Pattern** - Replaced `asyncio.new_event_loop()` with `asyncio.run()` in app.py
- **Broken Context Manager** - Fixed `__aexit__` to return `False` instead of `None` (was suppressing exceptions)
- **Redundant Import** - Removed local `import re` from `clean_county_name()` (already imported at module level)
- **Contact-Event Data Mismatch** - Events now correctly linked to contacts
  - Fixed fub_id lookup in `get_contact_property_summary()`
  - Fixed fub_id lookup in `get_activity_timeline()`
  - Fixed fub_id lookup in `get_contact_trend_summary()`
  - Contacts with UUID IDs now correctly display their events (events stored with FUB numeric ID)
- **Contact Detail Labels** - Clarified "Property Views" (total) vs "Unique Properties" (deduplicated)

---

## [1.1.0] - 2026-01-17

### Added
- **IDX MLS Validation** - Automatic validation with address fallback when MLS# not found (`d6d46e9`)
- **On-Demand Validation** - Validates pending properties when creating IDX portfolio (`f157fb0`)
- **UI Design System Documentation** - Color palette, typography, component patterns (`d872a15`)
- **ROADMAP.md** - Project phases and progress tracking

### Changed
- Dashboard layout: narrower address column, reordered columns, city moved right (`0917cba`)
- Default search name format: `YYMMDD.HHMM.ClientName` (`016271b`)
- More robust save search in IDX automation (`ed75764`)

### Fixed
- Redfin scraper incorrectly marking properties as "Sold" (`f157fb0`)
- IDX automation browser profile conflicts (`402d862`)

---

## [1.0.0] - 2026-01-16

### Added
- **Property Dashboard** - Web UI with filters, metrics, sorting (`ef36458`)
- **Lead Dashboard** - Client-facing view at `/lead/<client_name>` (`e479da8`)
- **IDX Portfolio Automation** - Playwright-based bulk portfolio creation (`a7dcfe9`)
- **IDX Auto-Login** - Automatic authentication for IDX site (`1b39a95`)
- **Save Search** - Save portfolios as named searches on IDX (`346c2d9`)
- **Batch Property Capture** - Capture multiple properties at once (`dc33bd6`)
- **3-State Sort Toggle** - Asc → Desc → Original order (`328c9f1`)
- **Horizontal Scrollbar** - Better table navigation (`328c9f1`)

### Changed
- Replaced ScraperAPI with Playwright for property monitoring (`1211539`)

### Fixed
- Photo capture reliability improvements (`ef36458`)
- IDX form submission simplified to JavaScript only (`51a273e`)
- Viewport sizing for IDX popup windows (`ff20265`)

---

## [0.9.0] - 2026-01-15

### Added
- **Property API** - Flask REST API on port 5000 (`35a578c`)
- **Chrome Extension v3** - Complete rewrite with multi-site support (`35a578c`)
- **Property Monitor** - Playwright-based price/status monitoring (`d5b3e80`)
- **Multi-Source Scraping** - Zillow, Redfin, Realtor.com support

---

## [0.8.0] - 2026-01-01

### Added
- **myDREAMS Branding** - Renamed from Integrity Dev OS (`cf87809`)
- **Clasp Integration** - Apps Script development workflow (`6968ee4`)
- **Backup/Restore System** - Secrets management (`dc5c3b2`)

### Changed
- FUB-to-Sheets converted from submodule to integrated code (`fdd638a`)

---

## [0.7.0] - 2025-12-23

### Added
- **Apps Script Dashboard** - Google Sheets lead visualization (`e98a112`)
- **Dashboard Enhancements** - Improved lead scoring display (`7362847`)

---

## [0.6.0] - 2025-12-22

### Added
- **fub-core Library** - Shared FUB API SDK (`287577e`)

### Changed
- Refactored fub_core package structure (`162be0e`)

---

## [0.5.0] - 2025-12-18

### Added
- **Vendor Directory App** - SQLite-based vendor management (`c2e3696`)
  - Add vendor command (`99fbe53`)
  - List vendors command (`7dc614a`)
  - Export to CSV (`fadea7c`)
  - Expanded schema with additional fields (`a094cdf`)
- **ADR 0002** - Vendor Directory architecture decision (`c4bb6ca`)

---

## [0.1.0] - 2025-12-18

### Added
- **Initial Repository Structure** - Integrity Dev OS baseline (`3718a05`)
- **ADR 0001** - Development OS baseline decision (`44e617f`)
- **Project Index** - Tracking active projects (`e4cc732`)
- **Assistant Roles** - AI assistant coordination patterns (`8429150`)
- **Daily Status Pattern** - Progress tracking template (`76f7254`)
- **Standard AI Prompt** - Multi-agent coordination (`7edba18`)

---

## Version Guide

| Version | Milestone |
|---------|-----------|
| 1.1.x | IDX Validation & Design System |
| 1.0.x | Property Dashboard & IDX Automation |
| 0.9.x | Property API & Chrome Extension v3 |
| 0.8.x | myDREAMS Rebrand |
| 0.7.x | Apps Script Dashboard |
| 0.6.x | fub-core Library |
| 0.5.x | Vendor Directory |
| 0.1.x | Initial Setup |

---

*Maintained by Joseph & Claude*
