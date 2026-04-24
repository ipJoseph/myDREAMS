#!/bin/bash
# Tripwire: detect drift between live crontab and committed template.
#
# Why this exists:
# - 2026-03-24: the Navica cron entries were silently wiped when someone
#   reinstalled the crontab from an older template. We didn't notice for
#   ~27 days (docs/incidents/20260324-navica-feed-stopped.md).
# - 2026-04-23: I (Claude) mis-diagnosed our intentionally-paused Canopy
#   cron as a regression and reinstalled, causing unintended live writes.
#
# A daily `diff live vs. template` catches both classes of drift within
# 24h, not 27 days.
#
# Exceptions:
# - The photo-catchup daemon and grace-period parallel drains legitimately
#   strip Canopy cron lines. If the catchup state dir has a recent backup
#   marker, we're in a deliberate pause — skip the check.
#
# Contract: silent on OK (cron swallows stdout via log redirect), writes
# to stderr + exits 1 on drift (cron MAILTO emails the error to the
# configured address).

set -euo pipefail

PROJECT=/opt/mydreams
TEMPLATE="$PROJECT/deploy/prd-crontab.txt"
PAUSE_MARKER="$PROJECT/data/photo-catchup/crontab-before-catchup.txt"
ALERT_LOG="$PROJECT/data/logs/tripwires.log"

log_alert() {
    mkdir -p "$(dirname "$ALERT_LOG")"
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') CRON_DRIFT: $*" >> "$ALERT_LOG"
}

# Skip during a catchup pause (backup marker less than 7 days old).
if [ -f "$PAUSE_MARKER" ]; then
    age_min=$(( ( $(date +%s) - $(stat -c %Y "$PAUSE_MARKER") ) / 60 ))
    if [ "$age_min" -lt 10080 ]; then
        echo "catchup pause active (marker age ${age_min} min); skipping drift check"
        exit 0
    fi
fi

if [ ! -f "$TEMPLATE" ]; then
    echo "CRON_DRIFT: template $TEMPLATE missing — cannot compare" >&2
    log_alert "template missing"
    exit 1
fi

# Normalize: strip comments + blank lines + leading/trailing whitespace.
# Don't care about ordering — compare sorted sets.
normalize() {
    grep -vE '^\s*#|^\s*$' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort
}

live=$(crontab -l 2>/dev/null | normalize || true)
template=$(normalize < "$TEMPLATE")

if [ "$live" = "$template" ]; then
    echo "cron OK: $(echo "$live" | grep -c . 2>/dev/null || echo 0) lines match template"
    exit 0
fi

# Drift detected. Log and emit both summary + diff to stderr.
log_alert "live crontab differs from template"
{
    echo "CRON_DRIFT: live crontab differs from $TEMPLATE"
    echo "--- diff (sorted, comments stripped) ---"
    diff <(echo "$live") <(echo "$template") | head -40
    echo "--- end diff ---"
} >&2
exit 1
