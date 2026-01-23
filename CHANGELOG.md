# Changelog

All notable changes to myDREAMS are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
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
