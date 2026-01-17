#!/bin/bash
# DREAMS Platform - Deployment Script
# Pulls latest code and restarts services
#
# Usage: ./deploy.sh [--no-restart]

set -e

DEPLOY_DIR="/opt/mydreams"
LOG_FILE="/opt/mydreams/logs/deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

# Parse arguments
NO_RESTART=false
if [[ "$1" == "--no-restart" ]]; then
    NO_RESTART=true
fi

# Ensure we're in the right directory
cd "$DEPLOY_DIR" || error "Cannot cd to $DEPLOY_DIR"

log "Starting deployment..."

# Create logs directory if it doesn't exist
mkdir -p "$DEPLOY_DIR/logs"

# Stash any local changes (shouldn't be any on server)
if [[ -n $(git status --porcelain) ]]; then
    warn "Local changes detected, stashing..."
    git stash
fi

# Pull latest changes
log "Pulling latest code from origin/main..."
git fetch origin
git reset --hard origin/main

# Update Python dependencies if requirements.txt changed
if git diff HEAD@{1} --name-only | grep -q "requirements.txt"; then
    log "requirements.txt changed, updating dependencies..."
    source "$DEPLOY_DIR/venv/bin/activate"
    pip install -r requirements.txt
    deactivate
fi

# Run any database migrations (if we add them later)
# log "Running database migrations..."
# source "$DEPLOY_DIR/venv/bin/activate"
# python -m alembic upgrade head
# deactivate

if [[ "$NO_RESTART" == false ]]; then
    # Restart services
    log "Restarting services..."
    sudo systemctl restart mydreams-api
    sudo systemctl restart mydreams-dashboard

    # Wait for services to start
    sleep 3

    # Check service status
    log "Checking service status..."
    if systemctl is-active --quiet mydreams-api; then
        log "mydreams-api: RUNNING"
    else
        error "mydreams-api failed to start!"
    fi

    if systemctl is-active --quiet mydreams-dashboard; then
        log "mydreams-dashboard: RUNNING"
    else
        error "mydreams-dashboard failed to start!"
    fi

    # Quick health check
    log "Running health check..."
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health | grep -q "200"; then
        log "API health check: PASSED"
    else
        warn "API health check: FAILED (may still be starting)"
    fi
else
    log "Skipping service restart (--no-restart flag)"
fi

log "Deployment complete!"
echo ""
echo "Recent commits:"
git log --oneline -5
