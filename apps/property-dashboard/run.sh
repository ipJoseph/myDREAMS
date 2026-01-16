#!/bin/bash
# Run the DREAMS Property Dashboard

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "../../.venv" ]; then
    source ../../.venv/bin/activate
elif [ -d "../property-api/venv" ]; then
    source ../property-api/venv/bin/activate
fi

# Install dependencies if needed
pip install -q flask notion-client

echo "Starting DREAMS Property Dashboard on http://localhost:5001"
python app.py
