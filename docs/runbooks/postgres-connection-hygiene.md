# Runbook: Postgres Connection Hygiene

Starting point: 2026-04-21 incident during Navica feed restore. Database refused a new connection with `FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute` because 89 backends were stuck in `active` state, aged 4 to 16 hours. This runbook documents detection, recovery, and prevention so we never rediscover this by surprise.

## Concepts

- **`max_connections`** (100 on PRD) is PostgreSQL's hard limit. 3 slots are reserved for superuser. The remaining 97 are the effective budget for application workers.
- **Per-process pool** (`ThreadedConnectionPool(minconn, maxconn)` in `src/core/pg_adapter.py`) bounds how many connections one Python process can hold at once. `minconn=2, maxconn=5` per process.
- **Active backends that don't represent live work are "zombies."** They hold a slot without doing anything. Accumulate silently. Usually from killed workers / unclosed transactions / dropped TCP sockets that PG hasn't noticed yet.

## Detection

Three cheap queries. Run them anytime, bookmark them in your head.

### 1. Fast pulse
```sql
SELECT state, count(*) FROM pg_stat_activity
WHERE pid <> pg_backend_pid() GROUP BY state ORDER BY count(*) DESC;
```
Expected on healthy PRD (rough): `active ≤ 10`, `idle ≤ 30`, `idle in transaction = 0 or 1`. If `active > 20` sustained, something is wrong.

### 2. Age breakdown (zombie detector)
```sql
SELECT state, count(*),
       MIN(now() - query_start) AS oldest,
       MAX(now() - query_start) AS newest
FROM pg_stat_activity
WHERE pid <> pg_backend_pid() AND state IS NOT NULL
GROUP BY state;
```
Anything in `active` older than 5 minutes is suspect. Over 30 minutes is certainly a zombie. Over an hour means PG's TCP keepalives are too slack.

### 3. Leak source attribution
```sql
SELECT LEFT(query, 80) AS q, count(*)
FROM pg_stat_activity
WHERE state = 'active' AND pid <> pg_backend_pid()
  AND now() - query_start > interval '5 minutes'
GROUP BY LEFT(query, 80)
ORDER BY count(*) DESC LIMIT 10;
```
Tells you which code path is responsible. The answer dictates the fix: a missing `try/finally`, a missing `conn.close()`, a missing `pool.putconn()`, or a worker that was SIGKILLed mid-query.

## Recovery

### Terminate zombies surgically
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active' AND pid <> pg_backend_pid()
  AND now() - query_start > interval '5 minutes';
```
Safe: only kills queries that have been "running" longer than anything legitimate should. For queries longer than that which ARE legitimate (rare), schedule the operation during off-hours and raise the threshold.

### Terminate leaked `idle in transaction`
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes';
```
These are clients that opened a transaction and walked away. Killing them rolls back the transaction (no data loss if the code didn't intend to commit).

### Restart services (blunt but effective)
```
systemctl restart mydreams-api mydreams-dashboard mydreams-workflow mydreams-task-sync mydreams-linear-sync
```
Clears all pools owned by those daemons. Worker-side connections go away; PG reaps them quickly once TCP detects the close.

## Prevention (config levers)

### PostgreSQL side (postgresql.conf)

```
# Auto-rollback transactions that sit open too long.
idle_in_transaction_session_timeout = 300000   # 5 minutes

# Cap runaway queries.
statement_timeout = 120000   # 2 minutes

# Detect dead TCP sockets quickly so zombie backends get reaped.
tcp_keepalives_idle = 60
tcp_keepalives_interval = 10
tcp_keepalives_count = 6
```

Apply with `sudo systemctl reload postgresql` (no restart needed for most of these).

### Application side (our code)

- Use `get_db()` via context manager, never raw. Ensure every code path returns the connection to the pool.
- Grep for bare `conn = get_db()` without a matching `conn.close()` or pool release. Each one is a latent leak.
- For long-running scripts (cron jobs, backfills), catch SIGTERM/SIGINT and close the pool cleanly before exit:
  ```python
  import signal, sys
  def _shutdown(*_):
      pg_adapter.close_pool()
      sys.exit(0)
  signal.signal(signal.SIGTERM, _shutdown)
  signal.signal(signal.SIGINT, _shutdown)
  ```

## Monitoring (add to dashboard or cron alert)

```sql
-- If any of these return true, alert:
-- (1) Too many active
SELECT count(*) > 20 FROM pg_stat_activity WHERE state = 'active';

-- (2) Any zombie older than 10 min
SELECT count(*) > 0 FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '10 minutes';

-- (3) Any idle-in-transaction older than 1 min
SELECT count(*) > 0 FROM pg_stat_activity
WHERE state = 'idle in transaction' AND now() - state_change > interval '1 minute';
```

Wire into the Photo Status dashboard tile style: green if all three false, amber if one true, red if two or more.

## History

| Date | Event | Peak active | Peak zombie age | Notes |
|---|---|---|---|---|
| 2026-04-21 | Navica backfill blocked; 89 zombies discovered | 89 | ~16h | Pool maxconn reduced 10 → 5 (commit `0f96d01`). Root cause: head-of-line block. 5 idempotent re-runs of `ALTER TABLE listings ADD COLUMN gallery_status` left stuck holding/waiting exclusive lock on `listings`. 45 `SELECT ... FROM listings`, 14 home-page COUNT queries, and ~10 aggregate stats queries from the public site queued behind them, aging for hours. Fix: `deploy/postgresql/99-mydreams.conf` (statement_timeout 2 min would have killed the stuck ALTERs on their own). |
| 2026-04-21 | Maintenance window resolved lingering blockers | 0 | n/a | 59-second self-contained run via `scripts/maintenance-20260421.sh`. Took pg_dump snapshot, disabled crontab, stopped 3 daemons, killed stragglers, ADDed `gallery_priority` column, widened `lot_sqft` INT → BIGINT (listing 26045243 had LotSizeSquareFeet=2.6B overflowing INT32), deployed A7 (public.py sqlite3→pg_adapter) + A8 (Navica sync per-row rollback), restarted services, re-enabled crontab, ran 5 smoke tests. Post-window pool: 0 active. Code commits `d683a9b`. |
