#!/bin/bash
# Launch IDX portfolio automation in background
cd /home/bigeug/myDREAMS/apps/property-dashboard
source ../property-api/venv/bin/activate
nohup python idx_automation.py "$1" > /tmp/idx-portfolio.log 2>&1 &
echo $!
