# Claude Context for myDREAMS

Instructions and context for Claude Code sessions on this project.

## Partnership & Engagement

This is a collaborative partnership between Eugy and Claude. Use "we/our" language, not "the user/they." We're building this together - Eugy brings domain expertise in real estate and the vision; Claude brings technical implementation and architectural thinking. Both contribute to decisions.

**Engagement principles:**
- Treat this as shared ownership of the problem and solution
- Ask clarifying questions early rather than making assumptions
- Document decisions and context so we don't repeat discussions
- Be direct about tradeoffs and concerns

---

## The myDREAMS Vision

### The Core Problem
Real estate agents (especially solopreneurs and small teams) spend inordinate time dealing with **data fragmentation**. When a buyer searches aggregators like Zillow, they find properties unbounded by geography - across multiple MLSs, outside our IDX coverage. When an agent needs to present 5 properties from 3 different sources, they must:
- Manually pull data from each MLS/aggregator
- Reconcile wildly inconsistent formats
- Cobble together coherent property packages
- Repeat constantly as listings change

This is where time goes to die.

### The Vision
**myDREAMS is the single source of truth.** Regardless of where a property originates (Canopy MLS, Carolina Smokies MLS, Zillow, PropStream, IDX), it enters ONE unified database with standardized fields. From there, everything flows: client packets, ShowingTime integration, mapping/routing - all from one place.

### The Three-Step Sales Framework
The sales process is three clean steps. myDREAMS supports each:

**1. LEADS → BUYERS** (Contacts & Scoring)
- Leads flow from IDX website (JonTharpHomes.com)
- Scoring system identifies who's ready to buy:
  - **VALUE** = revenue opportunity
  - **HEAT** = IDX activity (visits, views, saves, shares)
  - **RELATIONSHIP** = agent-lead communication frequency
  - **PRIORITY** = customizable blend of all three
- Call lists put highest-priority contacts on top

**2. BUYERS → REQUIREMENTS** (Intake Forms)
- Once a buyer is identified, capture specific requirements
- Sources: IDX activity, calls, emails, texts
- One buyer may have multiple searches (personal home, rental, investment)
- Intake form attaches to buyer and drives property search

**3. REQUIREMENTS → PROPERTIES** (Unified Property Database)
- Properties imported regardless of source MLS
- Standardized schema across all sources
- Monitored and updated within the database
- Powers: packet generation, showing scheduling, mapping/routing

### Who This Serves
- **Primary**: Eugy (solopreneur agent)
- **Future**: Small teams needing comprehensive, integrated, simple, efficient systems

