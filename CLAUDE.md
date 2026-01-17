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

## Owner

Joseph "Eugy" Williams
Keller Williams - Jon Tharp Homes
