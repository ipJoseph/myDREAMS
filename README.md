# myDREAMS
**my Desktop Real Estate Agent Management System**

A local-first platform for real estate agents to manage MLS listings, score leads, track buyer pursuits, and automate client workflows.

## What is myDREAMS?

**myDREAMS** is a production-grade real estate platform with:
- **MLS Integration** - Direct Navica API feed from Carolina Smokies MLS (1,589+ listings)
- **Lead Scoring** - Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- **Mission Control** - Intelligence Briefing, Power Hour calling, Command Center dashboard
- **Public Website** - IDX-compliant property search at wncmountain.homes
- **Buyer Pursuits** - Track buyer-property portfolios with auto-matching
- **Daily Reports** - Automated priority contact lists and activity digests
- **CRM Sync** - Follow Up Boss integration with behavioral signal processing

## Quick Start

### 1. Start the Property API
```bash
cd apps/property-api
python3 app.py
# Runs on http://localhost:5000
```

### 2. Start the Dashboard
```bash
cd apps/property-dashboard
python3 app.py
# Runs on http://localhost:5001
```

### 3. Start the Public Site
```bash
cd apps/public-site
npx next dev
# Runs on http://localhost:3000
```

## System Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Navica MLS  │────>│  Sync Engine │────>│   SQLite     │
│  (RESO API)  │     │  + Field Map │     │  (listings)  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          v                      v                      v
                   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
                   │  Dashboard   │     │  Public Site │     │  Property    │
                   │  (Mission    │     │  (Next.js)   │     │  API         │
                   │   Control)   │     │  :3000       │     │  :5000       │
                   │  :5001       │     └──────────────┘     └──────────────┘
                   └──────────────┘
                          ^
                          │
┌──────────────┐     ┌──────────────┐
│ Follow Up    │────>│  FUB Sync    │
│ Boss (CRM)   │     │  + Scoring   │
└──────────────┘     └──────────────┘
```

## Applications

| App | Port | Purpose |
|-----|------|---------|
| `property-api` | 5000 | REST API for property data and public IDX endpoints |
| `property-dashboard` | 5001 | Mission Control: briefing, calling, property management |
| `public-site` | 3000 | Public website at wncmountain.homes (Next.js) |
| `navica` | - | MLS listing sync from Carolina Smokies (RESO API) |
| `mlsgrid` | - | Canopy MLS integration (pending credentials) |
| `fub-to-sheets` | - | Follow Up Boss CRM sync with lead scoring |
| `property-extension-v3` | - | Chrome extension for property capture |

## Architecture

```
myDREAMS/
├── apps/
│   ├── property-api/           # Flask REST API (port 5000)
│   ├── property-dashboard/     # Mission Control dashboard (port 5001)
│   ├── public-site/            # Next.js public website
│   ├── navica/                 # Navica MLS sync engine
│   ├── mlsgrid/                # Canopy MLS integration
│   ├── fub-to-sheets/          # FUB CRM sync + scoring
│   ├── automation/             # Email service, PDF generation
│   ├── property-extension-v3/  # Chrome extension
│   └── fub-core/               # FUB API SDK library
├── src/
│   ├── core/                   # Database, matching engine
│   ├── adapters/               # External system adapters
│   └── utils/                  # Config, logging utilities
├── data/                       # SQLite database + photos
├── shared/css/                 # Design system (dreams.css)
├── deploy/                     # Systemd, Caddy, scripts
├── docs/                       # Documentation
└── .env                        # Secrets (git-ignored)
```

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - System design, data flow, integrations
- **[Roadmap](docs/ROADMAP.md)** - Current status, phases, what's next
- **[Project Index](docs/project-index.md)** - All apps and components
- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[TODO](docs/TODO.md)** - Master task list
- **[CLAUDE.md](CLAUDE.md)** - AI assistant context

## Environment Variables

```bash
# Core
DREAMS_ENV=dev                          # dev or prd
FLASK_DEBUG=false

# Authentication
DREAMS_API_KEY=xxx                      # X-API-Key header
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=xxx

# Follow Up Boss (CRM)
FUB_API_KEY=xxx

# Navica MLS
NAVICA_API_TOKEN=xxx

# Google
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
GOOGLE_SPREADSHEET_ID=xxx
GOOGLE_MAPS_API_KEY=xxx

# Email Reports
SMTP_SERVER=smtp.gmail.com
SMTP_USERNAME=xxx
SMTP_PASSWORD=xxx
EMAIL_RECIPIENT=xxx
```

## Lead Scoring System

| Score | Description |
|-------|-------------|
| **Heat** | Website visits, property views, calls, texts |
| **Value** | Transaction potential and relationship worth |
| **Relationship** | Engagement strength and connection quality |
| **Priority** | Weighted composite for daily call lists |

## Production

| Environment | URL | Host |
|------------|-----|------|
| Dashboard | https://app.wncmountain.homes | Hetzner VPS |
| Public Site | https://wncmountain.homes | Hetzner VPS |
| API | https://api.wncmountain.homes | Hetzner VPS |

## Author

**Joseph "Eugy" Williams**
Real Estate Agent | Developer
Keller Williams - Jon Tharp Homes
Integrity Pursuits LLC

---

*Built for world-class real estate operations*
