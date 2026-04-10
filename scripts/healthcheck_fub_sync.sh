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

# Sync completed, but did the EUG Morning FUB Brief email actually go out?
# The Python script swallows SMTP errors and still logs SYNC COMPLETED SUCCESSFULLY,
# so we have to inspect the log for email-send failures explicitly.
if grep -q "Failed to send email" "$LOG_FILE"; then
    EMAIL_ERR=$(grep "Failed to send email" "$LOG_FILE" | head -1)
    # Log to syslog too, since the alert email will likely also fail
    # (healthcheck shares the same SMTP credentials that just broke).
    logger -t fub-healthcheck "EUG daily email NOT delivered: $EMAIL_ERR"
    send_alert \
        "[DREAMS ALERT] FUB sync OK but EUG daily email did not send" \
        "FUB sync completed on $(date +%Y-%m-%d) and all sheet/DB data is updated, but the EUG Morning FUB Brief email failed to deliver.

Error: $EMAIL_ERR

Most likely cause: Gmail App Password was revoked.
Fix:
  1. Regenerate at https://myaccount.google.com/apppasswords
  2. Update SMTP_PASSWORD in /opt/mydreams/.env
  3. Re-send today's report: /opt/mydreams/apps/fub-to-sheets/run_fub_sync.sh"
    exit 1
fi

# All good — silent success
exit 0
