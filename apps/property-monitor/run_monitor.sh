#!/bin/bash
# myDREAMS Property Monitor - Run Script
# This script runs the property monitor with proper environment setup
# Intended for use with cron on VPS

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/venv}"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/property_monitor.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Timestamp for log entry
echo "========================================" >> "$LOG_FILE"
echo "Property Monitor Run: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Activate virtual environment and run monitor
cd "$PROJECT_ROOT"

if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "Virtual environment activated: $VENV_PATH" >> "$LOG_FILE"
else
    echo "Warning: Virtual environment not found at $VENV_PATH" >> "$LOG_FILE"
fi

# Run the property monitor
python "$SCRIPT_DIR/monitor_properties.py" 2>&1 | tee -a "$LOG_FILE"

# Log completion
echo "Monitor completed at: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
