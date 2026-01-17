#!/bin/bash
# DREAMS Platform - Backup Script
# Backs up SQLite database and config files to Backblaze B2
#
# Usage: ./backup.sh
#
# Prerequisites:
#   - Install b2 CLI: pip install b2
#   - Authenticate: b2 authorize-account <applicationKeyId> <applicationKey>
#
# Add to crontab for daily backups:
#   0 23 * * * /opt/mydreams/deploy/scripts/backup.sh >> /opt/mydreams/logs/backup.log 2>&1

set -e

# Configuration
DEPLOY_DIR="/opt/mydreams"
BACKUP_DIR="/opt/mydreams/backups"
B2_BUCKET="mydreams-backups"  # Create this bucket in Backblaze B2
RETENTION_DAYS=30

# Files to backup
DB_FILE="$DEPLOY_DIR/data/dreams.db"
ENV_FILE="$DEPLOY_DIR/.env"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
    exit 1
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="mydreams_backup_${TIMESTAMP}"

log "Starting backup: $BACKUP_NAME"

# Create SQLite backup (safe copy while database may be in use)
log "Backing up SQLite database..."
if [[ -f "$DB_FILE" ]]; then
    # Use SQLite's backup command for safe copy
    sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/${BACKUP_NAME}.db'"

    # Compress the backup
    gzip "$BACKUP_DIR/${BACKUP_NAME}.db"
    log "Database backup created: ${BACKUP_NAME}.db.gz"
else
    log "No database file found at $DB_FILE, skipping..."
fi

# Backup .env file (encrypted)
log "Backing up configuration..."
if [[ -f "$ENV_FILE" ]]; then
    # Create encrypted backup of .env
    # Using openssl with a password from environment
    if [[ -n "$BACKUP_ENCRYPTION_KEY" ]]; then
        openssl enc -aes-256-cbc -salt -pbkdf2 \
            -in "$ENV_FILE" \
            -out "$BACKUP_DIR/${BACKUP_NAME}.env.enc" \
            -pass env:BACKUP_ENCRYPTION_KEY
        log "Encrypted config backup created: ${BACKUP_NAME}.env.enc"
    else
        # Plain copy if no encryption key
        cp "$ENV_FILE" "$BACKUP_DIR/${BACKUP_NAME}.env"
        log "Config backup created: ${BACKUP_NAME}.env (unencrypted - set BACKUP_ENCRYPTION_KEY for encryption)"
    fi
fi

# Upload to Backblaze B2 (if configured)
if command -v b2 &> /dev/null; then
    log "Uploading to Backblaze B2..."

    # Upload database backup
    if [[ -f "$BACKUP_DIR/${BACKUP_NAME}.db.gz" ]]; then
        b2 upload-file "$B2_BUCKET" "$BACKUP_DIR/${BACKUP_NAME}.db.gz" "database/${BACKUP_NAME}.db.gz"
        log "Database uploaded to B2"
    fi

    # Upload config backup
    if [[ -f "$BACKUP_DIR/${BACKUP_NAME}.env.enc" ]]; then
        b2 upload-file "$B2_BUCKET" "$BACKUP_DIR/${BACKUP_NAME}.env.enc" "config/${BACKUP_NAME}.env.enc"
        log "Config uploaded to B2"
    elif [[ -f "$BACKUP_DIR/${BACKUP_NAME}.env" ]]; then
        b2 upload-file "$B2_BUCKET" "$BACKUP_DIR/${BACKUP_NAME}.env" "config/${BACKUP_NAME}.env"
        log "Config uploaded to B2"
    fi
else
    log "b2 CLI not found, skipping B2 upload. Install with: pip install b2"
fi

# Clean up old local backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "mydreams_backup_*" -type f -mtime +$RETENTION_DAYS -delete

# List recent backups
log "Recent local backups:"
ls -lh "$BACKUP_DIR" | tail -10

log "Backup complete!"

# Print backup size summary
if [[ -f "$BACKUP_DIR/${BACKUP_NAME}.db.gz" ]]; then
    SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.db.gz" | cut -f1)
    log "Database backup size: $SIZE"
fi
