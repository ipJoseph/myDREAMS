# Architectural Decisions

Established truths that MUST be respected in all code. If you're about to
write code that contradicts any of these, STOP and discuss with Eugy first.

This file is checked into git. It is the canonical reference for decisions
made during the myDREAMS pivot (April 2026). Claude Code reads this file
and enforces these rules.

---

## Database

### D1: PostgreSQL is the production database (2026-04-18)
- PRD runs PostgreSQL 16 on the same VPS (local Unix socket, zero internet bandwidth)
- DEV may use SQLite for convenience (pg_adapter falls back when DATABASE_URL is unset)
- ALL code must go through `src/core/pg_adapter.get_db()` for connections
- NO raw `sqlite3.connect()` in production code paths
- NO SQLite-specific SQL: no `PRAGMA`, no `AUTOINCREMENT`, no `date('now', ...)`, no `main.` schema prefix
- If you need database-specific behavior, use `pg_adapter.is_postgres()` to branch

### D2: Photos are LOCAL, not CDN (2026-04-18)
- **Canopy MLS (MLS Grid):** CDN tokens EXPIRE. Photos MUST be downloaded to local disk during sync. CDN URLs are NEVER served to the frontend. If a Canopy listing has no local photo, it shows a placeholder until the next sync downloads it.
- **Navica (Carolina Smokies):** CDN URLs are STABLE (CloudFront, no expiring tokens). Navica photos CAN be served from CDN as a fallback when local files don't exist. But local download is still preferred.
- **MountainLakes:** Same as Navica (also Navica-based). Stable CDN.
- Photo storage: `/mnt/dreams-photos/{source}/{mls_number}.jpg` on PRD, `data/photos/{source}/` on DEV
- Photos are NEVER uploaded to Supabase, S3, or any cloud storage. They stay on the VPS local disk.

### D3: Photos download DURING sync, not separately (2026-04-18)
- The sync engine has fresh CDN URLs from the API response
- By the time a separate download cron runs, Canopy CDN tokens are EXPIRED
- Therefore: download primary photo inline after each listing upsert
- Gallery photos can be deferred to a nightly sweep but must use the MLS Grid Media API for fresh URLs, not the expired ones in the database

### D3b: No listing goes live without photos (2026-04-19)
- The `photo_ready` column controls visibility on the public site
- `photo_ready = false` → listing is invisible to users (no placeholder ever shown)
- `photo_ready = true` when photos are downloaded locally OR when `photo_count = 0` (genuinely no photos in MLS)
- The public API enforces this via `AND photo_ready = 1` in all queries where `require_idx = true`
- The dashboard can still see all listings regardless of `photo_ready`
- New listings start as `photo_ready = false` and become visible after photos download

### D4: Identity resolution rules (2026-04-17)
- **Email is the primary identity key.** Always auto-merge on email match.
- **Phone NEVER auto-merges.** Phone match on different emails → flag as potential duplicate for agent review.
- **Agent decides** on duplicates from the dashboard inbox. System never merges automatically on phone alone.
- **Tier A (lead, no password):** Contact form / Request Info. Creates lead in DB + pushes to FUB. No login.
- **Tier B (user, password):** Registration with full account. Enables save/collection features.
- **Tier A → Tier B upgrade:** If a lead's email matches a new registration, the user account links to the existing lead. No duplicate, no data loss.

### D5: FUB integration rules (2026-04-10)
- **DEV does NOT push to FUB.** FUB_API_KEY is blank on DEV. Only PRD talks to FUB.
- **Source field:** All events from our website use `source: "wncmountain.homes"`.
- **System field:** All events use `system: "myDREAMS"`.
- **Events API (POST /v1/events)** is the primary write path to FUB. It auto-creates persons via email/phone dedup.
- **FUB deduplicates on phone internally.** We cannot control this. When testing, use unique phone numbers per test user to avoid FUB-side merging.

### D6: MLS sync contention is solved by PostgreSQL (2026-04-18)
- SQLite's single-writer bottleneck caused form submissions to fail during MLS sync
- PostgreSQL supports concurrent writes; this problem is eliminated
- ALL the SQLite retry/yield patches (commit-every-10, sleep(0.2), 15x1s retries) should be REMOVED once PostgreSQL is stable
- If you see retry logic for "database is locked" — that's legacy SQLite code that should be cleaned up

---

## Code Architecture

### A1: Adapter pattern for vendor integrations (2026-04-10)
- All vendor integrations live in `apps/integrations/<vendor>/`
- Each adapter implements `is_configured()`, `healthcheck()`, and vendor-specific methods
- The conductor (API, dashboard, scoring) talks to adapters, never directly to vendor APIs
- `AdapterResult` is the standard return type (ok, skipped, data, error)

### A2: Photo pipeline must be modular per MLS (2026-04-18)
- Each MLS source has different URL patterns, auth, rate limits, and CDN behavior
- The photo system must handle 3 MLSs today and scale to 6+
- Per-MLS adapter pattern (same as vendor integrations) for photo handling
- See D2 and D3 for per-MLS photo rules

### A3: DEV and PRD are independent environments (2026-04-17)
- DEV writes to local database (SQLite or local PostgreSQL)
- PRD writes to PRD PostgreSQL
- Only PRD pushes to FUB (DEV FUB_API_KEY is blank)
- Photos on PRD: /mnt/dreams-photos/. Photos on DEV: data/photos/
- NEVER overwrite PRD database with DEV database (this corrupted PRD on 2026-04-17)

---

## Operational Rules

### O1: Test on DEV before deploying to PRD (always)
- Build and verify locally before git push + PRD pull
- The deploy guard hook exists for a reason
- PRD is the live website; every deployment is a production change

### O2: Document decisions HERE, not just in conversation (2026-04-18)
- If a decision affects how code should be written, add it to this file
- Claude Code sessions end; this file persists
- Reference this file in code comments where relevant
