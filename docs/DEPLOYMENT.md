# DREAMS Platform - Cloud Deployment Guide

Complete guide for deploying myDREAMS to a VPS with Cloudflare DNS.

## Architecture Overview

```
                    INTERNET
                        │
              ┌─────────┴─────────┐
              │    Cloudflare     │  (Free SSL + CDN + WAF)
              └─────────┬─────────┘
                        │
    ┌───────────────────┼───────────────────┐
    ▼                   ▼                   ▼
api.wncmountain    app.wncmountain    leads.wncmountain
    .homes              .homes              .homes
    │                   │                   │
    └───────────────────┼───────────────────┘
                        │
              ┌─────────▼─────────┐
              │   Caddy Proxy     │  (Auto-HTTPS)
              │   Ports 80/443    │
              └─────────┬─────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Property API    Dashboard      Lead Dashboard
   Flask:5000      Flask:5001     (same :5001)
```

## Prerequisites

- Domain name (wncmountain.homes)
- Cloudflare account (free tier)
- Hetzner/DigitalOcean/Vultr account
- SSH key pair

---

## Phase 2: VPS Setup

### Step 1: Provision VPS

**Recommended: Hetzner CX22**
- Location: Ashburn, VA (ash) or closest to your users
- OS: Ubuntu 24.04 LTS
- Resources: 2 vCPU, 4GB RAM, 40GB SSD
- Cost: ~$4.50/month

1. Create server in Hetzner Cloud Console
2. Add your SSH public key during creation
3. Note the server's IP address

### Step 2: Initial Server Access

```bash
# SSH into your server
ssh root@<VPS_IP>

# Update system
apt update && apt upgrade -y

# Set hostname
hostnamectl set-hostname dreams
```

### Step 3: Run Setup Script

Option A - Direct run:
```bash
# Download and run setup script
curl -sSL https://raw.githubusercontent.com/ipJoseph/myDREAMS/main/deploy/scripts/setup-vps.sh | bash
```

Option B - Manual:
```bash
# Clone repo first
git clone https://github.com/ipJoseph/myDREAMS.git /opt/mydreams

# Run setup
bash /opt/mydreams/deploy/scripts/setup-vps.sh
```

The script will:
- Create `dreams` user
- Install Python 3.11+, Playwright, Caddy
- Clone repository to `/opt/mydreams`
- Create Python virtual environment
- Install systemd services
- Configure sudo permissions

### Step 4: Configure Environment

```bash
# Switch to dreams user
sudo -u dreams -i

# Copy environment template
cp /opt/mydreams/config/.env.example /opt/mydreams/.env

# Edit with your values
nano /opt/mydreams/.env
```

Required variables:
```env
# API Authentication
DREAMS_API_KEY=<generate-secure-key>

# Dashboard Authentication
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<your-password>

# Notion Integration
NOTION_API_KEY=<your-notion-token>
NOTION_PROPERTIES_DB_ID=<your-database-id>

# IDX Site (for property validation)
IDX_BASE_URL=<your-idx-site-url>
IDX_USERNAME=<idx-username>
IDX_PASSWORD=<idx-password>
```

Generate secure API key:
```bash
openssl rand -hex 32
```

### Step 5: Copy Google Service Account (if using Sheets)

```bash
# From your local machine
scp config/service_account.json root@<VPS_IP>:/opt/mydreams/config/

# On server, set permissions
chown dreams:dreams /opt/mydreams/config/service_account.json
chmod 600 /opt/mydreams/config/service_account.json
```

### Step 6: Start Services

```bash
# Start API
sudo systemctl start mydreams-api
sudo systemctl status mydreams-api

# Start Dashboard
sudo systemctl start mydreams-dashboard
sudo systemctl status mydreams-dashboard

# Test locally
curl http://localhost:5000/health
curl http://localhost:5001/
```

---

## Phase 3: DNS & SSL

### Step 1: Transfer DNS to Cloudflare

1. Create free Cloudflare account at cloudflare.com
2. Add your domain: `wncmountain.homes`
3. Cloudflare will scan existing DNS records
4. Update nameservers at GoDaddy to Cloudflare's:
   - Usually something like: `xxx.ns.cloudflare.com`
5. Wait for propagation (usually 1-24 hours)

### Step 2: Create DNS Records

In Cloudflare DNS settings, create these A records:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | @ | `<VPS_IP>` | Proxied (orange) |
| A | api | `<VPS_IP>` | Proxied (orange) |
| A | app | `<VPS_IP>` | Proxied (orange) |
| A | leads | `<VPS_IP>` | Proxied (orange) |
| A | www | `<VPS_IP>` | Proxied (orange) |

### Step 3: Configure SSL

In Cloudflare SSL/TLS settings:
1. Set encryption mode to **Full (Strict)**
2. Enable **Always Use HTTPS**
3. Enable **Automatic HTTPS Rewrites**

### Step 4: Start Caddy

```bash
# Validate Caddyfile
caddy validate --config /etc/caddy/Caddyfile

# Start Caddy
sudo systemctl restart caddy
sudo systemctl status caddy

# Check logs
journalctl -u caddy -f
```

### Step 5: Verify URLs

Test each endpoint:
```bash
curl https://api.wncmountain.homes/health
curl https://app.wncmountain.homes/
curl https://leads.wncmountain.homes/
```

---

## Phase 4: Migration

### Step 1: Export Local Database

On your local machine:
```bash
# Create backup
sqlite3 data/dreams.db ".backup dreams_export.db"

# Compress
gzip dreams_export.db
```

### Step 2: Transfer to VPS

