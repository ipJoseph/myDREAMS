# Session Continuation Guide

**Last session:** April 20, 2026
**What was completed:** Full codebase audit + all P0 hardening fixes
**Next priority:** P1 items (structural refactor + launch blockers)

## Current State

### Database
- **PostgreSQL** is the sole database on both DEV and PRD
- SQLite archived to `archive/sqlite-2026-04-20/` (not in git)
- DEV: `postgresql://bigeug:dreams_dev@localhost/dreams_dev` (23,688 active listings)
- PRD: `postgresql://dreams:dreams2026prd@localhost/dreams` (28,980 active listings)
- pg_adapter.py provides sqlite3-compatible interface (bridge; scheduled for removal in P1)

### Services (DEV)
- API: systemctl --user restart mydreams-api-dev (:5000)
- Dashboard: systemctl --user restart mydreams-dashboard (:5001)
- Public site: systemctl --user restart mydreams-public-site (:3000)
- All load .env via EnvironmentFile directive

### What P0 Fixed (2026-04-20)
1. Replaced str(e) in 26 HTTP responses with generic error messages
2. Removed time.sleep() blocking calls from 3 route handlers (SQLite retry loops)
3. Added Cache-Control: 1 year immutable on photo serving endpoint
4. Fixed 2 files still using hardcoded sqlite3.connect()
5. Archived 12 orphaned scripts, 2 dead apps, 1 backup file
6. Pinned next-auth to exact version (removed floating beta range)

### Photos
- PRD: 100% photo-ready (28,980/28,980)
- DEV: 86% photo-ready (28,110/32,584), 4,474 missing
- 166 GB on disk at /mnt/dreams-photos (PRD) and data/photos (DEV)

## P1 Work Items (Next Session)

See `docs/TODO.md` items 8-21. Two tracks:

### Track A: Launch Blockers (items 8-14)
Quick wins that should be knocked out first:
- Photo efficiency review (localize_photo per-file stat calls)
- Supabase Auth email test
- Google OAuth end-to-end test
- Favicon per app
- Remove pivot banner from dashboard
- FUB daily sync test
- GitHub Actions CI

### Track B: Structural Refactor (items 15-21)
The big work:
- Split property-dashboard/app.py (8,555 lines) into blueprints
- Decompose DREAMSDatabase (7,318 lines, 163 methods) into service classes
- Standardize get_db() calls
- Add Alembic migrations
- Remove SQLite compatibility layer (use native PostgreSQL)

### Recommended Approach
Start with Track A quick wins to build momentum, then tackle Track B.
For God Class decomposition, start with ContactService (most methods, most referenced).

## Key Files
- Audit report: `docs/audits/20260420.Audit.myDREAMS.md`
- TODO list: `docs/TODO.md`
- Decisions registry: `docs/DECISIONS.md`
- Architecture: `docs/ARCHITECTURE.md`
