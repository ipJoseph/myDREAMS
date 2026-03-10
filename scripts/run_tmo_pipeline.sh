#!/bin/bash
# TMO Weekly Pipeline: shell wrapper for cron execution
# Checks for new TMO reports, parses, generates PDFs, and emails.
#
# Cron entry (8 AM EST daily):
#   0 8 * * * /home/bigeug/myDREAMS/scripts/run_tmo_pipeline.sh

set -euo pipefail

PROJECT_DIR="/home/bigeug/myDREAMS"
LOG_DIR="$PROJECT_DIR/data/logs"
LOG_FILE="$LOG_DIR/tmo-pipeline-$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"

echo "=== TMO Pipeline started at $(date) ===" >> "$LOG_FILE"

# Activate venv if it exists
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

python3 scripts/tmo_weekly_pipeline.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "=== TMO Pipeline finished at $(date) with exit code $EXIT_CODE ===" >> "$LOG_FILE"

# Keep only 30 days of logs
find "$LOG_DIR" -name "tmo-pipeline-*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
