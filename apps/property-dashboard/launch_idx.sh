#!/bin/bash
# Launch IDX portfolio automation in background with virtual display

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment (try common locations)
if [ -f "../property-api/venv/bin/activate" ]; then
    source ../property-api/venv/bin/activate
elif [ -f "/opt/mydreams/venv/bin/activate" ]; then
    source /opt/mydreams/venv/bin/activate
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Log file location
LOG_FILE="${SCRIPT_DIR}/logs/idx-portfolio.log"
PROGRESS_FILE="${SCRIPT_DIR}/logs/idx-progress.json"
mkdir -p "${SCRIPT_DIR}/logs"

# Initialize progress file
echo '{"status": "starting", "current": 0, "total": 0, "message": "Initializing..."}' > "$PROGRESS_FILE"

# Check if we have a display (local) or need xvfb (server)
if [ -z "$DISPLAY" ]; then
    # No display - use xvfb-run for virtual display
    echo "No DISPLAY - using xvfb-run" >> "$LOG_FILE"
    nohup xvfb-run --auto-servernum --server-args="-screen 0 1280x900x24" \
        python idx_automation.py "$1" "$2" "$PROGRESS_FILE" >> "$LOG_FILE" 2>&1 &
else
    # Has display - run normally
    echo "DISPLAY=$DISPLAY - running with visible browser" >> "$LOG_FILE"
    nohup python idx_automation.py "$1" "$2" "$PROGRESS_FILE" >> "$LOG_FILE" 2>&1 &
fi

echo $!
