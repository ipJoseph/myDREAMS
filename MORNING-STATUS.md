# Morning Status — 2026-04-24

Written by Claude overnight while you slept. Updated as checkpoints fire.

## Drain (Task #1, Phase 2) — on track

Canopy photo-catchup daemon is running cleanly under `photo-catchup.service`
(systemd-run, journald-captured). Zero crashes overnight.

### Trajectory

| Timestamp (UTC) | ready | pending | skipped | Notes |
|---|---|---|---|---|
| 2026-04-23 22:17 | 23,931 | **6,437** | 687 | Baseline after restart |
| 2026-04-24 03:02 | 24,171 | **6,230** | 654 | First hour, −207 net |
| 2026-04-24 03:17 | 24,178 | **6,223** | 654 | Throttled, 35k budget reached |
| 2026-04-24 03:21 | 24,178 | **6,223** | 654 | **Worker asleep 18.3h until ~21:03 UTC** |

**Updated ETA — longer than I first quoted.**

At 03:03 UTC the worker logged:
> 24h budget full (35000); sleeping 65898s for oldest entry to expire

That's **18.3 hours of sleep** before any more requests fire. The throttle
is doing exactly what it was designed to do — protect us from the 40k/24h
MLS Grid warning — but it means the drain is budget-bounded, not rate-bounded:

- Listings remaining ≈ 6,223 × ~25 photos = **~155k requests to drain**
- Daily budget: 35k requests/24h
- Realistic pending drop per 24h cycle: ~2,000–3,000 listings
- **True full-drain ETA: ~3–4 more days** (not the 24–48h I first quoted)

The faster initial drop happened because many pending listings were
"already downloaded but misflagged" — correcting those required only the
DB flip, not new downloads. That low-hanging fruit is gone.

**Speed knobs we could turn** (all would still stay under the 40k/24h
warning, but gain is small):
- `--daily-budget 35000` → `38000` (8% more headroom per day)
- `--max-rps 1.8` → `2.0` (at the ceiling; saves ~30 min per cycle)

Neither materially changes the 3–4 day estimate because we're budget-bound,
not rate-bound. The daemon is correctly pacing itself against MLS Grid's
limits. If we want faster, we need to either:
  - Request a higher quota from MLS Grid (real conversation, not a knob)
  - Accept the 3–4 day drain as the cost of the initial bulk load

Going forward post-drain, new listings arrive at ~100/day × 30 photos =
3,000 reqs/day — far under budget. Steady-state is trivial.

- **Zero logged errors** from the worker on the ~1,500 listings processed
- No listings stuck flipping ready↔pending — the new readiness rule is working

### Observability

```bash
# On PRD:
systemctl status photo-catchup
journalctl -u photo-catchup -f
cat /opt/mydreams/data/photo-catchup/COMPLETED   # exists when done
```

Local trend log: `data/drain-trend.log` (appended each checkpoint).

## Phase 3 — DEV progress committed, NOT deployed

All changes are on `main`, pushed to GitHub. **Nothing deployed to PRD.**
You review the diffs before we `git pull` on PRD.

### Commits overnight

```
fc78333  photo-catchup: document systemd-run as canonical invocation
d49ccb3  archive 3 one-shot photo scripts superseded by gallery_backfill_strict
45dbe8e  sync_engine: per-row SAVEPOINTs (invariant #7) + fix dangling indent
06dc160  audit_photo_invariants: stable category keys + summary-only default
49e2d7f  Phase 3 chunk 1: pristine Canopy upkeep — deprecate photo_ready + photo_local_path
```

### What each commit does

1. **49e2d7f (pristine upkeep)** — stops writing the deprecated columns
   `photo_ready`, `photo_local_path`, `photos_count` in every live Canopy
   code path (sync_engine, PhotoManager, cron.py, gallery_backfill_strict).
   `gallery_status` is the single source of truth per spec invariant #3.
   Also switches the sync engine's inline photo download from the
   CLOSE_WAIT-prone `requests.get(stream=True, timeout=30)` pattern to the
   hardened `apps.photos.downloader.download_photo()`. Applies the same
   10%-broken readiness tolerance as the backfill worker. Marks
   `apps/mlsgrid/download_photos.py` deprecated (crontab line to be
   removed in Phase 4).

