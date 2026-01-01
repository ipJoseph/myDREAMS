# myDREAMS Utility Scripts

## Backup & Restore

### backup-secrets.sh
Backs up critical non-versioned files to Google Drive:
- `.env`
- `service_account.json`
- `session.json` (if exists)

Usage:
```bash
./scripts/backup-secrets.sh
```

Run automatically via cron (see crontab setup).

### restore-secrets.sh
Restores secrets from Google Drive backup.

Usage:
```bash
./scripts/restore-secrets.sh
```

Use this when setting up a new system or recovering from data loss.

## Backup Location
Google Drive (Integrity Pursuits): `myDREAMS-Backups/secrets/`

Includes versioned archives with timestamps for recovery.
