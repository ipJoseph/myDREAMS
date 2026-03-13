#!/bin/bash
# Pull canonical dreams.db from PRD to DEV
# PRD is the single source of truth for all data
set -e

PRD_HOST="root@178.156.221.10"
PRD_DB="/opt/mydreams/data/dreams.db"
DEV_DB="/home/bigeug/myDREAMS/data/dreams.db"

echo "Pulling dreams.db from PRD..."
scp "$PRD_HOST:$PRD_DB" "$DEV_DB"
echo "Done. DEV database synced from PRD canonical source."
