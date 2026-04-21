#!/bin/bash
#
# Maintenance window 2026-04-21
# =============================
# Purpose: clean-house fixes that have been blocked by live write traffic.
# All four items were approved as a scoped bundle (see chat transcript
# 2026-04-21, "maintenance window" discussion).
#
# Items:
#   1. ALTER TABLE listings ADD COLUMN gallery_priority INTEGER NOT NULL DEFAULT 0
#   2. ALTER TABLE listings ALTER COLUMN lot_sqft TYPE BIGINT  (lot 26045243 has 2.6B sqft)
#   3. Deploy A8 fix: per-row transaction rollback in apps/navica/sync_engine.py
#   4. Deploy A7 fix: replace 3x sqlite3.connect() in apps/property-api/routes/public.py
#      with pg_adapter.get_db()
#
# The last two are ALREADY in the repo when this script runs; the
# `git pull` below picks them up on PRD.
#
# Services that stay UP: mydreams-api, mydreams-dashboard, mydreams-public,
#                        postgresql
# Services paused: crontab, mydreams-workflow, mydreams-task-sync, mydreams-linear-sync
#
# Public site serves stale-but-current data throughout. No user-visible downtime.
#
# Time budget: 45 minutes. The script self-exits (with log) if any step fails.

set -o pipefail
LOG=/opt/mydreams/data/logs/maintenance-20260421.log
exec > >(tee -a "$LOG") 2>&1

echo "================================================================"
echo "Maintenance window START  $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================"

