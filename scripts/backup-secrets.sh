#!/bin/bash
# myDREAMS Secrets Backup Script
# Backs up critical non-versioned files to Google Drive

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
REMOTE="gdrive-ip:myDREAMS-Backups/secrets"

echo "🔒 myDREAMS Secrets Backup - $(date)"
echo "=================================="

# Files to backup
FILES=(
    ".env"
    "service_account.json"
)

# Optional files (backup if they exist)
OPTIONAL_FILES=(
    "session.json"
    "apps/fub-to-sheets/cache/session.json"
)

cd "$PROJECT_ROOT"

# Backup required files
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ Backing up: $file"
        rclone copy "$file" "$REMOTE/" -v
        # Also archive with timestamp
        rclone copy "$file" "$REMOTE/archive/$file.$BACKUP_DATE/" -v
    else
        echo "⚠ Missing: $file (skipping)"
    fi
done

# Backup optional files
for file in "${OPTIONAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ Backing up: $file"
        rclone copy "$file" "$REMOTE/" -v
    fi
done

echo ""
echo "✅ Backup complete!"
echo "📁 Location: $REMOTE"
echo ""

# Verify backup
echo "📋 Current backups:"
rclone ls "$REMOTE/" | grep -E "\.env|service_account\.json|session\.json" || echo "No files found"
