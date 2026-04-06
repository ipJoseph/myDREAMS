#!/bin/bash
# Health check for FUB daily sync
# Runs at 6:30 AM daily — verifies today's sync completed successfully.
# Sends an alert email if the sync log is missing or shows failure.

# Auto-detect environment
if [ -d "/opt/mydreams" ]; then
    PROJECT_DIR="/opt/mydreams"
else
    PROJECT_DIR="/home/bigeug/myDREAMS"
fi
CRON_LOG_DIR="$PROJECT_DIR/apps/fub-to-sheets/cron_logs"
TODAY=$(date +%Y%m%d)
RECIPIENT="joseph@integritypursuits.com"

# Load SMTP credentials from .env
if [ -f "$PROJECT_DIR/.env" ]; then
    SMTP_USER=$(grep -m1 '^SMTP_USERNAME=' "$PROJECT_DIR/.env" | cut -d= -f2)
    SMTP_PASS=$(grep -m1 '^SMTP_PASSWORD=' "$PROJECT_DIR/.env" | cut -d= -f2)
fi

if [ -z "$SMTP_USER" ] || [ -z "$SMTP_PASS" ]; then
    echo "ERROR: SMTP credentials not found in .env" >&2
    exit 1
fi

send_alert() {
    ALERT_SUBJECT="$1" ALERT_BODY="$2" \
    ALERT_FROM="$SMTP_USER" ALERT_TO="$RECIPIENT" \
    ALERT_SMTP_USER="$SMTP_USER" ALERT_SMTP_PASS="$SMTP_PASS" \
    python3 -c "
import os, smtplib
from email.mime.text import MIMEText

msg = MIMEText(os.environ['ALERT_BODY'])
msg['Subject'] = os.environ['ALERT_SUBJECT']
msg['From'] = os.environ['ALERT_FROM']
msg['To'] = os.environ['ALERT_TO']

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login(os.environ['ALERT_SMTP_USER'], os.environ['ALERT_SMTP_PASS'])
    s.send_message(msg)
"
}

# Find today's log file (matches YYYYMMDD_*.log)
LOG_FILE=$(ls "$CRON_LOG_DIR"/${TODAY}_*.log 2>/dev/null | head -1)

if [ -z "$LOG_FILE" ]; then
    send_alert \
        "[DREAMS ALERT] FUB sync did not run today" \
        "No FUB sync log found for $(date +%Y-%m-%d). The cron job may be missing or failed to start. Check: crontab -l"
    exit 1
fi

if ! grep -q "SYNC COMPLETED SUCCESSFULLY" "$LOG_FILE"; then
    TAIL=$(tail -10 "$LOG_FILE")
    send_alert \
        "[DREAMS ALERT] FUB sync failed today" \
        "FUB sync ran but did not complete successfully on $(date +%Y-%m-%d). Last lines: $TAIL"
    exit 1
fi

# All good — silent success
exit 0
