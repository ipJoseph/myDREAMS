#!/bin/bash
# DREAMS Services Startup Script
# Starts the Property API and Dashboard

DREAMS_ROOT="/home/bigeug/myDREAMS"
VENV_PATH="$DREAMS_ROOT/apps/property-api/venv"

echo "Starting DREAMS services..."

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Kill any existing instances
pkill -f "property-api.*app.py" 2>/dev/null
pkill -f "property-dashboard.*app.py" 2>/dev/null
sleep 1

# Start Property API (port 5000)
echo "Starting Property API on port 5000..."
cd "$DREAMS_ROOT/apps/property-api"
python app.py > /tmp/dreams-api.log 2>&1 &
API_PID=$!

# Wait for API to start
sleep 2

# Start Dashboard (port 5001)
echo "Starting Property Dashboard on port 5001..."
cd "$DREAMS_ROOT/apps/property-dashboard"
python app.py > /tmp/dreams-dashboard.log 2>&1 &
DASHBOARD_PID=$!

# Wait and verify
sleep 2

# Check if services are running
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "✓ Property API running on http://localhost:5000"
else
    echo "✗ Property API failed to start - check /tmp/dreams-api.log"
fi

if curl -s http://localhost:5001 > /dev/null 2>&1; then
    echo "✓ Property Dashboard running on http://localhost:5001"
else
    echo "✗ Property Dashboard failed to start - check /tmp/dreams-dashboard.log"
fi

echo ""
echo "Services started. Logs at:"
echo "  - API: /tmp/dreams-api.log"
echo "  - Dashboard: /tmp/dreams-dashboard.log"
echo ""
echo "To stop services: pkill -f 'app.py'"
