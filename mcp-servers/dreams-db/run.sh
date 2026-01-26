#!/bin/bash
# Run the DREAMS Database MCP Server

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd ../.. && pwd)"

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Set environment variables
export DREAMS_DB_PATH="${DREAMS_DB_PATH:-$PROJECT_ROOT/data/dreams.db}"

# Run the server
exec python server.py
