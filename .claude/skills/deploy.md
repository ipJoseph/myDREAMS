# Deploy Skill

Deploy myDREAMS from DEV (localhost) to PRD (VPS).

## Activation

Use this skill when asked to:
- Deploy to production
- Push changes to VPS
- Update the live site
- Sync code to PRD

## Environment Details

| Environment | Path | Host | User |
|-------------|------|------|------|
| DEV | `/home/bigeug/myDREAMS` | localhost | bigeug |
| PRD | `/opt/mydreams` | 178.156.221.10 | root (run as dreams) |

## Domain & URLs

- Dashboard: https://app.wncmountain.homes
- API: https://api.wncmountain.homes

## Pre-Deployment Checklist

Before deploying, verify:

- [ ] All changes committed locally
- [ ] No uncommitted changes (`git status` clean)
- [ ] Tests pass (if applicable)
- [ ] No debug mode enabled in code
- [ ] No hardcoded localhost URLs
- [ ] CHANGELOG.md updated

## Deployment Commands

### 1. Standard Deploy (Code Only)

```bash
# Commit and push local changes
git add -A && git commit -m "Description" && git push

# Pull to PRD and restart services
ssh root@178.156.221.10 'git -C /opt/mydreams pull && systemctl restart mydreams-api mydreams-dashboard'

# Verify services running
ssh root@178.156.221.10 'systemctl status mydreams-api mydreams-dashboard'
```

### 2. Deploy with Database Sync

```bash
# Push code first
git push

# Sync database to PRD
scp /home/bigeug/myDREAMS/data/dreams.db root@178.156.221.10:/opt/mydreams/data/dreams.db

# Set permissions and restart
ssh root@178.156.221.10 'chown dreams:dreams /opt/mydreams/data/dreams.db && systemctl restart mydreams-api mydreams-dashboard'
```

### 3. Check PRD Status

```bash
# Service status
ssh root@178.156.221.10 'systemctl status mydreams-api mydreams-dashboard'

# Recent logs
ssh root@178.156.221.10 'journalctl -u mydreams-api -n 50'
ssh root@178.156.221.10 'journalctl -u mydreams-dashboard -n 50'

# Check what version is running
ssh root@178.156.221.10 'git -C /opt/mydreams log --oneline -3'
```

### 4. Rollback

```bash
# Revert to previous commit on PRD
ssh root@178.156.221.10 'git -C /opt/mydreams reset --hard HEAD~1 && systemctl restart mydreams-api mydreams-dashboard'
```

## Deployment Workflow

1. **Verify** local changes are ready
   ```bash
   git status
   git diff --stat main
   ```

2. **Commit** if not already done
   ```bash
   git add -A
   git commit -m "Brief description of changes"
   ```

3. **Push** to remote
   ```bash
   git push
   ```

4. **Pull** on PRD
   ```bash
   ssh root@178.156.221.10 'git -C /opt/mydreams pull'
   ```

5. **Restart** services
   ```bash
   ssh root@178.156.221.10 'systemctl restart mydreams-api mydreams-dashboard'
   ```

6. **Verify** deployment
   ```bash
   # Check services
   ssh root@178.156.221.10 'systemctl status mydreams-api --no-pager'

   # Test API
   curl -s https://api.wncmountain.homes/health

   # Test Dashboard
   curl -s -o /dev/null -w "%{http_code}" https://app.wncmountain.homes/
   ```

7. **Monitor** for errors
   ```bash
   ssh root@178.156.221.10 'journalctl -u mydreams-dashboard -f'
   ```

## Common Issues

### Service Won't Start
```bash
# Check for Python errors
ssh root@178.156.221.10 'journalctl -u mydreams-dashboard -n 100 | grep -i error'

# Check if port is in use
ssh root@178.156.221.10 'ss -tlnp | grep 5001'
```

### Permission Errors
```bash
# Fix ownership
ssh root@178.156.221.10 'chown -R dreams:dreams /opt/mydreams/data'
```

### Database Locked
```bash
# Check for stale connections
ssh root@178.156.221.10 'fuser /opt/mydreams/data/dreams.db'
```

## Safety Rules

1. **NEVER** push directly without testing locally
2. **ALWAYS** commit with meaningful message
3. **VERIFY** services after restart
4. **BACKUP** database before major schema changes
5. **MONITOR** logs after deploy for errors
6. **ROLLBACK** immediately if errors detected

## Post-Deployment

After successful deployment:
1. Verify functionality manually
2. Check logs for errors
3. Update deployment notes if needed
4. Notify stakeholders if major changes
