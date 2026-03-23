#!/bin/bash
# Rolling database backup with validation
#
# Creates compressed, dated snapshots of dreams.db and validates
# that critical tables have data. Keeps 14 days of local backups
# and pushes dated copies to Google Drive.
#
# Usage:
#   scripts/backup-db.sh              # run from project root
#   scripts/backup-db.sh --prd        # run on PRD server
#
# Designed to run via cron before any sync or migration operations.
set -e

# Detect environment
if [ "$1" = "--prd" ] || [ "$(hostname)" != "eugybuntustudio" ]; then
    PROJECT_ROOT="/opt/mydreams"
    ENV="PRD"
    GDRIVE_REMOTE=""
else
    PROJECT_ROOT="/home/bigeug/myDREAMS"
    ENV="DEV"
    GDRIVE_REMOTE="gdrive-ip"
fi

DB_PATH="$PROJECT_ROOT/data/dreams.db"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
LOG_FILE="$PROJECT_ROOT/data/logs/db-backup.log"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

log() {
    echo "[$TIMESTAMP] $ENV: $1" >> "$LOG_FILE"
    echo "$1"
}

# Check DB exists
if [ ! -f "$DB_PATH" ]; then
    log "ERROR: Database not found at $DB_PATH"
    exit 1
fi

# Create compressed backup
BACKUP_FILE="$BACKUP_DIR/dreams.db.$DATE.gz"

if [ -f "$BACKUP_FILE" ]; then
    log "Backup already exists for today: $BACKUP_FILE"
else
    log "Creating backup: $BACKUP_FILE"
    # Use Python sqlite3 .backup() for a consistent snapshot (handles WAL correctly)
    TEMP_DB=$(mktemp)
    python3 -c "
import sqlite3, sys
src = sqlite3.connect('$DB_PATH')
dst = sqlite3.connect('$TEMP_DB')
src.backup(dst)
dst.close()
src.close()
"
    gzip -c "$TEMP_DB" > "$BACKUP_FILE"
    rm -f "$TEMP_DB"
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup created: $BACKUP_SIZE"
fi

# Validate: check critical tables have data
log "Validating backup..."
TEMP_VALIDATE=$(mktemp)
gunzip -c "$BACKUP_FILE" > "$TEMP_VALIDATE"

VALIDATION=$(python3 -c "
import sqlite3, sys
conn = sqlite3.connect('$TEMP_VALIDATE')
checks = [('listings', 1000), ('leads', 10), ('agents', 100)]
failed = False
for table, minimum in checks:
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    except:
        count = 0
    status = 'OK' if count >= minimum else 'FAIL'
    if status == 'FAIL':
        failed = True
    print(f'  {table}: {count} rows ({status})')

# Log tables with no minimum (informational)
for table in ['property_packages', 'showings', 'showing_properties']:
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    except:
        count = 0
    print(f'  {table}: {count} rows')

conn.close()
sys.exit(1 if failed else 0)
")
VALID=$?

echo "$VALIDATION" | while IFS= read -r line; do
    log "$line"
done

rm -f "$TEMP_VALIDATE"

if [ "$VALID" -ne 0 ]; then
    log "ERROR: Backup validation FAILED. Critical tables below minimum."
    exit 1
fi
log "Validation passed."

# Prune old backups (keep KEEP_DAYS days)
find "$BACKUP_DIR" -name "dreams.db.*.gz" -mtime +$KEEP_DAYS -delete -print 2>/dev/null | while read f; do
    log "Pruned old backup: $(basename "$f")"
done

# Count remaining backups
BACKUP_COUNT=$(ls "$BACKUP_DIR"/dreams.db.*.gz 2>/dev/null | wc -l)
log "Backups on disk: $BACKUP_COUNT (keeping $KEEP_DAYS days)"

# Push to Google Drive (DEV only, dated copy not sync)
if [ -n "$GDRIVE_REMOTE" ] && command -v rclone &>/dev/null; then
    GDRIVE_PATH="$GDRIVE_REMOTE:/myDREAMS-db-backups/$DATE/"
    log "Pushing to Google Drive: $GDRIVE_PATH"
    if ! rclone copy "$BACKUP_FILE" "$GDRIVE_PATH" --log-level ERROR 2>> "$LOG_FILE"; then
        log "WARNING: Google Drive upload failed (local backup is still safe)"
    fi

    # Prune old Drive backups (keep 30 days)
    CUTOFF_DATE=$(date -d "-30 days" +%Y%m%d)
    rclone lsf "$GDRIVE_REMOTE:/myDREAMS-db-backups/" --dirs-only 2>/dev/null | while read dir; do
        DIR_DATE=$(echo "$dir" | tr -d '/')
        if [ "$DIR_DATE" -lt "$CUTOFF_DATE" ] 2>/dev/null; then
            rclone purge "$GDRIVE_REMOTE:/myDREAMS-db-backups/$dir" 2>> "$LOG_FILE"
            log "Pruned Drive backup: $dir"
        fi
    done
    log "Google Drive backup complete."
fi

log "Backup complete."
