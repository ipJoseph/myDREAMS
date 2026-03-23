#!/bin/bash
# PRD database backup wrapper
# Runs backup-db.sh in PRD mode
# Install on PRD cron: 0 23 * * * /opt/mydreams/scripts/backup-db-prd.sh
set -e
exec /opt/mydreams/scripts/backup-db.sh --prd
