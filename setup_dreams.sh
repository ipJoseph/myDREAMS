#!/bin/bash
# DREAMS Platform Setup Script
# Run this from your myDREAMS repository root

set -e

echo "================================================"
echo "DREAMS Platform Setup"
echo "================================================"
echo ""

# Check we're in the right place
if [ ! -d "apps/fub-to-sheets" ]; then
    echo "ERROR: Please run this script from your myDREAMS repository root"
    echo "       Expected to find apps/fub-to-sheets directory"
    exit 1
fi

echo "✓ Found myDREAMS repository"

# Create new directories (won't overwrite existing)
echo ""
echo "Creating directory structure..."

mkdir -p src/adapters
mkdir -p src/core
mkdir -p src/presentation
mkdir -p src/utils
mkdir -p config
mkdir -p templates/assets
mkdir -p data
mkdir -p tests/test_adapters
mkdir -p tests/test_core
mkdir -p tests/test_integration

echo "✓ Directories created"

# Check if .gitignore needs updating
if ! grep -q "data/" .gitignore 2>/dev/null; then
    echo ""
    echo "Adding data/ to .gitignore..."
    echo "" >> .gitignore
    echo "# DREAMS Platform" >> .gitignore
    echo "data/" >> .gitignore
    echo "*.db" >> .gitignore
    echo "config/.env" >> .gitignore
    echo "config/config.yaml" >> .gitignore
    echo "✓ Updated .gitignore"
fi

# Create config from examples if they don't exist
if [ -f "config/.env.example" ] && [ ! -f "config/.env" ]; then
    echo ""
    echo "Creating config/.env from example..."
    cp config/.env.example config/.env
    echo "✓ Created config/.env (please edit with your API keys)"
fi

if [ -f "config/config.example.yaml" ] && [ ! -f "config/config.yaml" ]; then
    echo ""
    echo "Creating config/config.yaml from example..."
    cp config/config.example.yaml config/config.yaml
    echo "✓ Created config/config.yaml"
fi

# Check Python virtual environment
echo ""
if [ -d ".venv" ]; then
    echo "✓ Found existing virtual environment (.venv)"
    echo "  Activating..."
    source .venv/bin/activate
else
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "✓ Created and activated .venv"
fi

# Install new dependencies
echo ""
echo "Installing DREAMS platform dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt
    echo "✓ Dependencies installed"
else
    echo "⚠ No requirements.txt found - skipping dependency installation"
fi

# Initialize database
echo ""
echo "Initializing SQLite database..."
if [ -f "scripts/init_database.py" ]; then
    python scripts/init_database.py
    echo "✓ Database initialized at data/dreams.db"
else
    echo "⚠ init_database.py not found - skipping database initialization"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit config/.env with your API keys"
echo "2. Review docs/PROJECT_PLAYBOOK.md for the roadmap"
echo "3. Run: python scripts/init_database.py (if not done)"
echo ""
echo "Your existing apps in apps/ are unchanged and will"
echo "continue to work. The new architecture is in src/."
echo ""
