#!/bin/bash
# Run the Property API server

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "../../.venv" ]; then
    source ../../.venv/bin/activate
fi

# Install dependencies if needed
pip install -q -r requirements.txt

# Run the server
python app.py
