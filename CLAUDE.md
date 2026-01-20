# Claude Context for myDREAMS

Instructions and context for Claude Code sessions on this project.

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
