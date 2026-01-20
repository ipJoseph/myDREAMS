#!/bin/bash
# Launch IDX portfolio automation in background

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment (try common locations)
if [ -f "../property-api/venv/bin/activate" ]; then
    source ../property-api/venv/bin/activate
elif [ -f "/opt/dreams/venv/bin/activate" ]; then
    source /opt/dreams/venv/bin/activate
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Log file location
LOG_FILE="${SCRIPT_DIR}/logs/idx-portfolio.log"
mkdir -p "${SCRIPT_DIR}/logs"

# Launch the automation
nohup python idx_automation.py "$1" "$2" > "$LOG_FILE" 2>&1 &
echo $!
