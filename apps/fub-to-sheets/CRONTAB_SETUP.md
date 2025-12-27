# FUB to Sheets - Crontab Setup Guide

## The Problem
When running Python scripts via crontab, they don't inherit:
- Your shell environment variables
- Your current working directory
- Your PATH settings

This causes issues with:
- Finding the service_account.json file
- Finding the .env file
- Creating log/cache directories in the wrong location

## The Solution

I've made two changes to fix this:

### 1. Updated Python Script (`fub_to_sheets_v2.py`)

The script now:
- Detects its own directory using `Path(__file__).parent.resolve()`
- Changes to that directory before running
- Loads the .env file from the script directory
- Resolves the service_account.json path relative to the script directory

### 2. Created Wrapper Script (`run_fub_sync.sh`)

This bash wrapper:
- Changes to the correct directory
- Explicitly loads environment variables from .env
- Runs Python with full paths
- Passes through exit codes

## Setup Instructions

### Step 1: Make the wrapper script executable
```bash
cd "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2"
chmod +x run_fub_sync.sh
```

### Step 2: Edit your crontab
```bash
crontab -e
```

### Step 3: Add cron job using the wrapper script

For daily run at 8:00 AM:
```cron
0 8 * * * /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/run_fub_sync.sh >> /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/logs/cron.log 2>&1
```

For hourly runs:
```cron
0 * * * * /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/run_fub_sync.sh >> /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/logs/cron.log 2>&1
```

For every 30 minutes:
```cron
*/30 * * * * /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/run_fub_sync.sh >> /home/bigeug/Insync/joseph@integritypursuits.com/Google\ Drive/fub-sheets-v2/logs/cron.log 2>&1
```

**Note:** Escape spaces in the path with backslashes or quote the entire path.

### Alternative: Using quoted path
```cron
0 8 * * * "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/run_fub_sync.sh" >> "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/logs/cron.log" 2>&1
```

## Testing the Cron Job

### Test the wrapper script manually first:
```bash
cd "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2"
./run_fub_sync.sh
```

### Test with the same environment as cron:
```bash
env -i /bin/bash -c 'cd "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2" && ./run_fub_sync.sh'
```

This runs with a clean environment like cron does.

### Check cron logs:
```bash
# View the cron output log
tail -f "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/logs/cron.log"

# View the Python script logs
tail -f "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/logs/"*.log
```

### Verify cron is running:
```bash
# Check system cron log for your user
grep CRON /var/log/syslog | grep bigeug | tail -20
```

## Troubleshooting

### If you still get "service_account.json not found":

1. **Check the file exists:**
   ```bash
   ls -la "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/service_account.json"
   ```

2. **Check the .env file:**
   ```bash
   cat "/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/.env" | grep GOOGLE_SERVICE_ACCOUNT_FILE
   ```

3. **Set absolute path in .env:**
   If you have issues, set the full path in your .env file:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=/home/bigeug/Insync/joseph@integritypursuits.com/Google Drive/fub-sheets-v2/service_account.json
   ```

### If cron doesn't run at all:

1. **Check crontab syntax:**
   ```bash
   crontab -l
   ```

2. **Check cron service is running:**
   ```bash
   sudo systemctl status cron
   ```

3. **Check for errors in system log:**
   ```bash
   sudo tail -f /var/log/syslog
   ```

## Alternative: Using systemd timer (more modern approach)

If you prefer systemd over cron, I can help you set that up instead. Systemd timers have better logging and error handling.

Let me know if you need help with that!
