#!/bin/bash
# Guard against unauthorized PRD deployments.
# This hook intercepts Bash commands and blocks any write operations
# to the PRD server unless the user explicitly approves.
#
# Read-only operations (like sync-from-prd.sh pulling DB to DEV) are allowed.
# Write operations (ssh deploy, scp TO prd, systemctl, git pull on PRD) are blocked
# unless a time-limited authorization token exists.
#
# Authorization flow:
#   1. Claude asks Eugy for deploy permission
#   2. Eugy grants permission
#   3. Claude creates /tmp/mydreams-prd-deploy-auth (valid for 10 minutes)
#   4. Hook sees the token and allows PRD write commands
#   5. Token auto-expires after 10 minutes
#
# PRD_HOST is read from .env so changing VPS vendors only requires
# updating one place.

set -e

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Get project root (relative to this script: .claude/hooks/ -> project root)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Read PRD_HOST from .env (single source of truth)
PRD_HOST=""
if [ -f "$PROJECT_ROOT/.env" ]; then
    PRD_HOST=$(grep -E '^PRD_HOST=' "$PROJECT_ROOT/.env" | cut -d= -f2 | tr -d '"'"'" | tr -d '[:space:]')
fi

# If no PRD_HOST configured, nothing to guard
if [ -z "$PRD_HOST" ]; then
    exit 0
fi

# If command doesn't reference PRD at all, allow it
if ! echo "$COMMAND" | grep -q "$PRD_HOST"; then
    exit 0
fi

# Allow read-only operations FROM PRD (pulling data to DEV)
# sync-from-prd.sh uses scp to pull DB from PRD to local
if echo "$COMMAND" | grep -qE "^scp\s+root@${PRD_HOST}:"; then
    exit 0
fi

# Allow the sync script itself
if echo "$COMMAND" | grep -q "sync-from-prd.sh"; then
    exit 0
fi

# Allow read-only SSH commands (status checks, log viewing, git log)
if echo "$COMMAND" | grep -qE "ssh\s+root@${PRD_HOST}\s+.*(systemctl status|systemctl is-active|journalctl|cat |head |tail |ls |git.*log|git.*status|git.*diff|python3 -c)"; then
    exit 0
fi

# Check for time-limited authorization token (valid for 10 minutes)
# Token lives in the project dir (not /tmp) so it's visible from both
# the Bash sandbox and the hook process.
AUTH_TOKEN="$PROJECT_ROOT/.claude/prd-deploy-auth"
if [ -f "$AUTH_TOKEN" ]; then
    TOKEN_AGE=$(( $(date +%s) - $(stat -c %Y "$AUTH_TOKEN" 2>/dev/null || echo 0) ))
    if [ "$TOKEN_AGE" -lt 600 ]; then
        # Token is fresh (under 10 minutes), allow the deploy
        exit 0
    else
        # Token expired, remove it
        rm -f "$AUTH_TOKEN"
    fi
fi

# Block everything else to PRD (deploys, restarts, scp TO prd, git pull on prd)
jq -n '{
    hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: "PRD DEPLOY BLOCKED: This command targets the production server. You must ask Eugy for explicit permission before deploying to PRD. Develop and test on DEV first, then ask: Ready to deploy to PRD?"
    }
}'
exit 0
