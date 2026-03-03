#!/bin/bash
# myDREAMS Secrets & Config Restore Script
# Restores critical non-versioned files from Google Drive backup
#
# Run this after cloning the repo on a fresh OS install.
# After this script completes, follow the post-restore checklist.

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE="gdrive-ip:myDREAMS-Backups/secrets"

echo "myDREAMS Secrets Restore - $(date)"
echo "=================================="

cd "$PROJECT_ROOT"

# Check what's available
echo ""
echo "Available backups in Google Drive:"
rclone ls "$REMOTE/" --max-depth 3 | grep -v "archive/" || echo "No files found"
echo ""

# All files to restore with their target paths
RESTORE_FILES=(
    ".env"
    "service_account.json"
    "apps/public-site/.env.local"
    "data/navica_sync_state.json"
    "data/mlsgrid_sync_state.json"
)

RESTORED=0
FAILED=0

echo "Restoring files..."
echo ""

for file in "${RESTORE_FILES[@]}"; do
    target_dir=$(dirname "$file")
    mkdir -p "$target_dir"

    if rclone lsf "$REMOTE/$file" >/dev/null 2>&1; then
        echo "  Restoring: $file"
        rclone copy "$REMOTE/$file" "$PROJECT_ROOT/$target_dir/" -v
        # Secure permissions for secret files
        if [[ "$file" == *.env* || "$file" == *service_account* ]]; then
            chmod 600 "$PROJECT_ROOT/$file"
        fi
        ((RESTORED++))
    else
        echo "  Not in backup: $file (skipping)"
        ((FAILED++))
    fi
done

# Create symlinks
echo ""
echo "--- Creating directories ---"
mkdir -p "$PROJECT_ROOT/logs"
echo "  Created: logs/"

echo ""
echo "--- Creating symlinks ---"
if [ -f "$PROJECT_ROOT/service_account.json" ] && [ ! -e "$PROJECT_ROOT/apps/fub-to-sheets/service_account.json" ]; then
    ln -s "$PROJECT_ROOT/service_account.json" "$PROJECT_ROOT/apps/fub-to-sheets/service_account.json"
    echo "  Symlinked: apps/fub-to-sheets/service_account.json -> service_account.json"
else
    echo "  Symlink already exists or source missing"
fi

echo ""
echo "=================================="
echo "Restore complete: $RESTORED restored, $FAILED not found"
echo ""

# Post-restore checklist
echo "=========================================="
echo "  POST-RESTORE CHECKLIST"
echo "=========================================="
echo ""
echo "  1. Install Python dependencies:"
echo "     cd $PROJECT_ROOT"
echo "     .venv/bin/pip install -r requirements.txt"
echo "     .venv/bin/pip install -e apps/fub-core/"
echo ""
echo "  2. Install Node.js dependencies:"
echo "     cd apps/public-site && npm install"
echo ""
echo "  3. Verify crontab is set:"
echo "     crontab -l"
echo "     (If empty, restore from docs/ARCHITECTURE.md cron section)"
echo ""
echo "  4. Start services:"
echo "     scripts/start-services.sh"
echo "     cd apps/public-site && npx next dev &"
echo ""
echo "  5. Verify everything works:"
echo "     curl http://localhost:5000/health"
echo "     curl http://localhost:5001"
echo "     curl http://localhost:3000"
echo "     curl http://localhost:3000/api/auth/session"
echo ""
echo "  6. Test FUB sync:"
echo "     apps/fub-to-sheets/run_fub_sync.sh"
echo ""
echo "=========================================="
