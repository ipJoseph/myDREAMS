#!/bin/bash
# myDREAMS Secrets & Config Backup Script
# Backs up critical non-versioned files to Google Drive
#
# Covers:
#   - Root .env (API keys, SMTP creds, all secrets)
#   - Google service account credentials
#   - Public site auth config (.env.local)
#   - Sync state files (avoid unnecessary full re-syncs)
#   - FUB sync cache/session files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
REMOTE="gdrive-ip:myDREAMS-Backups/secrets"

echo "myDREAMS Secrets Backup - $(date)"
echo "=================================="

# Required files (warn if missing)
REQUIRED_FILES=(
    ".env"
    "service_account.json"
)

# App-specific config files
APP_CONFIG_FILES=(
    "apps/public-site/.env.local"
)

# State files (not secrets, but painful to lose)
STATE_FILES=(
    "data/navica_sync_state.json"
    "data/mlsgrid_sync_state.json"
)

# Optional files (backup if they exist, no warning if missing)
OPTIONAL_FILES=(
    "session.json"
    "apps/fub-to-sheets/cache/session.json"
)

cd "$PROJECT_ROOT"

BACKED_UP=0
MISSING=0

# Backup required files
echo ""
echo "--- Required secrets ---"
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  Backing up: $file"
        rclone copy "$file" "$REMOTE/$(dirname "$file")/" -v
        rclone copy "$file" "$REMOTE/archive/$file.$BACKUP_DATE/" -v
        BACKED_UP=$((BACKED_UP + 1))
    else
        echo "  WARNING - Missing: $file"
        MISSING=$((MISSING + 1))
    fi
done

# Backup app config files
echo ""
echo "--- App config files ---"
for file in "${APP_CONFIG_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  Backing up: $file"
        rclone copy "$file" "$REMOTE/$(dirname "$file")/" -v
        rclone copy "$file" "$REMOTE/archive/$file.$BACKUP_DATE/" -v
        BACKED_UP=$((BACKED_UP + 1))
    else
        echo "  WARNING - Missing: $file"
        MISSING=$((MISSING + 1))
    fi
done

# Backup state files
echo ""
echo "--- State files ---"
for file in "${STATE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  Backing up: $file"
        rclone copy "$file" "$REMOTE/$(dirname "$file")/" -v
        BACKED_UP=$((BACKED_UP + 1))
    else
        echo "  (skipped, does not exist): $file"
    fi
done

# Backup optional files
echo ""
echo "--- Optional files ---"
for file in "${OPTIONAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  Backing up: $file"
        rclone copy "$file" "$REMOTE/$(dirname "$file")/" -v
        BACKED_UP=$((BACKED_UP + 1))
    fi
done

echo ""
echo "=================================="
echo "Backup complete: $BACKED_UP files backed up, $MISSING missing"
if [ $MISSING -gt 0 ]; then
    echo "WARNING: $MISSING required files were missing!"
fi
echo "Location: $REMOTE"
echo ""

# Verify backup
echo "Current backups:"
rclone ls "$REMOTE/" --max-depth 3 | grep -v "archive/" || echo "No files found"
