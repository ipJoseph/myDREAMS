#!/bin/bash
# myDREAMS Property Monitor - VPS Setup Script
# Run this script on the VPS to set up property monitoring
#
# Prerequisites:
# - Python 3.10+ installed
# - myDREAMS project at /opt/mydreams
# - Virtual environment at /opt/mydreams/venv
# - .env file configured with NOTION credentials

set -e  # Exit on error

# Configuration
PROJECT_ROOT="${PROJECT_ROOT:-/opt/mydreams}"
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/venv}"
LOG_DIR="$PROJECT_ROOT/logs"
MONITOR_DIR="$PROJECT_ROOT/apps/property-monitor"

echo "=========================================="
echo "myDREAMS Property Monitor - VPS Setup"
echo "=========================================="
echo ""

# Check if running as appropriate user
if [ "$EUID" -eq 0 ]; then
    echo "Warning: Running as root. Consider using a dedicated user."
fi

# Step 1: Install system dependencies for Playwright
echo "[1/5] Installing system dependencies for Playwright..."
if command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libatspi2.0-0
    echo "  System dependencies installed."
else
    echo "  Warning: apt not found. Please install Playwright dependencies manually."
fi

# Step 2: Create log directory
echo "[2/5] Creating log directory..."
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"
echo "  Log directory created: $LOG_DIR"

# Step 3: Install Python dependencies
echo "[3/5] Installing Python dependencies..."
if [ -f "$VENV_PATH/bin/pip" ]; then
    "$VENV_PATH/bin/pip" install playwright httpx notion-client
    echo "  Python packages installed."
else
    echo "  Error: Virtual environment not found at $VENV_PATH"
    echo "  Please create it first: python3 -m venv $VENV_PATH"
    exit 1
fi

# Step 4: Install Playwright browsers
echo "[4/5] Installing Playwright Chromium browser..."
"$VENV_PATH/bin/playwright" install chromium
echo "  Chromium browser installed."

# Step 5: Make run script executable
echo "[5/5] Setting up run script..."
chmod +x "$MONITOR_DIR/run_monitor.sh"
echo "  Run script is executable."

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Verify .env file has NOTION credentials:"
echo "   NOTION_API_KEY=your_key"
echo "   NOTION_PROPERTIES_DB_ID=your_db_id"
echo ""
echo "2. Test the monitor manually:"
echo "   $MONITOR_DIR/run_monitor.sh"
echo ""
echo "3. Add cron job for daily monitoring (5 AM EST = 10 AM UTC):"
echo "   crontab -e"
echo "   0 10 * * * $MONITOR_DIR/run_monitor.sh >> $LOG_DIR/cron.log 2>&1"
echo ""
echo "4. Check logs at: $LOG_DIR/property_monitor.log"
echo ""
