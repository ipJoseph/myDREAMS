# myDREAMS
**my Desktop Real Estate Agent Management System**

A local-first platform for real estate agents to capture properties, manage leads, and automate client workflows.

## What is myDREAMS?

**myDREAMS** is a production-grade real estate platform with:
- 🏠 **Property Capture** - Chrome extension scrapes Zillow, Redfin, Realtor.com
- 🎯 **Lead Scoring** - Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- 📊 **Dashboards** - Property dashboard + Google Sheets lead reports
- 🔄 **IDX Integration** - Automatic MLS validation and portfolio creation
- 📧 **Daily Reports** - Automated priority contact lists
- 🔗 **CRM Sync** - Follow Up Boss + Notion integration
- 🖥️ **Desktop-First** - Optimized for Ubuntu/Linux workflows

## Quick Start

### 1. Start the Property API
```bash
cd apps/property-api
source venv/bin/activate
python app.py
# Runs on http://localhost:5000
```

### 2. Install Chrome Extension
1. Open `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `apps/property-extension-v3`

### 3. Start the Dashboard
```bash
cd apps/property-dashboard
source ../property-api/venv/bin/activate
python app.py
# Runs on http://localhost:5001
```

## System Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Chrome Ext     │────▶│  Property API   │────▶│    SQLite       │
│  (v3.9.16)      │     │  (Flask:5000)   │     │  (Canonical)    │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                │                        │
                        ┌───────┴───────┐                │
                        ▼               ▼                ▼
                ┌───────────┐   ┌───────────┐   ┌───────────────┐
                │  Notion   │   │ IDX Site  │   │  Dashboard    │
                │  Sync     │   │ Validate  │   │  (Flask:5001) │
                └───────────┘   └───────────┘   └───────────────┘
```

## Applications

| App | Port | Purpose |
|-----|------|---------|
| `property-api` | 5000 | REST API - receives scraped data, syncs to Notion |
| `property-dashboard` | 5001 | Web UI - view properties, create IDX portfolios |
| `property-extension-v3` | - | Chrome extension - scrape property sites |
| `fub-to-sheets` | - | Follow Up Boss CRM to Google Sheets sync |
| `property-monitor` | - | Monitor price/status changes via Playwright |

## Architecture

```
myDREAMS/
├── apps/
│   ├── property-api/           # Flask REST API (port 5000)
│   ├── property-dashboard/     # Flask web dashboard (port 5001)
│   ├── property-extension-v3/  # Chrome extension (current)
│   ├── property-monitor/       # Playwright-based monitoring
│   ├── fub-to-sheets/          # FUB CRM automation
│   └── fub-core/               # FUB API SDK library
├── src/
│   ├── core/                   # Database, matching engine
│   ├── adapters/               # External system adapters
│   └── utils/                  # Config, logging utilities
├── scripts/                    # Operational scripts
├── docs/                       # Documentation
├── data/                       # SQLite database
└── .env                        # Secrets (git-ignored)
```

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - System design, data flow, integrations
- **[Roadmap](docs/ROADMAP.md)** - Current status, phases, what's next
- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[CLAUDE.md](CLAUDE.md)** - AI assistant context

## Environment Variables

```bash
# Required for Property System
NOTION_API_KEY=secret_xxx
NOTION_PROPERTIES_DB_ID=xxx

# Required for Lead System
FUB_API_KEY=xxx
GOOGLE_SHEET_ID=xxx
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json

# Optional - IDX Integration
IDX_EMAIL=xxx
IDX_PHONE=xxx

# Optional - Monitoring
USE_PROXY=false
```

## Lead Scoring System

| Score | Description |
|-------|-------------|
| **Heat** | Website visits, property views, calls, texts |
| **Value** | Transaction potential and relationship worth |
| **Relationship** | Engagement strength and connection quality |
| **Priority** | Weighted composite for daily call lists |

## Author

**Joseph "Eugy" Williams**
Real Estate Agent | Developer
Keller Williams - Jon Tharp Homes
Integrity Pursuits LLC

---

*Built for world-class real estate operations on Ubuntu/Linux desktop environments*
