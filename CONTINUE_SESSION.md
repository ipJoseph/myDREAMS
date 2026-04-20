# Session Continuation Guide

**Last session:** April 20, 2026 (continuation)
**What was completed:** All of Track A (P1 items 8-14). Track B is next.

## Current State

### Database
- **PostgreSQL** is the sole database on both DEV and PRD
- SQLite archived to `archive/sqlite-2026-04-20/` (not in git, not in history — filter-repo'd out)
- DEV: `postgresql://bigeug:dreams_dev@localhost/dreams_dev` (23,688 active listings)
- PRD: `postgresql://dreams:dreams2026prd@localhost/dreams` (28,980 active listings)
- pg_adapter.py provides sqlite3-compatible interface (bridge; scheduled for removal in Track B #21)

### Services (DEV)
- API: systemctl --user restart mydreams-api-dev (:5000)
- Dashboard: systemctl --user restart mydreams-dashboard (:5001)
- Public site: systemctl --user restart mydreams-public-site (:3000)
- All load .env via EnvironmentFile directive

### Photos
- PRD: 100% photo-ready (28,980/28,980)
- DEV: 86% photo-ready (28,110/32,584), 4,474 missing
- 166 GB on disk at /mnt/dreams-photos (PRD) and data/photos (DEV)

## Track A Progress (items 8-14 — all shipped)

| # | Task | State |
|---|------|-------|
| 8 | Photo architecture efficiency review | Done — hot path fixed (dir-scan cache); race conditions + sold-photo cleanup deferred |
| 9 | Supabase Auth email confirmation test | BROKEN — Supabase returns 500 "Error sending confirmation email". See "Operational issues" below |
| 10 | Google OAuth end-to-end test | Infra OK (Supabase → Google redirect works); needs manual browser click-through to confirm session exchange |
| 11 | Distinct favicons per app | Done — dashboard now uses mountain silhouette, public-site keeps the house |
| 12 | Remove frozen-data pivot banner | Done — 4 template includes + partial deleted |
| 13 | FUB daily sync test | Done — ported 3 SQLite-only code paths to PG. Sync now runs cleanly end-to-end |
| 14 | GitHub Actions CI | Done — pytest + ruff + next build on push. See `.github/workflows/ci.yml` |

## Operational issues surfaced during Track A (for Eugy)

These are NOT code bugs but credential/config issues that need human action:

1. **Gmail app password expired** (appears in two places)
   - FUB daily sync email report: `SMTP_PASSWORD=fpxjskkzykvyyikc` in `.env` fails with
     `535 5.7.8 BadCredentials` when sending the daily top-priority report to
     `joseph@integritypursuits.com`.
   - Supabase Auth email: `signUp` returns 500 "Error sending confirmation email"
     from `https://skoavtsqckyipqxayjog.supabase.co`. Likely the same cause if
     Supabase is using custom SMTP with the same Gmail app password.
   - Fix: generate a fresh Gmail app password, update `.env` AND Supabase
     Dashboard → Authentication → Settings → SMTP Settings.

2. **FUB API keys were committed to local git**
   - `config/myDREAMS API Keys` plaintext file containing two FUB keys
     (`fka_18idAqt6q0Ks...` and `fka_18idAqAdYOl...`) landed in local commit
     802f3ee from the previous session. Never pushed — filter-repo stripped it
     out before the push.
   - Backup at `~/secrets-fub-api-keys.txt` (outside repo).
   - `.gitignore` now covers `config/*API Keys*` to prevent re-add.
   - **Strongly recommend rotating both keys** — anything that lived in a local
     git object should be treated as potentially leaked.

3. **Google OAuth redirect URI**
   - When manually testing, confirm `https://wncmountain.homes/auth/callback`
     (and its `app.wncmountain.homes` equivalent, if distinct) are registered
     as authorized redirect URIs in Google Cloud Console OAuth client
     `464039217231-lcbr0i0hq57kupnhtinclrsel9gq63up.apps.googleusercontent.com`.

## Track B: Structural Refactor (next)

See `docs/TODO.md` items 15-21:
- #15 Split property-dashboard/app.py (8,555 lines) into blueprints
- #16 Decompose DREAMSDatabase (7,318 lines, 163 methods) into service classes
- #17 Standardize all get_db() calls (10 implementations → 1)
- #18 Add Alembic for database migrations
- #19 Add Sentry for error monitoring
- #20 Move route-level raw SQL into service methods
- #21 Remove SQLite compatibility layer (use native PostgreSQL)

### Recommended order
1. #17 first — standardising on pg_adapter's `get_db()` is prerequisite for
   every other refactor. Small, mechanical, low risk.
2. #16 next — start with ContactService (most methods, most referenced).
   Peel slice by slice so the god class shrinks incrementally.
3. #15 after that — route handlers move to blueprints once the service layer
   they call into is stable.
4. #18 (Alembic) is independent and can be done any time before #21.
5. #21 last — removing pg_adapter means every call site is already using
   native PG, which flows naturally from #17 + #16 + #20.

## Key Files
- Audit report: `docs/audits/20260420.Audit.myDREAMS.md`
- TODO list: `docs/TODO.md`
- Architecture: `docs/ARCHITECTURE.md`
- CI workflow: `.github/workflows/ci.yml`
