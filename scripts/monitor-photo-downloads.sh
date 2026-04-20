#!/bin/bash
# Hourly photo download monitor
LOG="/home/bigeug/myDREAMS/data/photo-download-monitor.log"

# Check if DEV download is still running
DEV_STATUS="STOPPED"
pgrep -f "bulk_gallery_download" > /dev/null && DEV_STATUS="RUNNING"

# Check if PRD download is still running
PRD_STATUS="STOPPED"
ssh root@178.156.221.10 'pgrep -f bulk_gallery_download' > /dev/null 2>&1 && PRD_STATUS="RUNNING"

DEV_LINE="$(tail -1 /home/bigeug/myDREAMS/data/gallery-download.log 2>/dev/null)"
DEV_FILES="$(ls /home/bigeug/myDREAMS/data/photos/mlsgrid/ 2>/dev/null | wc -l)"
DEV_DISK="$(du -sh /home/bigeug/myDREAMS/data/photos/mlsgrid/ 2>/dev/null | cut -f1)"

PRD_LINE="$(ssh root@178.156.221.10 'tail -1 /opt/mydreams/data/gallery-download.log' 2>/dev/null)"
PRD_FILES="$(ssh root@178.156.221.10 'ls /opt/mydreams/data/photos/mlsgrid/ 2>/dev/null | wc -l' 2>/dev/null)"
PRD_DISK="$(ssh root@178.156.221.10 'du -sh /opt/mydreams/data/photos/mlsgrid/ 2>/dev/null | cut -f1' 2>/dev/null)"

echo "$(date '+%Y-%m-%d %H:%M') DEV [$DEV_STATUS]: $DEV_LINE | Files: $DEV_FILES | Disk: $DEV_DISK" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M') PRD [$PRD_STATUS]: $PRD_LINE | Files: $PRD_FILES | Disk: $PRD_DISK" >> "$LOG"
echo "---" >> "$LOG"