2. **06dc160 (audit cleanup)** — makes `scripts/audit_photo_invariants.py`
   cron-friendly. Summary-only by default, stable category keys so counts
   don't fragment across "5 files missing" / "34 files missing" buckets.

3. **45dbe8e (per-row savepoints)** — spec invariant #7. Each sync row is
   now its own SAVEPOINT inside the batch transaction. One row's failure
   no longer poisons up to 9 sibling rows (the 2026-03-24 incident's
   cascade pattern). Also fixes an IndentationError in the incremental
   sync except-block that I introduced and then caught during testing.

4. **d49ccb3 (archive)** — moves three superseded one-shot scripts to
   `archive/scripts-2026-04-23/` with a README explaining the provenance.

5. **fc78333 (daemon docstring)** — documents `systemd-run` as the
   canonical invocation. The legacy `nohup ... > log 2>&1 &` pattern is
   what made the daemon blind yesterday; systemd-run forces journald.

### How to deploy Phase 3 (when you're ready)

```bash
# On PRD
ssh root@178.156.221.10 "cd /opt/mydreams && git pull"
```

**No service restart needed** for any of these changes:
- The sync engine changes take effect on the next `apps.mlsgrid.cron_sync`
  run. Right now Canopy cron is paused, so the sync_engine changes are
  dormant until we restart the cron (Phase 4).
- The gallery_backfill_strict.py change takes effect on the next iteration
  the daemon starts. It'll pick up the new code without a restart since
  the daemon re-invokes the script each iteration.

### What I *haven't* done yet (Phase 3 residue)

- **Error taxonomy improvements** — distinguishing upstream-404 / timeout /
  rate-limit / pg-timeout in `gallery_backfill_strict.py` stats. Current
  code has one `stats["errors"]` counter for all failures. Low-priority;
  the existing DEBUG logs from the downloader already distinguish, just
  not in aggregate.
- **Phase 4 and Phase 5** — cron restart and tripwires. Those are your call.

## Issues I noticed but did NOT touch

- **`dreams-db` MCP reports stale/wrong counts.** MCP's Canopy ACTIVE total
  was 23,521; ground-truth psql showed 31,055. Either MCP is hitting a
  different snapshot or a cache. I ignored MCP for this session's data.
  **Worth investigating tomorrow** — it could mislead anyone using the
  MCP for operational checks.
- **DEV audit reported 17,564 invariant violations.** Don't panic — that's
  almost certainly because DEV DB was restored from PRD at some point
  before photos were fully downloaded, and DEV's `data/photos/mlsgrid/`
  dir is sparse compared to PRD's `/mnt/dreams-photos/`. The real PRD
  invariant state will be measurable after the drain completes. Do NOT
  run `audit_photo_invariants.py --source CanopyMLS --fix` on DEV — it'd
  flip the entire DEV DB to pending with no worker to drain.
- **`photo_verified_at` stored as TEXT, not TIMESTAMP** in PG. Caused a
  `date_trunc(unknown, text)` error when I tried a time-bucketed query.
  Same for `photos_change_timestamp`. Not blocking anything but violates
  type hygiene. Could be fixed during Phase 4 schema cleanup.
- **The committed hook TTL is still 600s (10 min).** I edited it to 28800
  for tonight only (with your explicit approval). **Revert before
  morning**: `sed -i 's/-lt 28800/-lt 600/' .claude/hooks/guard-prd-deploy.sh`
  — or leave for future overnight work, your call.

## What I will NOT do

- Deploy Phase 3 to PRD — you review first
- Modify the crontab — Phase 4
- Touch the running daemon unless it crashes (recovery only)

## Contact recovery

If the daemon crashed and auto-recovery failed, this file will have been
overwritten with the error details. If the file still reads like a status
(not an error report), everything is green.
