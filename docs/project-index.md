# Project Index

This file tracks all active applications and components in myDREAMS.

## How to use
- One section per app/component
- Keep this high-level and current
- Link out to deeper docs as needed

---

## Platform: myDREAMS

**Desktop Real Estate Agent Management System**

Status: **Production (v2.0)**
Owner: Joseph Williams
Last Updated: February 23, 2026

### Purpose
Local-first platform for real estate agents to capture properties, manage leads, track buyer pursuits, and automate client workflows.

### Documentation
- [Architecture](ARCHITECTURE.md) - System design, data flow
- [Roadmap](ROADMAP.md) - Phases and progress
- [Changelog](../CHANGELOG.md) - Version history

---

## Active Applications

### property-api
**Status:** Production | **Port:** 5000

Flask REST API serving property data, public IDX endpoints, and internal management endpoints.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/public/listings` | Public listing search (IDX-compliant, no auth) |
| `GET /api/public/listings/:id` | Public listing detail |
| `GET /api/public/areas` | Cities/counties with listing stats |
| `GET /api/public/stats` | Aggregate market statistics |
| `GET /properties` | Internal: list all properties |
| `POST /property` | Internal: receive property data |

---

### property-dashboard (Mission Control)
**Status:** Production | **Port:** 5001

Flask web UI for agent operations. Mission Control v3 with Intelligence Briefing, Power Hour calling, and Command Center modes.

| Route | Purpose |
|-------|---------|
| `/` | Mission Control v3 (briefing, power hour, command center) |
| `/properties` | Listing search and management |
| `/properties/<id>` | Listing detail with map, photos, full MLS fields |
| `/contacts` | Contact list with scoring and filtering |
| `/contacts/<id>` | Contact detail with scores, activity, requirements |
| `/pursuits` | Buyer-property pursuit management |
| `/pursuits/<id>` | Pursuit detail with property list and buyer info |
| `/pipeline` | Workflow pipeline (Kanban view) |
| `/actions` | Pending actions dashboard |

---

### public-site
**Status:** Production | **Domain:** wncmountain.homes

Next.js 16 public website with TypeScript, Tailwind CSS, and App Router.

| Page | Purpose |
|------|---------|
| `/` | Homepage with hero search, featured listings, area highlights |
| `/listings` | Property search with filters, sorting, pagination |
| `/listings/[id]` | Listing detail with photo gallery, schema.org JSON-LD |
| `/areas` | Cities and counties with listing counts and price ranges |
| `/about` | About page |
| `/contact` | Contact form |

---

### navica
**Status:** Production

Navica MLS integration (Carolina Smokies AOR) via RESO API.

| Component | Purpose |
|-----------|---------|
| `client.py` | REST API client for Navica endpoints |
| `sync_engine.py` | Full/incremental listing sync with change detection |
| `cron_sync.py` | Cron entry point (4 modes: incremental, nightly, weekly-sold, daily-extras) |
| `field_mapper.py` | RESO field mapping to unified `listings` schema |
| `download_photos.py` | Photo download from CloudFront CDN |

---

### mlsgrid
**Status:** Development (pending credentials)

Canopy MLS integration via MLS Grid OData API.

| Component | Purpose |
|-----------|---------|
| `client.py` | OData-based RESO Web API client |
| `sync_engine.py` | Full/incremental sync (reuses Navica field mapper) |
| `cron_sync.py` | Cron entry point |

**Gating item:** Need `MLSGRID_TOKEN` from data@canopyrealtors.com

---

### fub-to-sheets
**Status:** Production

Follow Up Boss CRM sync to SQLite with lead scoring and daily email reports.

Features:
- Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- Automated daily sync via cron (6 AM)
- Daily email brief with activity stats, priority call list, property changes
- Two-pass reassignment detection
- Behavioral signal processing (intent signals from IDX activity)

---

### property-extension-v3
**Status:** Production | **Version:** 3.9.16

Chrome extension for property capture.

---

### fub-core
**Status:** Library

Shared FUB API SDK used by fub-to-sheets and other FUB integrations.

---

### automation
**Status:** Production

Shared automation infrastructure.

| Component | Purpose |
|-----------|---------|
| `email_service.py` | Jinja2 templated HTML emails |
| `pdf_generator.py` | WeasyPrint HTML-to-PDF generation |

---

## Shared Resources

### shared/
Cross-application resources.

| Path | Purpose |
|------|---------|
| `shared/css/dreams.css` | Design system (colors, components) |
| `shared/js/` | Shared JavaScript |

---

## Infrastructure

### src/
Core library code.

| Path | Purpose |
|------|---------|
| `src/core/database.py` | DREAMSDatabase class (SQLite, all table operations) |
| `src/core/` | Matching engine |
| `src/adapters/` | External system adapters |
| `src/utils/` | Config, logging utilities |

### data/
SQLite database storage (canonical data store).

| File | Purpose |
|------|---------|
| `dreams.db` | Main database (listings, leads, pursuits, events, etc.) |
| `photos/navica/` | Downloaded MLS listing photos (~331 MB) |
| `navica_sync_state.json` | Navica sync cursor |
| `backups/` | Daily database backups |

### deploy/
Production deployment configuration.

| File | Purpose |
|------|---------|
| `systemd/` | Service files for API, dashboard, public site |
| `Caddyfile` | Reverse proxy with SSL |
| `scripts/` | Setup, deploy, backup scripts |

---

## Archived

See `archive/` for deprecated code:
- `pre-navica-2026-02-19/` - Redfin, PropStream, old importers
- property-extension-v1, v2
- property-monitor (retired; Navica handles change detection)

---

*Updated: February 23, 2026*
