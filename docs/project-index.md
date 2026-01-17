# Project Index

This file tracks all active applications and components in myDREAMS.

## How to use
- One section per app/component
- Keep this high-level and current
- Link out to deeper docs as needed

---

## Platform: myDREAMS

**Desktop Real Estate Agent Management System**

Status: **Production (v1.1)**
Owner: Joseph Williams
Last Updated: January 17, 2026

### Purpose
Local-first platform for real estate agents to capture properties, manage leads, and automate client workflows.

### Documentation
- [Architecture](ARCHITECTURE.md) - System design, data flow
- [Roadmap](ROADMAP.md) - Phases and progress
- [Changelog](../CHANGELOG.md) - Version history

---

## Active Applications

### property-api
**Status:** Production | **Port:** 5000

Flask REST API - receives scraped property data, syncs to Notion.

| Endpoint | Purpose |
|----------|---------|
| `POST /property` | Receive scraped property |
| `GET /properties` | List all properties |
| `POST /api/idx-portfolio` | Launch IDX automation |
| `POST /api/validate-idx` | Validate MLS numbers |

---

### property-dashboard
**Status:** Production | **Port:** 5001

Flask web UI for viewing and managing properties.

| Route | Purpose |
|-------|---------|
| `/` | Main dashboard with filters, metrics |
| `/lead/<name>` | Client-facing property view |

---

### property-extension-v3
**Status:** Production | **Version:** 3.9.16

Chrome extension for scraping property sites.

Supported sites:
- Zillow
- Redfin
- Realtor.com

---

### property-monitor
**Status:** Active

Playwright-based monitoring for price/status changes on tracked properties.

---

### fub-to-sheets
**Status:** Production

Follow Up Boss CRM to Google Sheets sync with lead scoring.

Features:
- Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- Automated daily sync via cron
- Stage-based filtering

---

### fub-core
**Status:** Library

Shared FUB API SDK used by fub-to-sheets and other FUB integrations.

---

### fub-dashboard-appsscript
**Status:** Production

Google Apps Script for lead dashboard visualization in Sheets.

---

### vendor-directory
**Status:** MVP

SQLite-based vendor/contractor management.

Commands:
- `add-vendor` - Add new vendor
- `list-vendors` - List all vendors
- `export` - Export to CSV

---

## Shared Resources

### shared/
Cross-application resources.

| Path | Purpose |
|------|---------|
| `shared/css/dreams.css` | Design system (colors, components) |
| `shared/js/` | Future shared JavaScript |

---

## Infrastructure

### src/
Core library code.

| Path | Purpose |
|------|---------|
| `src/core/` | Database, matching engine |
| `src/adapters/` | External system adapters |
| `src/utils/` | Config, logging utilities |

### data/
SQLite database storage (canonical data store).

### config/
Configuration files.

### scripts/
Operational scripts for maintenance and deployment.

---

## Archived

See `archive/` for deprecated code:
- property-extension-v1
- property-extension-v2
- testscaper

---

*Updated: January 17, 2026*
