#!/bin/bash

# FUB to Sheets Cron Wrapper
# This script ensures the proper working directory and environment for cron execution

# Set the script directory (change this to your actual path)
SCRIPT_DIR="/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2"

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

# Load environment variables from .env if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Run the Python script with full path to Python interpreter
# Using python3 explicitly to ensure correct version
"$REPO_ROOT/.venv/bin/python" "$SCRIPT_DIR/fub_to_sheets_v2.py"

# Exit with the same code as the Python script
exit $?
