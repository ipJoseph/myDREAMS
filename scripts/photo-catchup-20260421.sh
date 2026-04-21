#!/bin/bash
#
# Photo catchup daemon — 2026-04-21
# ==================================
# Pauses all Canopy/MLS-Grid cron entries (incremental sync, gallery sweeps,
# nightly reconciliation, photo downloads), runs a SINGLE-AGENT backfill at
# --max-rps 1.8 (ceiling is 2.0, per Eugy), daily-budget 35000 (safe under the
# 40k/24h warning), loops until CanopyMLS active listings with gallery_status
# 'pending' reaches zero, then restores the original crontab and exits.
#
# Navica cron stays active (different API, separate rate budget).
# DB backup and schema check stay active (no API calls).
#
# Safe to SIGTERM/SIGKILL: EXIT trap always restores crontab.
# Safe to re-run: idempotent. Each iteration re-reads pending count.
#
# Invocation:
#   nohup bash /opt/mydreams/scripts/photo-catchup-20260421.sh \
#     > /opt/mydreams/data/logs/photo-catchup-20260421.log 2>&1 < /dev/null &
#   disown
#
# Monitor:
#   tail -F /opt/mydreams/data/logs/photo-catchup-20260421.log
#   cat /opt/mydreams/data/photo-catchup/COMPLETED  (after it finishes)

set -o pipefail

PROJECT=/opt/mydreams
STATE_DIR=$PROJECT/data/photo-catchup
CRONTAB_BAK=$STATE_DIR/crontab-before-catchup.txt
COMPLETION_MARKER=$STATE_DIR/COMPLETED
mkdir -p "$STATE_DIR"

echo "=================================================================="
echo "Photo catchup daemon START  $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "PID=$$"
echo "=================================================================="

# -------------------------------------------------------------------------
# Cleanup: ALWAYS restore crontab on exit, whether normal or signal-triggered.
# -------------------------------------------------------------------------
cleanup() {
    RC=$?
    echo ""
    echo "---- cleanup (rc=$RC) at $(date -u +'%Y-%m-%dT%H:%M:%SZ') ----"
    if [ -f "$CRONTAB_BAK" ]; then
        if crontab "$CRONTAB_BAK"; then
            echo "crontab restored from $CRONTAB_BAK"
        else
            echo "ERROR: crontab restore failed. Run: crontab $CRONTAB_BAK"
        fi
    fi
    echo "catchup exited with rc=$RC at $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
}
trap cleanup EXIT
trap 'echo "caught SIGTERM"; exit 143' TERM
trap 'echo "caught SIGINT"; exit 130' INT

# -------------------------------------------------------------------------
# Step 1: Backup current crontab
# -------------------------------------------------------------------------
crontab -l > "$CRONTAB_BAK" || {
    echo "FATAL: could not read current crontab"
    exit 1
}
echo "crontab backed up: $(wc -l < "$CRONTAB_BAK") lines -> $CRONTAB_BAK"

# -------------------------------------------------------------------------
# Step 2: Install reduced crontab
#   Remove every line that uses MLS Grid (apps.mlsgrid.*) or the Canopy
#   gallery backfill script. Keep Navica, DB backup, schema check.
# -------------------------------------------------------------------------
grep -Ev "apps\.mlsgrid|gallery_backfill_strict|download_photos" "$CRONTAB_BAK" | crontab -
REMAINING=$(crontab -l | grep -cE "^[0-9\*]")
echo "paused Canopy/MLS-Grid entries. $REMAINING active cron lines remain:"
crontab -l | grep -vE "^#" | grep -vE "^$" | sed 's/^/  /'

# -------------------------------------------------------------------------
# Step 3: Kill any in-flight MLS-Grid workers
# -------------------------------------------------------------------------
if pkill -f gallery_backfill_strict.py 2>/dev/null; then
    echo "killed in-flight gallery_backfill_strict workers"
fi
if pkill -f "apps.mlsgrid.cron_sync" 2>/dev/null; then
    echo "killed in-flight mlsgrid.cron_sync workers"
fi
sleep 5

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
pending_count() {
    sudo -u postgres psql -tA dreams -c "
        SELECT COUNT(*) FROM listings
        WHERE mls_source = 'CanopyMLS'
          AND status = 'ACTIVE'
          AND gallery_status = 'pending'" 2>/dev/null | tr -d ' \n'
}

# -------------------------------------------------------------------------
# Step 4: Loop until done
# -------------------------------------------------------------------------
ITERATION=0
PREV_PENDING=""
NO_PROGRESS=0

while true; do
    ITERATION=$((ITERATION + 1))
    PENDING=$(pending_count)
    NOW=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

    echo ""
    echo "================================================================"
    echo "iteration $ITERATION  pending=$PENDING  $NOW"
    echo "================================================================"

    if [ "$PENDING" = "0" ]; then
        echo "ZERO pending: catchup complete"
        break
    fi

    # Safety: abort after 5 back-to-back iterations with no progress
    if [ "$PENDING" = "$PREV_PENDING" ]; then
        NO_PROGRESS=$((NO_PROGRESS + 1))
        if [ "$NO_PROGRESS" -ge 5 ]; then
            echo "ABORT: no progress in 5 consecutive iterations at pending=$PENDING"
            echo "       manual investigation required"
            exit 1
        fi
    else
        NO_PROGRESS=0
    fi
    PREV_PENDING="$PENDING"

    # Run one backfill cycle. Returns when daily budget hit or queue drains.
    cd "$PROJECT"
    "$PROJECT/venv/bin/python3" scripts/gallery_backfill_strict.py \
        --only-stale \
        --max-rps 1.8 \
        --daily-budget 35000
    BACKFILL_RC=$?
    echo "backfill iteration $ITERATION exited rc=$BACKFILL_RC"

    NEW_PENDING=$(pending_count)
    echo "pending after iteration: $NEW_PENDING"

    if [ "$NEW_PENDING" = "0" ]; then
        echo "queue drained"
        break
    fi

    # Decide pause length
    if [ "$NEW_PENDING" -lt "$PENDING" ]; then
        DELTA=$((PENDING - NEW_PENDING))
        echo "progress: -$DELTA listings this iteration; 60s before next"
        sleep 60
    else
        echo "no listings cleared: likely daily budget hit or transient API issue"
        echo "sleeping 3600s (1h) before retry"
        sleep 3600
    fi
done

# -------------------------------------------------------------------------
# Step 5: Completion marker
# -------------------------------------------------------------------------
FINAL=$(pending_count)
{
    echo "completed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    echo "final_pending=$FINAL"
    echo "total_iterations=$ITERATION"
} > "$COMPLETION_MARKER"

echo ""
echo "=================================================================="
echo "Photo catchup daemon COMPLETE  $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "final_pending=$FINAL  iterations=$ITERATION"
echo "=================================================================="
