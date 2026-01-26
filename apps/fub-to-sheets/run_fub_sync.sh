#!/bin/bash
# myDREAMS FUB Sync - Cron Wrapper
# Runs the FUB to Sheets sync with proper environment and logging

set -e  # Exit on error

# Auto-detect environment based on hostname or path
if [ -d "/opt/mydreams" ]; then
    # PRD environment
    PROJECT_ROOT="/opt/mydreams"
    VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
else
    # DEV environment
    PROJECT_ROOT="/home/bigeug/myDREAMS"
    VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
fi

SCRIPT_DIR="$PROJECT_ROOT/apps/fub-to-sheets"
CRON_LOG_DIR="$SCRIPT_DIR/cron_logs"

# Create log directory if it doesn't exist
mkdir -p "$CRON_LOG_DIR"

# Log file with timestamp
LOG_FILE="$CRON_LOG_DIR/$(date +%Y%m%d_%H%M%S).log"

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

# Run the sync and log output
# Note: Python script loads .env itself via python-dotenv
echo "========================================" >> "$LOG_FILE"
echo "myDREAMS FUB Sync - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

"$VENV_PYTHON" "$SCRIPT_DIR/fub_to_sheets_v2.py" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Sync completed successfully" >> "$LOG_FILE"
else
    echo "❌ Sync failed with exit code: $EXIT_CODE" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"

# Keep only last 30 days of cron logs
find "$CRON_LOG_DIR" -name "*.log" -mtime +30 -delete

exit $EXIT_CODE
