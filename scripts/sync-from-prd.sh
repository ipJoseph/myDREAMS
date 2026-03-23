#!/bin/bash
# Pull canonical dreams.db from PRD to DEV
# PRD is the single source of truth for all data
#
# Safety: takes a backup of the current DEV database before overwriting.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PRD_HOST="root@178.156.221.10"
PRD_DB="/opt/mydreams/data/dreams.db"
DEV_DB="$PROJECT_ROOT/data/dreams.db"

echo "=== Pre-sync backup ==="
"$SCRIPT_DIR/backup-db.sh"

echo ""
echo "=== Pulling dreams.db from PRD ==="
scp "$PRD_HOST:$PRD_DB" "$DEV_DB"
echo "PRD database copied."

# Ensure schema columns exist (PRD may not have DEV-only columns)
echo "Ensuring schema..."
cd "$PROJECT_ROOT"
python3 scripts/ensure_schema.py
echo "Done. DEV database synced from PRD canonical source."
