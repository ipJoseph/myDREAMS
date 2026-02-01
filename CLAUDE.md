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
| property-api | 5000 | REST API for property data |
| property-dashboard | 5001 | Web UI for properties |
| property-extension-v3 | - | Chrome extension (current) |
| fub-to-sheets | - | CRM to Sheets sync |

### Important Paths
- Database: `data/` (SQLite)
- Secrets: `.env` (git-ignored)
- Shared CSS: `shared/css/dreams.css`
- Archive: `archive/` (deprecated code)

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design
- [Roadmap](docs/ROADMAP.md) - Progress tracking
- [Changelog](CHANGELOG.md) - Version history
- [Project Index](docs/project-index.md) - All apps
- **[TODO List](docs/TODO.md)** - Master task list (29 items, prioritized) - CHECK THIS AT SESSION START

## Conventions

- Commit messages: Short summary, bullet details if needed
- Design system: Use `shared/css/dreams.css` for new UIs
- Tech debt: Track in ROADMAP.md "Known Issues" section
- Versioning: Update CHANGELOG.md when shipping features

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

### Sync Database (DEV to PRD)
```bash
scp /home/bigeug/myDREAMS/data/dreams.db root@178.156.221.10:/opt/mydreams/data/dreams.db
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
