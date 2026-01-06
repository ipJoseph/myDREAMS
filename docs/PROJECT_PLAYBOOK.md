# DREAMS Platform Project Playbook

**Desktop Real Estate Agent Management System**

*Version 1.0 | January 2026*

---

## Executive Vision

DREAMS transforms real estate operations from manual, fragmented workflows into an intelligent, automated system that matches buyers to properties and generates professional packages with minimal human intervention.

**The core insight:** Real estate agents spend 60-70% of their time on data gathering, property research, and package preparation. DREAMS reduces this to 10-20%, freeing agents to focus on relationships and closings.

**The key principle:** CRM independence through a canonical data layer. The system works with any CRM, any MLS, any presentation tool—adapters connect external systems to a portable, reliable core.

---

## Platform Architecture

### The Hexagonal Model

```
                    ┌─────────────────────────────────────┐
                    │         PRESENTATION LAYER          │
                    │   Notion | Airtable | Sheets | CLI  │
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │            CORE DOMAIN              │
                    │                                     │
                    │  ┌─────────┐  ┌─────────┐          │
                    │  │  Leads  │──│Properties│          │
                    │  └────┬────┘  └────┬────┘          │
                    │       │            │               │
                    │       └─────┬──────┘               │
                    │             │                      │
                    │       ┌─────▼─────┐                │
                    │       │  Matches  │                │
                    │       └─────┬─────┘                │
                    │             │                      │
                    │       ┌─────▼─────┐                │
                    │       │ Packages  │                │
                    │       └───────────┘                │
                    │                                     │
                    │         SQLite (Canonical)          │
                    └──────────────────┬──────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
    ┌─────▼─────┐               ┌──────▼─────┐              ┌───────▼──────┐
    │   CRM     │               │  PROPERTY  │              │   OUTPUT     │
    │ ADAPTERS  │               │  ADAPTERS  │              │  ADAPTERS    │
    ├───────────┤               ├────────────┤              ├──────────────┤
    │FollowUpBoss│              │ Zillow     │              │ PDF Generator│
    │ Salesforce │              │ Realtor.com│              │ Email        │
    │ Sierra     │              │ MLS APIs   │              │ SMS          │
    │ KW Command │              │ IDX/RealGeeks│            │ Print        │
    │ Pipeliner  │              │ ScraperAPI │              │              │
    └───────────┘               └────────────┘              └──────────────┘
```

### Four Pillars

| Pillar | Purpose | Status |
|--------|---------|--------|
| **1. Lead Intelligence** | Understand who to contact, when, and why | ✅ Operational |
| **2. Property Research** | Capture, monitor, and organize inventory | ✅ Operational |
| **3. Buyer-Property Matching** | Predictive matching based on behavior + stated preferences | 🔄 In Development |
| **4. Package Generation** | One-click showing packages and client communications | ⬜ Planned |

---

## Components Inventory

### Completed Components

#### 1. FUB-to-Sheets Lead Sync
**Location:** `myDREAMS/` repository  
**Function:** Syncs Follow Up Boss contacts to Google Sheets twice daily  
**Benefits:**
- Centralized lead visibility
- Multi-dimensional scoring (Heat, Value, Relationship, Priority)
- Daily prioritized call lists via email
- Foundation for behavioral analysis

**Project Contribution:** Pillar 1 (Lead Intelligence) - Core

#### 2. Chrome Extension Property Scraper
**Location:** `myDREAMS/` repository  
**Function:** Captures property data from Zillow listings  
**Benefits:**
- Rapid property capture (seconds vs. manual entry)
- Extracts: price, beds, baths, sqft, acreage, MLS#, parcel ID
- Direct integration with property database
- Eliminates copy-paste workflows

**Project Contribution:** Pillar 2 (Property Research) - Data Capture

#### 3. Property Monitoring System
**Location:** `myDREAMS/` repository  
**Function:** Automated daily monitoring of tracked properties via ScraperAPI  
**Benefits:**
- Price change detection
- Status change alerts (Active → Pending → Sold)
- DOM tracking
- Market intelligence over time

**Project Contribution:** Pillar 2 (Property Research) - Monitoring

#### 4. Notion Property Database
**Location:** Notion workspace  
**Function:** Property inventory with structured schema  
**Benefits:**
- User-friendly interface for Dolores
- Relational structure (properties ↔ leads)
- Views for different workflows
- Export capability

**Project Contribution:** Pillar 2 (Property Research) - Presentation Layer

### In-Development Components

#### 5. Buyer Requirements Extraction
**Status:** Design phase  
**Function:** Extract buyer preferences from FUB activities and stated requirements  
**Target Benefits:**
- Automated preference inference from saves, favorites, searches
- Weighted scoring of stated vs. demonstrated preferences
- Real-time updates via webhooks or polling

