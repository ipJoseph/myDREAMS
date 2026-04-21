# Incident: Navica Feed Silent Stop (2026-03-25 through 2026-04-21)

**Status:** Diagnosed, fix pending
**Discovered:** 2026-04-21 during photo-UX investigation
**Duration before detection:** 27 days
**Impact:** Two of three MLS sources stopped ingesting new listings. Active inventory from Navica + Mountain Lakes became stale "residue" of what was active on 2026-03-25.

## Impact

| Source | Adapter | Last capture | New listings last 30d (as of 2026-04-21) |
|---|---|---|---|
| CanopyMLS | `apps/mlsgrid/` | ongoing | 7,377 |
| MountainLakesMLS | `apps/navica/` (nav26) | 2026-03-25 17:18 UTC | 3 |
| NavicaMLS / Carolina Smokies | `apps/navica/` (nav27) | 2026-03-25 17:20 UTC | 12 |

The "89 / 78 active" counts visible in April 2026 are not a real current inventory snapshot. They are the residue of what happened to be `ACTIVE` on 2026-03-25 and has not been manually marked sold/expired since. Buyers on `wncmountain.homes` were seeing a frozen Navica dataset for nearly a month.

## Root Cause

`deploy/prd-crontab.txt` was first committed on 2026-03-21 (commit `a6c848941`, "Add schema migration script and Canopy cron setup") as a **brand-new file** (122-line addition, not an edit). Its contents covered the MLS Grid / Canopy sync exhaustively. Navica was never added.

Prior to that commit, the Navica sync presumably ran on PRD via a manually-installed crontab entry that was never checked in to the repository. The `crontab` command installs by replacing the entire file, so when `crontab /opt/mydreams/deploy/prd-crontab.txt` was run on PRD (around 2026-03-21 or 22), any manual Navica entry was wiped.

The `navica-sync.log` on PRD has a clean final run at 2026-03-25 17:18-17:20 UTC ("MountainLakesMLS incremental: 10200 fetched, 0 created, 10200 updated, 0 errors" then "Cross-listing: 32 properties found in both MLSs"). No auth failures. No exceptions. Just a final invocation, likely manual, then silence. The `.env` file on PRD was recreated on 2026-04-13 (inode `Birth` time) and contains 5 `NAVICA_*` keys, so credentials are present; they are simply not being used by any scheduled job.

This was neither a credential expiry, nor a code regression, nor an upstream API change. It was a cron entry that was never carried forward into the repo, so it got wiped the first time the authoritative crontab was installed from the repo.

## Evidence

- DEV DB query: max `captured_at` for mls_source IN ('NavicaMLS','MountainLakesMLS') = 2026-03-25T02:00 UTC (from DEV DB, slightly behind PRD).
- PRD `tail -50 /opt/mydreams/data/logs/navica-sync.log`: clean final run 2026-03-25 17:18-17:20 UTC.
- PRD `crontab -l`: zero entries containing `navica`.
- PRD `stat /opt/mydreams/.env`: inode `Birth: 2026-04-13`, so the file did not exist pre-incident; credentials were added during the 2026-04-10 "Phase A triage: pivot away from JTH-FUB" restructure.
- PRD `grep -c '^NAVICA_' /opt/mydreams/.env`: 5 (keys present).
- Git `log -S "navica" deploy/prd-crontab.txt`: empty. Navica has never been in the committed crontab.

## Why It Took 27 Days To Detect

No alerting existed for feed freshness. We discovered the gap while investigating broken gallery UX on `wncmountain.homes` — by looking at `max(list_date) per mls_source` and noticing two of three sources were frozen at 2026-03-24.

The memory principle on the project ("Quality Bar: Photo Status dashboard is the benchmark") correctly applies here: we had a detailed photo health tile but no feed health tile. **Photo quality means nothing if the underlying data is stale.**

## Fix

1. **Add Navica entries to `deploy/prd-crontab.txt`.** Incremental sync for both datasets on a reasonable cadence (Navica rate limits are TBD, but conservative is fine), plus one nightly reconciliation.
2. **Verify credentials.** Single test call against Navica to confirm the five `NAVICA_*` keys in `.env` still authenticate. If they were rotated into the `.env` on 2026-04-13 without being tested, they might be stale.
3. **Re-install the crontab on PRD** via `crontab /opt/mydreams/deploy/prd-crontab.txt` (destructive to any remaining manual entries; verify `crontab -l` after).
4. **One-shot manual backfill** from 2026-03-25 forward to catch up the 27-day gap for both datasets, using the incremental sync mode with `modification_timestamp > 2026-03-25T00:00:00Z`.
5. **Add a feed-freshness monitor** that runs daily, compares `max(list_date)` per `mls_source` to today, and alerts if any source is more than 48 hours behind.

## Lessons

1. **If a cron lives on PRD, it lives in `deploy/prd-crontab.txt`.** Anything else is load-bearing shadow infrastructure waiting to be erased.
2. **"Installing" the crontab is destructive** because `crontab <file>` replaces the whole table. Any review of the committed crontab must ask "what am I about to wipe?" not just "what am I about to add?"
3. **Dashboards must cover the data layer, not just the presentation layer.** We spent five weeks patching the photo path while two feeds were frozen. A `max(list_date) per mls_source` tile would have shown this on day 2.
4. **Silent correctness is the most expensive failure mode.** Navica didn't error, it just didn't run. No logs to read, no exceptions to chase. Detecting that requires measuring the expected output, not only the visible errors.