```bash
# Upload to server
scp dreams_export.db.gz root@<VPS_IP>:/opt/mydreams/data/

# On server, decompress and set permissions
cd /opt/mydreams/data
gunzip dreams_export.db.gz
mv dreams_export.db dreams.db
chown dreams:dreams dreams.db
```

### Step 3: Restart Services

```bash
sudo systemctl restart mydreams-api
sudo systemctl restart mydreams-dashboard
```

### Step 4: Update Chrome Extension

1. Open extension settings (gear icon)
2. Update Server URL: `https://api.wncmountain.homes`
3. Enter your API Key
4. Click "Save Settings"
5. Click "Test Connection" to verify

### Step 5: Verify End-to-End

1. Navigate to a Redfin/Zillow property
2. Open extension popup
3. Click "Add to DREAMS"
4. Check https://app.wncmountain.homes to see the property

---

## Phase 5: Cron & Backup

### Step 1: Configure Backups

```bash
# As dreams user
sudo -u dreams -i

# Set backup encryption key
echo 'export BACKUP_ENCRYPTION_KEY="<your-encryption-key>"' >> ~/.bashrc
source ~/.bashrc

# Test backup
/opt/mydreams/deploy/scripts/backup.sh
```

### Step 2: Set Up Backblaze B2 (Optional)

```bash
# Install b2 CLI
pip install b2

# Authenticate (get keys from Backblaze console)
b2 authorize-account <applicationKeyId> <applicationKey>

# Create bucket
b2 create-bucket mydreams-backups allPrivate

# Test upload
/opt/mydreams/deploy/scripts/backup.sh
```

### Step 3: Add Cron Jobs

```bash
# Edit crontab
crontab -e

# Add these lines:
# Daily backup at 11 PM
0 23 * * * /opt/mydreams/deploy/scripts/backup.sh >> /opt/mydreams/logs/backup.log 2>&1

# FUB sync at 6 AM and 6 PM (if using)
0 6,18 * * * cd /opt/mydreams/apps/fub-to-sheets && /opt/mydreams/venv/bin/python sync.py >> /opt/mydreams/logs/fub_sync.log 2>&1

# Property monitor at 5 AM (if using)
0 5 * * * cd /opt/mydreams/apps/property-monitor && /opt/mydreams/venv/bin/python monitor_properties.py >> /opt/mydreams/logs/monitor.log 2>&1
```

### Step 4: Set Up Monitoring

1. Create free UptimeRobot account
2. Add monitors for:
   - `https://api.wncmountain.homes/health` (HTTP check)
   - `https://app.wncmountain.homes/` (HTTP check)
3. Configure email/SMS alerts

---

## Operations Guide

### Deploying Updates

```bash
# SSH to server
ssh root@<VPS_IP>

# Run deploy script
sudo -u dreams /opt/mydreams/deploy/scripts/deploy.sh
```

Or from your local machine:
```bash
# Push changes
git push origin main

# Deploy remotely
ssh root@<VPS_IP> "sudo -u dreams /opt/mydreams/deploy/scripts/deploy.sh"
```

### Viewing Logs

```bash
# API logs
journalctl -u mydreams-api -f

# Dashboard logs
journalctl -u mydreams-dashboard -f

# Caddy logs
journalctl -u caddy -f

# Application logs
tail -f /opt/mydreams/logs/*.log
```

### Restarting Services

```bash
# Restart all
sudo systemctl restart mydreams-api mydreams-dashboard caddy

# Check status
sudo systemctl status mydreams-api mydreams-dashboard caddy
```

### Database Access

```bash
# As dreams user
sudo -u dreams sqlite3 /opt/mydreams/data/dreams.db

# Example queries
.tables
SELECT COUNT(*) FROM properties;
.quit
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs for errors
journalctl -u mydreams-api -n 50
journalctl -u mydreams-dashboard -n 50

# Common issues:
# - Missing .env file
# - Wrong file permissions
# - Python dependency missing
```

### Caddy SSL Errors

```bash
# Check Caddy logs
journalctl -u caddy -n 50

# Verify DNS is pointed correctly
dig api.wncmountain.homes

# Test without Cloudflare proxy temporarily
# (set to DNS only / grey cloud)
```

### Chrome Extension Can't Connect

1. Check API is running: `curl https://api.wncmountain.homes/health`
2. Verify API key matches between extension and server
3. Check Cloudflare isn't blocking the request
4. Look at browser console for errors

### Database Issues

```bash
# Check database integrity
sqlite3 /opt/mydreams/data/dreams.db "PRAGMA integrity_check;"

# Restore from backup
cd /opt/mydreams/backups
ls -la  # Find latest backup
gunzip mydreams_backup_YYYYMMDD.db.gz
cp mydreams_backup_YYYYMMDD.db /opt/mydreams/data/dreams.db
sudo systemctl restart mydreams-api mydreams-dashboard
```

---

## Cost Summary

| Service | Monthly Cost |
|---------|--------------|
| Hetzner CX22 (2GB/2CPU) | $4.50 |
| Cloudflare (DNS + SSL) | Free |
| Backblaze B2 (~1GB) | ~$0.01 |
| UptimeRobot (50 monitors) | Free |
| **Total** | **~$5/month** |

---

## Security Checklist

- [ ] SSH key authentication only (disable password auth)
- [ ] Firewall configured (UFW: allow 22, 80, 443 only)
- [ ] Strong API key generated
- [ ] Strong dashboard password set
- [ ] .env file has restricted permissions (600)
- [ ] Backups encrypted
- [ ] Cloudflare WAF enabled
- [ ] Rate limiting configured

---

*Last updated: January 2026*