**Project Contribution:** Pillar 3 (Matching) - Input Layer

#### 6. Property Matching Engine
**Status:** Design phase  
**Function:** Score and rank properties against buyer requirements  
**Target Benefits:**
- Multi-dimensional matching algorithm
- Behavioral signal weighting
- Ranked recommendations per buyer
- Match confidence scoring

**Project Contribution:** Pillar 3 (Matching) - Core Logic

### Planned Components

#### 7. SQLite Canonical Database
**Status:** Planned  
**Function:** Single source of truth for all DREAMS data  
**Target Benefits:**
- CRM independence
- Offline capability
- Query power (SQL joins)
- Portability

**Project Contribution:** Core Infrastructure

#### 8. CRM Adapter Framework
**Status:** Planned  
**Function:** Standardized interface for CRM integrations  
**Target Benefits:**
- Swap CRMs without changing core logic
- Support multiple CRMs simultaneously
- Plugin architecture for new integrations

**Project Contribution:** Core Infrastructure

#### 9. Package Generator
**Status:** Planned  
**Function:** Automated showing package creation  
**Target Benefits:**
- One-command package generation
- Branded templates
- Multi-property compilations
- PDF/email output

**Project Contribution:** Pillar 4 (Package Generation)

---

## Implementation Roadmap

### Phase 1: Foundation Hardening (Weeks 1-2)

**Objective:** Establish SQLite as canonical store, migrate existing data

| Task | Deliverable | Est. Hours |
|------|-------------|------------|
| Design canonical schema | `schema.sql` | 4 |
| Create SQLite database | `dreams.db` | 2 |
| Build FUB adapter (extract from existing sync) | `adapters/fub_adapter.py` | 6 |
| Build Notion adapter (read/write) | `adapters/notion_adapter.py` | 8 |
| Migrate lead data | Data in SQLite | 4 |
| Migrate property data | Data in SQLite | 4 |
| Update cron jobs to use new architecture | Working sync | 4 |

**Total: ~32 hours**

### Phase 2: Matching Engine (Weeks 3-4)

**Objective:** Build buyer-property matching with behavioral signals

| Task | Deliverable | Est. Hours |
|------|-------------|------------|
| Design buyer requirements schema | Schema update | 2 |
| Build FUB activity monitor | `core/activity_monitor.py` | 8 |
| Build preference inference logic | `core/preference_engine.py` | 8 |
| Build matching algorithm | `core/matching_engine.py` | 10 |
| Test with 10 real buyers | Validation report | 6 |
| Iterate based on Dolores feedback | Refined algorithm | 6 |

**Total: ~40 hours**

### Phase 3: Package Generation (Weeks 5-6)

**Objective:** Automated showing package creation

| Task | Deliverable | Est. Hours |
|------|-------------|------------|
| Design package template (HTML/CSS) | `templates/showing_package.html` | 6 |
| Build PDF generator | `core/package_generator.py` | 10 |
| Integrate property photos | Photo handling | 6 |
| Build CLI interface | `scripts/generate_package.py` | 4 |
| Test with real showings | Production packages | 6 |

**Total: ~32 hours**

### Phase 4: Scale & Polish (Weeks 7-8)

**Objective:** Production hardening, documentation, team rollout

| Task | Deliverable | Est. Hours |
|------|-------------|------------|
| Error handling & logging | Robust system | 8 |
| User documentation | Dolores can train others | 8 |
| Additional CRM adapter (Sierra or Salesforce) | Second adapter | 12 |
| Performance optimization | Fast queries | 6 |
| Jon Tharp team pilot | Team adoption | 8 |

**Total: ~42 hours**

---

## Technology Stack

### Core
- **Language:** Python 3.11+
- **Database:** SQLite 3 (WAL mode)
- **Task Scheduling:** cron (Linux) / Task Scheduler (Windows)

### Integrations
- **CRM:** Follow Up Boss API (primary), extensible to others
- **Property Data:** ScraperAPI, Chrome extension, future MLS APIs
- **Presentation:** Notion API, Google Sheets API, Airtable API

### Output
- **PDF Generation:** WeasyPrint or ReportLab
- **Email:** Gmail API or SMTP
- **Templates:** Jinja2 + HTML/CSS

### Development
- **Version Control:** Git + GitHub
- **Backup:** rclone to Google Drive
- **Environment:** Python venv

---

## Repository Structure