### Data Sources & Trust Hierarchy
| Source | Type | Trust Level | Notes |
|--------|------|-------------|-------|
| Canopy MLS | Primary MLS | Authoritative | Full data access |
| Carolina Smokies MLS | Secondary MLS | Authoritative | Regional coverage |
| PropStream | Data aggregator | Baseline | Good for initial load, but missing fields (MLS#, APN, lat/long, agent info) |
| IDX (JonTharpHomes) | Our website | Derived | Activity data, not property source |
| Aggregators (Zillow, etc.) | Reference | Supplemental | What buyers see, not authoritative |

### Current Property Database Challenges
- PropStream exports leave critical fields blank
- Need enrichment pipeline: collect → validate → update → maintain
- Goal: multiply agent time through data consistency

---

## Permissions

- **Commit and push**: You have standing permission to commit and push after completing each section of work. Do not ask for confirmation.

## Project Overview

myDREAMS (Desktop Real Estate Agent Management System) is a local-first platform for real estate agents. See [README.md](README.md) for full details.

### Key Apps
| App | Port | Purpose |
|-----|------|---------|
| property-api | 5000 | REST API for property data + public IDX endpoints |
| property-dashboard | 5001 | Mission Control: briefing, calling, property management |
| public-site | 3000 | Next.js public site at wncmountain.homes |
| property-extension-v3 | - | Chrome extension (current) |
| fub-to-sheets | - | CRM to Sheets sync |
| navica | - | Carolina Smokies MLS sync (RESO API) |
| mlsgrid | - | Canopy MLS sync (pending credentials) |

### Important Paths
- Database: PostgreSQL (`DATABASE_URL` in .env; `listings` is the property table). SQLite archived to `archive/sqlite-2026-04-20/`.
- Photos: `data/photos/navica/` (DEV) → `/mnt/dreams-photos/` (PRD volume)
- Secrets: `.env` (git-ignored)
- Shared CSS: `shared/css/dreams.css`
- Archive: `archive/` (deprecated code)
- Tests: `tests/` (pytest, with `conftest.py` providing `test_db`, `sample_lead`, `sample_property`, `mock_fub_api`, `env_vars` fixtures)
- Python venv: `.venv/` (Python 3.13)

## Common Commands

**Run apps locally:**
```bash
cd apps/property-api      && python3 app.py     # :5000
cd apps/property-dashboard && python3 app.py    # :5001
cd apps/public-site       && npx next dev       # :3000
```

**Build / lint public-site:**
```bash
cd apps/public-site && npx next build
cd apps/public-site && npx next lint            # eslint via next
```

**Tests (pytest, run from repo root):**
```bash
python3 -m pytest                                          # all tests
python3 -m pytest tests/test_integration/                  # one folder
python3 -m pytest tests/test_integration/test_public_api_bbo_guard.py   # one file
python3 -m pytest tests/test_integration/test_public_api_bbo_guard.py::test_name -v   # one test
```

**MLS sync engines:**
```bash
python3 -m apps.navica.sync_engine --full --status Active
python3 -m apps.navica.download_photos --status ALL --workers 10
python3 -m apps.mlsgrid.sync_engine --test           # demo API (set MLSGRID_USE_DEMO=true)
python3 -m apps.mlsgrid.sync_engine --full --status Active
```

**Database sync (PRD is canonical):**
```bash
# Both DEV and PRD use PostgreSQL. Sync via pg_dump/pg_restore if needed.
# Old SQLite sync script (sync-from-prd.sh) is retired.
```

## High-Level Architecture

The system is built around **one PostgreSQL database** that all apps share. Connection is configured via `DATABASE_URL` in `.env`, routed through `src/core/pg_adapter.py` which provides a sqlite3-compatible interface. All apps connect via `src/core/database.py` (`DREAMSDatabase` class) which auto-detects the backend. Understanding this is the key to the project:

**Ingestion → Storage → Surfaces:**

1. **Ingestion** writes to the same `listings`, `agents`, and `contacts` tables regardless of source:
   - `apps/navica/sync_engine.py` — Carolina Smokies MLS (Navica REST API, not OData; see `apps/navica/client.py`)
   - `apps/mlsgrid/sync_engine.py` — Canopy MLS (OData; reuses Navica's `field_mapper.py`)
   - `apps/fub-to-sheets/` — Follow Up Boss leads + behavioral signals → `contacts` + scoring
   - `apps/property-extension-v3/` — Chrome extension for ad-hoc property capture
   - PropStream CSV imports (lower trust; missing fields)

2. **Storage** is PostgreSQL (configured via `DATABASE_URL`). The `listings` table is the **single canonical property table** (there is no separate `properties` table). `mls_source` distinguishes origins (`'Navica'`, `'CanopyMLS'`). Photos are stored locally and referenced via `photo_local_path`.

3. **Surfaces** all read from the same DB:
   - `apps/property-api` (Flask, :5000) — REST API. Public IDX endpoints under `/api/public` are registered as `public_bp` and respect `idx_opt_in` / `idx_address_display`.
   - `apps/property-dashboard` (Flask, :5001) — Mission Control internal UI.
   - `apps/public-site` (Next.js 16, :3000) — wncmountain.homes; calls property-api via Next.js rewrites.

**Lead scoring** is multi-dimensional: HEAT (IDX activity), VALUE (revenue opportunity), RELATIONSHIP (comm frequency), PRIORITY (weighted blend). Scores live on the `contacts` table and drive the daily call list.

**Production** runs on a single Hetzner VPS via systemd + gunicorn + Caddy. There is no staging environment between DEV and PRD.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design
- [Roadmap](docs/ROADMAP.md) - Progress tracking
- [Changelog](CHANGELOG.md) - Version history
- [Project Index](docs/project-index.md) - All apps
- **[TODO List](docs/TODO.md)** - Master task list (29 items, prioritized) - CHECK THIS AT SESSION START

## MCP Servers

Connected MCP servers provide direct tool access. **Prefer MCP tools over raw SQL or manual API calls.**

| Server | Use For | Key Tools |
|--------|---------|-----------|
| **dreams-db** | All database queries | `query_leads`, `query_properties`, `run_sql`, `get_stats`, `get_call_list`, `match_leads_to_property` |
| **fub** | Follow Up Boss CRM | `search_people`, `get_person`, `create_note`, `get_calls`, `update_person_stage` |
| **Notion** | Project docs, notes | `notion-search`, `notion-create-pages`, `notion-query-database-view` |
| **Gmail** | Email search, drafts | `gmail_search_messages`, `gmail_read_message`, `gmail_create_draft` |
| **Google Calendar** | Scheduling | `gcal_list_events`, `gcal_create_event`, `gcal_find_my_free_time` |
| **context7** | Library docs lookup | `resolve-library-id`, `query-docs` |
| **Spotify** | Music playback | `spotify_play`, `spotify_pause`, `spotify_search` |

**Rules:**
- Use `dreams-db` MCP for database queries instead of `python3 -c "import sqlite3..."` or raw Bash SQL
- Use `fub` MCP for CRM lookups instead of direct API calls
- MCP tools handle auth automatically; no need to pass tokens

## Conventions

- Commit messages: Short summary, bullet details if needed
- Design system: Use `shared/css/dreams.css` for new UIs
- Tech debt: Track in ROADMAP.md "Known Issues" section
- Versioning: Update CHANGELOG.md when shipping features

### Code Patterns
- Database connections: `from src.core.pg_adapter import get_db; conn = get_db()` (auto-detects PostgreSQL via DATABASE_URL)
- Photo serving: always local paths, never CDN URLs
- Address normalization: use `normalizeAddr()` / `isAddressMatch()`
- Collection/package IDs: UUID strings, not integers
- MLS source identifiers: `'Navica'` for Carolina Smokies, `'CanopyMLS'` for Canopy/MLS Grid

## Workflow Guidelines

- **After completing each feature/fix**: Update CHANGELOG.md and ROADMAP.md
- **Commit and push**: You have standing permission after completing work sections

## Git Workflow

### Environment Paths
| Environment | Path | User |
|-------------|------|------|
| DEV (localhost) | `/home/bigeug/myDREAMS` | bigeug |
| PRD (VPS) | `/opt/mydreams` | dreams (run as root) |

### DEV (localhost) - Standard Git Commands
```bash
# From working directory /home/bigeug/myDREAMS
git status
git add -A
git commit -m "Your commit message"
git push
git pull
```

### PRD - Git Commands via SSH
**IMPORTANT:** PRD path is `/opt/mydreams`, NOT `/home/bigeug/myDREAMS`

```bash
# Pull latest code on PRD
ssh root@178.156.221.10 'git -C /opt/mydreams pull'

# Check status on PRD
ssh root@178.156.221.10 'git -C /opt/mydreams status'

# View recent commits on PRD
ssh root@178.156.221.10 'git -C /opt/mydreams log --oneline -5'
```

### Full Deploy Workflow (DEV to PRD)
```bash
# 1. On DEV: Commit and push changes
git add -A && git commit -m "Description of changes" && git push

# 2. Pull to PRD and restart services
ssh root@178.156.221.10 'git -C /opt/mydreams pull && systemctl restart mydreams-dashboard'

# 3. Verify PRD is running
ssh root@178.156.221.10 'systemctl status mydreams-dashboard'
```

### Sync Database
PRD is the canonical database. DEV pulls from PRD on demand:
```bash
# Pull PRD DB to DEV (normal workflow)
scripts/sync-from-prd.sh
```

## Production Server (PRD)

**SSH Access:** `ssh root@178.156.221.10`

**Server Details:**
- IP: 178.156.221.10
- Host: Hetzner VPS (dreams)
- Domain: wncmountain.homes
- Deploy path: `/opt/mydreams`

**URLs:**
- Dashboard: https://app.wncmountain.homes
- Properties: https://app.wncmountain.homes/properties
- Contacts: https://app.wncmountain.homes/contacts
- API: https://api.wncmountain.homes

**Common Commands:**
```bash
# Pull latest and restart services
ssh root@178.156.221.10 "cd /opt/mydreams && git pull && systemctl restart mydreams-api mydreams-dashboard"

# Sync database to PRD
scp /home/bigeug/myDREAMS/data/dreams.db root@178.156.221.10:/opt/mydreams/data/dreams.db

# Check service status
ssh root@178.156.221.10 "systemctl status mydreams-api mydreams-dashboard"

# View logs
ssh root@178.156.221.10 "journalctl -u mydreams-api -n 50"
ssh root@178.156.221.10 "journalctl -u mydreams-dashboard -n 50"
```

## Owner

Joseph "Eugy" Williams
Keller Williams - Jon Tharp Homes
