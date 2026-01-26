---
description: Deploy to production VPS
---

# Deploy

Deploy myDREAMS from DEV to PRD.

## Instructions

Follow the deploy skill guidelines in `.claude/skills/deploy.md`.

## Pre-Deployment Checks

1. Verify no uncommitted changes (`git status`)
2. Check tests pass (if applicable)
3. Ensure debug mode disabled
4. CHANGELOG.md updated

## Deployment Steps

1. Commit and push local changes
2. SSH to PRD and pull
3. Restart services
4. Verify deployment
5. Monitor logs for errors

## Environments

| Env | Path | Host |
|-----|------|------|
| DEV | `/home/bigeug/myDREAMS` | localhost |
| PRD | `/opt/mydreams` | 178.156.221.10 |

## Argument

$ARGUMENTS - Optional: "check" (status only), "db" (include database sync), "rollback" (revert)