```
dreams-platform/
├── README.md
├── requirements.txt
├── setup.py
├── .gitignore
│
├── docs/
│   ├── PROJECT_PLAYBOOK.md      # This document
│   ├── ARCHITECTURE.md          # Technical architecture details
│   ├── ROADMAP.md              # Detailed timeline
│   ├── USER_GUIDE.md           # End-user documentation
│   └── API_REFERENCE.md        # Adapter interface specs
│
├── src/
│   ├── __init__.py
│   │
│   ├── adapters/               # External system integrations
│   │   ├── __init__.py
│   │   ├── base_adapter.py     # Abstract interfaces
│   │   ├── fub_adapter.py      # Follow Up Boss
│   │   ├── notion_adapter.py   # Notion
│   │   ├── sheets_adapter.py   # Google Sheets
│   │   └── zillow_adapter.py   # Zillow scraping
│   │
│   ├── core/                   # Business logic
│   │   ├── __init__.py
│   │   ├── database.py         # SQLite operations
│   │   ├── lead_scoring.py     # Multi-dimensional scoring
│   │   ├── activity_monitor.py # Behavioral tracking
│   │   ├── preference_engine.py # Preference inference
│   │   ├── matching_engine.py  # Buyer-property matching
│   │   └── package_generator.py # Showing packages
│   │
│   ├── presentation/           # Output formatting
│   │   ├── __init__.py
│   │   ├── pdf_builder.py
│   │   ├── email_builder.py
│   │   └── report_builder.py
│   │
│   └── utils/                  # Shared utilities
│       ├── __init__.py
│       ├── config.py
│       ├── logging.py
│       └── helpers.py
│
├── scripts/                    # CLI tools
│   ├── sync_leads.py
│   ├── sync_properties.py
│   ├── generate_matches.py
│   ├── generate_package.py
│   └── daily_report.py
│
├── templates/                  # Output templates
│   ├── showing_package.html
│   ├── property_card.html
│   ├── email_template.html
│   └── styles.css
│
├── data/                       # Local data (gitignored)
│   ├── dreams.db              # SQLite database
│   └── backups/
│
├── tests/                      # Test suite
│   ├── test_adapters/
│   ├── test_core/
│   └── test_integration/
│
└── config/                     # Configuration
    ├── config.example.yaml
    └── .env.example
```

---

## Success Metrics

### Operational Efficiency
- Property research time: 2-3 hours → 20-30 minutes (target: 85% reduction)
- Package creation time: 45 minutes → 5 minutes (target: 90% reduction)
- Lead follow-up consistency: 60% → 95% (target: contact every qualified lead)

### Business Impact
- Showings per week: Increase by 50%
- Time to first showing: Reduce by 40%
- Dolores capacity: Handle 2-3x more leads

### Technical Health
- System uptime: 99%+
- Sync reliability: Zero missed syncs
- Data accuracy: 100% match between CRM and DREAMS

---

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-03 | SQLite as canonical database | Portability, simplicity, cost, adequate performance |
| 2026-01-03 | CRM independence via adapters | Future-proofing, marketability, consulting opportunities |
| 2026-01-03 | Notion as presentation layer (not database) | User-friendly but swappable; SQLite holds truth |
| 2026-01-03 | Behavioral signals weighted over stated preferences | Actions reveal true preferences better than words |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| API rate limits (FUB, Notion, Zillow) | Sync delays | Batch operations, caching, exponential backoff |
| Zillow blocking scraping | Property data loss | ScraperAPI rotation, multiple sources, MLS direct |
| Schema changes in source systems | Data corruption | Version detection, graceful degradation |
| Single point of failure (SQLite file) | Data loss | Automated backups via rclone (already implemented) |
| Dolores finds system too complex | Adoption failure | Design for her workflow first, iterate based on feedback |

---

## Team & Responsibilities

| Person | Role | Primary Responsibilities |
|--------|------|--------------------------|
| Joseph | Architect & Developer | System design, code, integrations |
| Dolores | Operations & QA | Daily usage, feedback, workflow validation |
| Jon Tharp | Sponsor & Pilot User | Team adoption, business requirements |
| Claude | Technical Partner | Architecture guidance, code review, documentation |

---

## Appendix: Existing myDREAMS Repository

The current `myDREAMS` repository contains proven components that will be integrated into the DREAMS platform:

- **Lead sync scripts** — Refactor into FUB adapter
- **Chrome extension** — Integrate with property adapter
- **Monitoring system** — Incorporate into property tracking
- **Google Sheets integration** — Refactor into Sheets adapter

**Recommendation:** Expand `myDREAMS` repository to become `DREAMS platform` rather than creating separate repo. This maintains Git history and existing integrations while evolving the architecture.

---

*Document maintained by Joseph & Claude*  
*Last updated: January 3, 2026*
