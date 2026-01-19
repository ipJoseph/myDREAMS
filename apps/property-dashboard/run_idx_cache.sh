#!/bin/bash
# myDREAMS IDX Cache Populator - Cron Wrapper
# Looks up addresses for MLS numbers from FUB events

set -e

# Project paths
PROJECT_ROOT="/home/bigeug/myDREAMS"
SCRIPT_DIR="$PROJECT_ROOT/apps/property-dashboard"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOG_DIR="$PROJECT_ROOT/logs"

# Create log directory if needed
mkdir -p "$LOG_DIR"

# Log file with date
LOG_FILE="$LOG_DIR/idx_cache_$(date +%Y%m%d).log"

# Change to project root
cd "$PROJECT_ROOT" || exit 1

# Run the cache populator (limit 100 per run to avoid long execution)
echo "========================================" >> "$LOG_FILE"
echo "IDX Cache Populator - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

"$VENV_PYTHON" "$SCRIPT_DIR/populate_idx_cache.py" --limit 100 >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Cache population completed successfully" >> "$LOG_FILE"
else
    echo "Cache population failed with exit code: $EXIT_CODE" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"

# Keep only last 7 days of logs
find "$LOG_DIR" -name "idx_cache_*.log" -mtime +7 -delete 2>/dev/null || true

exit $EXIT_CODE
