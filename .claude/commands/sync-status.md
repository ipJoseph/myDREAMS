---
description: Check MLS sync health
---

# MLS Sync Status

Check the health and status of all MLS data sync pipelines.

## Instructions

For each MLS source, report the following:

### 1. Navica (Carolina Smokies MLS)
- Read `data/navica_sync_state.json` for last sync timestamp and status
- Use `dreams-db` MCP `run_sql` to count listings by status: `SELECT status, COUNT(*) FROM listings WHERE mls_source='NavicaMLS' GROUP BY status`
- Also check MountainLakesMLS (nav26 dataset): `SELECT status, COUNT(*) FROM listings WHERE mls_source='MountainLakesMLS' GROUP BY status`
- Check photo counts: `SELECT mls_source, COUNT(*) FROM listings WHERE mls_source IN ('NavicaMLS','MountainLakesMLS') AND photo_local_path IS NOT NULL GROUP BY mls_source`
- Note any errors in the sync state

### 2. MLS Grid (Canopy MLS)
- Read `data/mlsgrid_sync_state.json` for last sync timestamp and status
- Use `dreams-db` MCP `run_sql` to count listings by status: `SELECT status, COUNT(*) FROM listings WHERE mls_source='CanopyMLS' GROUP BY status`
- Check if MLSGRID_TOKEN is configured (check .env for the variable name, don't display the value)
- Note any errors in the sync state

### 3. Overall Database Health
- Total listing count: `SELECT COUNT(*) FROM listings`
- Listings by source: `SELECT mls_source, COUNT(*) FROM listings GROUP BY mls_source`
- Recent additions (last 24h): `SELECT COUNT(*) FROM listings WHERE captured_at > datetime('now', '-1 day')`
- Recent modifications (last 24h): `SELECT COUNT(*) FROM listings WHERE modification_timestamp > datetime('now', '-1 day')`

## Output Format

Present results in a clean table format:

```
MLS Sync Status Report
======================

Source          | Last Sync        | Active | Pending | Total | Photos | Status
----------------|------------------|--------|---------|-------|--------|-------
Navica          | 2026-03-21 08:00 |  1,373 |     202 | 1,575 |  1,575 | OK
Canopy MLS      | 2026-03-21 08:00 |  5,432 |     312 | 5,744 |  5,100 | OK

Database Total: 7,319 listings
Updated (24h): 150 | Added (24h): 12
```

Flag any issues: stale syncs (>24h old), missing photos, error states, missing API tokens.

## Argument

$ARGUMENTS - Optional: "navica" or "canopy" to check only one source
