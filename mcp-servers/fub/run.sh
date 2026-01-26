#!/bin/bash
# Run the Follow Up Boss MCP Server

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd ../.. && pwd)"

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Run the server
exec python server.py
