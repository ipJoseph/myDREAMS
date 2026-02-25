#!/bin/bash
# Run all enrichment scripts sequentially (resumable).
#
# Each script skips already-enriched records, so this is safe to re-run
# after a crash. Just launch it again and it picks up where it left off.
#
# Usage:
#   bash apps/navica/enrich_all.sh                    # Run all three
#   bash apps/navica/enrich_all.sh --flood-and-views   # Skip elevation (daytime)
#
# Overnight:
#   nohup bash apps/navica/enrich_all.sh > logs/enrich_all.log 2>&1 &
#   disown

cd "$(dirname "$0")/../.."

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "=========================================="
log "Starting enrichment pipeline"
log "=========================================="

run_step() {
    local name="$1"
    local module="$2"
    log ""
    log "[$name] Starting..."
    if python3 -u -m "$module"; then
        log "[$name] Complete."
    else
        log "[$name] FAILED (exit $?). Continuing to next step."
    fi
}

if [ "$1" != "--flood-and-views" ]; then
    run_step "1/3 Elevation" "apps.navica.enrich_elevation"
fi

run_step "2/3 Flood Zone" "apps.navica.enrich_flood"
run_step "3/3 View Potential" "apps.navica.enrich_views"

log ""
log "=========================================="
log "Pipeline finished."

python3 -c "
import sqlite3
c = sqlite3.connect('data/dreams.db')
t = c.execute('SELECT COUNT(*) FROM listings WHERE latitude IS NOT NULL AND latitude != 0').fetchone()[0]
e = c.execute('SELECT COUNT(*) FROM listings WHERE elevation_feet IS NOT NULL').fetchone()[0]
f = c.execute('SELECT COUNT(*) FROM listings WHERE flood_zone IS NOT NULL').fetchone()[0]
v = c.execute('SELECT COUNT(*) FROM listings WHERE view_potential IS NOT NULL').fetchone()[0]
print(f'  Elevation: {e:,}/{t:,}')
print(f'  Flood:     {f:,}/{t:,}')
print(f'  Views:     {v:,}/{t:,}')
c.close()
"

log "=========================================="
