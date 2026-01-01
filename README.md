# myDREAMS
**my Desktop Real Estate Agent Management System**

A comprehensive, desktop-optimized system for managing real estate operations with Follow Up Boss integration, automated lead scoring, and daily reporting.

## What is myDREAMS?

**myDREAMS** is a production-grade real estate agent management platform designed for:
- 🎯 **Automated Lead Scoring** - Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- 📊 **Google Sheets Integration** - Real-time dashboards and data visualization
- 📧 **Daily Email Reports** - Automated priority contact lists
- 🔄 **Follow Up Boss Sync** - Seamless CRM integration
- 💾 **Automated Backups** - Secure Google Drive backup system
- 🖥️ **Desktop-First** - Optimized for Ubuntu/Linux desktop workflows

## Quick Start

### 1. Restore Secrets (First Time Setup)
```bash
./scripts/restore-secrets.sh
```

### 2. Set Up Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/fub-to-sheets/requirements.txt
```

### 3. Run the System
```bash
cd apps/fub-to-sheets
python fub_to_sheets_v2.py
```

### 4. Backup Your Secrets
```bash
./scripts/backup-secrets.sh
```

## Architecture
```
myDREAMS/
├── apps/
│   ├── fub-to-sheets/       # Main automation engine
│   ├── fub-core/            # Reusable FUB API library
│   └── fub-dashboard/       # Google Sheets dashboard UI
├── scripts/
│   ├── backup-secrets.sh    # Automated backup to Google Drive
│   └── restore-secrets.sh   # Easy secret recovery
├── docs/                    # Documentation and decisions
├── .venv/                   # Python virtual environment
├── .env                     # Secrets (git-ignored)
└── service_account.json     # Google API credentials (git-ignored)
```

## Features

### Lead Scoring System
- **Heat Score**: Website visits, property views, calls, texts
- **Value Score**: Transaction potential and relationship worth
- **Relationship Score**: Engagement strength and connection quality
- **Priority Score**: Weighted composite for daily call lists

### Automation
- Daily automated sync with Follow Up Boss
- Real-time Google Sheets updates
- Email notifications with priority contacts
- Cron job integration for hands-free operation

### Data Security
- Automated encrypted backups to Google Drive
- Version history with timestamps
- Easy restore for disaster recovery
- Git-ignored secrets management

## Documentation

See `docs/` directory for:
- Architecture decisions
- Scoring methodology
- Runbooks and troubleshooting
- Enhancement guides

## Author

**Joseph "Eugy" Williams**  
Real Estate Agent | Developer  
Keller Williams - Jon Tharp Homes  
Integrity Pursuits LLC

---

*Built for world-class real estate operations on Ubuntu/Linux desktop environments*
