#!/bin/bash
#
# Start the DREAMS Property API Server
# This script starts the property API that receives data from the Chrome extension
# and syncs it to Notion.
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
API_DIR="$PROJECT_ROOT/apps/property-api"
VENV_DIR="$API_DIR/venv"
LOG_FILE="$PROJECT_ROOT/logs/property-api.log"
PID_FILE="$PROJECT_ROOT/logs/property-api.pid"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/logs"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Property API is already running (PID: $OLD_PID)"
        echo "Use: $0 restart  to restart"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q flask flask-cors python-dotenv notion-client
fi

# Change to API directory
cd "$API_DIR" || exit 1

case "${1:-start}" in
    start)
        echo "Starting DREAMS Property API..."
        nohup "$VENV_DIR/bin/python" app.py >> "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        sleep 2

        # Verify it started
        if curl -s http://localhost:5000/health > /dev/null 2>&1; then
            echo "Property API started successfully (PID: $(cat $PID_FILE))"
            echo "  - API:  http://localhost:5000"
            echo "  - Logs: $LOG_FILE"
        else
            echo "Failed to start Property API. Check logs: $LOG_FILE"
            exit 1
        fi
        ;;

    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            echo "Stopping Property API (PID: $PID)..."
            kill "$PID" 2>/dev/null
            rm -f "$PID_FILE"
            echo "Stopped."
        else
            echo "Property API is not running."
        fi
        ;;

    restart)
        $0 stop
        sleep 1
        $0 start
        ;;

    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
            echo "Property API is running (PID: $(cat $PID_FILE))"
            curl -s http://localhost:5000/health | python3 -m json.tool 2>/dev/null || echo "Health check failed"
        else
            echo "Property API is not running."
        fi
        ;;

    logs)
        tail -f "$LOG_FILE"
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