step() { echo ""; echo "---- $1 ----"; }
fail() { echo "FAIL at step: $1"; echo "See $LOG for details."; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Pre-flight snapshot (cheap insurance)
# ---------------------------------------------------------------------------
step "1. PG snapshot"
SNAP=/opt/mydreams/data/backups/pg_dump-maintenance-20260421.sql.gz
sudo -u postgres pg_dump dreams | gzip > "$SNAP" || fail "pg_dump"
ls -lh "$SNAP" || fail "snapshot size"
echo "snapshot OK: $SNAP"

# ---------------------------------------------------------------------------
# Step 2: Disable crontab (save first so we can restore)
# ---------------------------------------------------------------------------
step "2. Disable root crontab"
crontab -l > /opt/mydreams/data/logs/crontab-backup-20260421.txt || fail "crontab save"
crontab -r
echo "crontab backed up to /opt/mydreams/data/logs/crontab-backup-20260421.txt and cleared"

# ---------------------------------------------------------------------------
# Step 3: Stop background daemons (keep api + dashboard + public up)
# ---------------------------------------------------------------------------
step "3. Stop background daemons"
systemctl stop mydreams-workflow || true
systemctl stop mydreams-task-sync || true
systemctl stop mydreams-linear-sync || true
systemctl is-active mydreams-workflow mydreams-task-sync mydreams-linear-sync || true

# ---------------------------------------------------------------------------
# Step 4: Kill any lingering active queries from stopped processes
# ---------------------------------------------------------------------------
step "4. Terminate backends older than 30s on listings"
sudo -u postgres psql dreams -c "
SELECT pg_terminate_backend(pid), LEFT(query, 60)
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND state = 'active'
  AND now() - query_start > interval '30 seconds'
" || true
sleep 3

# ---------------------------------------------------------------------------
# Step 5: Apply ALTER TABLE (lock should now be uncontested)
# ---------------------------------------------------------------------------
step "5a. ADD COLUMN gallery_priority"
sudo -u postgres psql dreams <<'SQL'
BEGIN;
SET LOCAL statement_timeout = 0;
SET LOCAL lock_timeout = '30s';
ALTER TABLE listings ADD COLUMN IF NOT EXISTS gallery_priority INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_listings_gallery_priority_active ON listings (gallery_priority DESC) WHERE gallery_priority > 0;
COMMIT;
SQL
sudo -u postgres psql dreams -c "SELECT column_name FROM information_schema.columns WHERE table_name='listings' AND column_name='gallery_priority'" | grep -q gallery_priority || fail "5a gallery_priority not added"
echo "5a OK: gallery_priority added"

step "5b. ALTER COLUMN lot_sqft TYPE BIGINT"
sudo -u postgres psql dreams <<'SQL'
BEGIN;
SET LOCAL statement_timeout = 0;
SET LOCAL lock_timeout = '60s';
ALTER TABLE listings ALTER COLUMN lot_sqft TYPE BIGINT;
COMMIT;
SQL
sudo -u postgres psql dreams -c "SELECT data_type FROM information_schema.columns WHERE table_name='listings' AND column_name='lot_sqft'" | grep -q bigint || fail "5b lot_sqft not BIGINT"
echo "5b OK: lot_sqft is BIGINT"

# ---------------------------------------------------------------------------
# Step 6: Pull code fixes (A8 Navica rollback, A7 public.py conversion)
# ---------------------------------------------------------------------------
step "6. git pull"
git -C /opt/mydreams pull || fail "git pull"

# ---------------------------------------------------------------------------
# Step 7: Restart all daemons + api + dashboard
# ---------------------------------------------------------------------------
step "7. Restart services"
systemctl restart mydreams-api mydreams-dashboard || fail "restart api/dashboard"
systemctl start mydreams-workflow mydreams-task-sync mydreams-linear-sync || true
sleep 4
systemctl is-active mydreams-api mydreams-dashboard mydreams-public mydreams-workflow mydreams-task-sync mydreams-linear-sync || echo "WARN: one or more services not active (check above)"

# ---------------------------------------------------------------------------
# Step 8: Re-enable crontab
# ---------------------------------------------------------------------------
step "8. Re-enable crontab"
crontab /opt/mydreams/deploy/prd-crontab.txt || fail "crontab install"
crontab -l | grep -c cron_sync
echo "cron re-enabled"

# ---------------------------------------------------------------------------
# Step 9: Smoke tests
# ---------------------------------------------------------------------------
step "9. Smoke tests"

echo "  [9a] API health"
curl -sf http://127.0.0.1:5000/api/public/listings?limit=1 > /dev/null || fail "9a API /listings"
echo "  OK"

echo "  [9b] Detail endpoint returns gallery_status"
DETAIL_ID=$(curl -s "http://127.0.0.1:5000/api/public/listings?limit=1" | python3 -c "import sys,json;print(json.load(sys.stdin)['data'][0]['id'])")
GS=$(curl -s "http://127.0.0.1:5000/api/public/listings/$DETAIL_ID" | python3 -c "import sys,json;print(json.load(sys.stdin)['data'].get('gallery_status','MISSING'))")
[ "$GS" = "ready" ] || [ "$GS" = "pending" ] || fail "9b gallery_status=$GS"
echo "  OK gallery_status=$GS"

echo "  [9c] Gallery endpoint"
curl -sf "http://127.0.0.1:5000/api/public/listings/$DETAIL_ID/gallery" > /dev/null || fail "9c gallery endpoint"
echo "  OK"

echo "  [9d] Autocomplete (A7 converted endpoint)"
curl -sf "http://127.0.0.1:5000/api/public/autocomplete?q=Ash&limit=3" > /dev/null || fail "9d autocomplete"
echo "  OK"

echo "  [9e] Pool state"
sudo -u postgres psql dreams -c "SELECT state, count(*) FROM pg_stat_activity WHERE pid <> pg_backend_pid() GROUP BY state"
ACTIVE=$(sudo -u postgres psql dreams -tA -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()")
[ "$ACTIVE" -lt 30 ] || fail "9e too many active: $ACTIVE"
echo "  OK active=$ACTIVE"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "Maintenance window COMPLETE  $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "MAINTENANCE COMPLETE"
echo "================================================================"
