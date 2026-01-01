#!/bin/bash
# myDREAMS Secrets Restore Script
# Restores critical files from Google Drive backup

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE="gdrive-ip:myDREAMS-Backups/secrets"

echo "🔓 myDREAMS Secrets Restore - $(date)"
echo "=================================="

cd "$PROJECT_ROOT"

# Check what's available
echo "📋 Available backups in Google Drive:"
rclone ls "$REMOTE/" | grep -E "\.env|service_account\.json|session\.json" || echo "No files found"
echo ""

# Restore files
echo "Restoring secrets..."

FILES=(
    ".env"
    "service_account.json"
)

for file in "${FILES[@]}"; do
    if rclone lsf "$REMOTE/$file" >/dev/null 2>&1; then
        echo "⬇ Restoring: $file"
        rclone copy "$REMOTE/$file" "$PROJECT_ROOT/" -v
        chmod 600 "$file"  # Secure permissions
    else
        echo "⚠ Not found in backup: $file"
    fi
done

echo ""
echo "✅ Restore complete!"
echo ""
echo "📁 Restored to: $PROJECT_ROOT"
ls -lh .env service_account.json 2>/dev/null || echo "Check which files were restored above"
