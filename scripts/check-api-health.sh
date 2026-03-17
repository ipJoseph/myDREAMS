#!/bin/bash
# Health check for local DEV property API
# Called by systemd timer every 30 seconds
# Restarts the service if the API is unresponsive

API_URL="http://localhost:5000/api/health"
SERVICE="mydreams-api-dev.service"

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_URL" 2>/dev/null)

if [ "$response" != "200" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') API health check failed (HTTP $response), restarting $SERVICE"
    systemctl --user restart "$SERVICE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') API healthy"
fi
