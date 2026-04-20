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

## Track B Progress (items 15-21)

| # | Task | State |
|---|------|-------|
| 15 | Blueprint split | In progress — pattern established (blueprints/__init__.py deps container + blueprints/expenses.py, 14 routes). Monolith 8,555 → 8,153 |
| 16 | DREAMSDatabase decomposition | In progress — pattern established (src/core/services/contact_service.py, 4 methods). Back-compat delegators keep old callers working |
| 17 | Standardize get_db() | Done — 5 raw sqlite3.connect sites routed through pg_adapter |
| 18 | Alembic migrations | Done — DEV stamped at baseline 28957ed21753. **PRD still needs `alembic stamp head` once** |
| 19 | Sentry error monitoring | Done — wired into both Flask apps as no-op until SENTRY_DSN is set |
| 20 | Move route-level raw SQL into services | Pending — waits for more service coverage |
| 21 | Remove pg_adapter bridge | Pending — final step once every caller is on native psycopg2 |

## Incremental work for future sessions

#15 and #16 are long-tail refactors rather than single-turn items. The
patterns are in place; subsequent sessions just keep chipping away:

**Extract another blueprint (#15):** pick a cohesive slice of routes
(e.g. `/pursuits/*`, `/api/power-hour/*`, `/admin/*`, `/contacts/*`) and
replicate the expenses model — move routes + helpers + constants into a
new file under `blueprints/`, register it after the deps are populated.

**Extract another service (#16):** pick a cluster of DREAMSDatabase
methods that share a table (pursuits, activities, workflow, assignments,
communications, events, analytics) and move them into a new
`src/core/services/*_service.py`. Keep the old DREAMSDatabase method
names as thin delegators during the transition.

**#20 becomes easy** once #15 and #16 progress — each blueprint should
call services, not raw SQL. Audit the blueprint files after each
extraction and convert any inline SQL to a service call.

**#21 is gated on #20** being complete across the codebase.

## Key Files
- Audit report: `docs/audits/20260420.Audit.myDREAMS.md`
- TODO list: `docs/TODO.md`
- Architecture: `docs/ARCHITECTURE.md`
- CI workflow: `.github/workflows/ci.yml`
