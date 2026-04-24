#!/bin/bash
# Tripwire: confirm photo-catchup / photo-drain systemd units are alive.
#
# Why this exists:
# - 2026-04-21→23: the Canopy catchup daemon ran for 2.5 days with fds 1
#   and 2 → /dev/null. Silent, blind. We only noticed because the pending
#   count stopped moving. By the time we looked, the budget was mis-spent.
#
# This check runs hourly, finds any systemd unit matching the photo-*
# naming, and confirms its journald output has a line newer than 90
# minutes ago. If not, alert.
#
# Contract: silent on OK, stderr + exit 1 on any stale unit.

set -euo pipefail

ALERT_LOG=/opt/mydreams/data/logs/tripwires.log
STALE_THRESHOLD_MIN=90   # alert if no journal output in this window

log_alert() {
    mkdir -p "$(dirname "$ALERT_LOG")"
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') DAEMON_STALE: $*" >> "$ALERT_LOG"
}

# All active photo-* units (systemd-run transient units + service units).
# --no-legend strips the header; awk picks the unit name column.
units=$(systemctl list-units --state=active --no-legend 2>/dev/null \
    | awk '$1 ~ /^photo-(catchup|drain-)/ {print $1}')

if [ -z "$units" ]; then
    echo "no photo-* units running; nothing to check"
    exit 0
fi

alerts=0
now_unix=$(date +%s)

for unit in $units; do
    # Last journald entry timestamp in epoch seconds, short-unix format
    # prints the timestamp as the first whitespace-separated field.
    last_line=$(journalctl -u "$unit" -n 1 --no-pager -o short-unix 2>/dev/null | tail -1)
    if [ -z "$last_line" ]; then
        log_alert "$unit has no journald output at all"
        {
            echo "DAEMON_STALE: $unit has never logged — likely started with stdout redirected to /dev/null"
        } >&2
        alerts=$((alerts + 1))
        continue
    fi
    last_unix=$(echo "$last_line" | awk '{print int($1)}')
    if [ -z "$last_unix" ] || [ "$last_unix" -eq 0 ]; then
        log_alert "$unit journalctl timestamp unparseable"
        continue
    fi
    age_min=$(( (now_unix - last_unix) / 60 ))
    if [ "$age_min" -gt "$STALE_THRESHOLD_MIN" ]; then
        log_alert "$unit silent for ${age_min} min (threshold ${STALE_THRESHOLD_MIN})"
        {
            echo "DAEMON_STALE: $unit silent ${age_min} min > ${STALE_THRESHOLD_MIN} threshold"
            echo "Recent (last 3 lines):"
            journalctl -u "$unit" -n 3 --no-pager
        } >&2
        alerts=$((alerts + 1))
    fi
done

if [ "$alerts" -gt 0 ]; then
    exit 1
fi
echo "$(echo "$units" | wc -l) daemon unit(s) healthy"
exit 0
