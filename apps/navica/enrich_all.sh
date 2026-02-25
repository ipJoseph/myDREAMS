#!/bin/bash
# Run all enrichment scripts sequentially.
# Usage: bash apps/navica/enrich_all.sh
# Or with nohup: nohup bash apps/navica/enrich_all.sh > logs/enrich_all.log 2>&1 &

set -e
cd "$(dirname "$0")/../.."

echo "=========================================="
echo "Starting full enrichment pipeline"
echo "Time: $(date)"
echo "=========================================="

echo ""
echo "[1/3] Elevation enrichment..."
echo "Started: $(date)"
python3 -u -m apps.navica.enrich_elevation
echo "Finished: $(date)"

echo ""
echo "[2/3] Flood zone enrichment..."
echo "Started: $(date)"
python3 -u -m apps.navica.enrich_flood
echo "Finished: $(date)"

echo ""
echo "[3/3] View potential enrichment..."
echo "Started: $(date)"
python3 -u -m apps.navica.enrich_views
echo "Finished: $(date)"

echo ""
echo "=========================================="
echo "All enrichment complete!"
echo "Time: $(date)"
echo "=========================================="
