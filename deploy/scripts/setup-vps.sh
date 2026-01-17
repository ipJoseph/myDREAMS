#!/bin/bash
# DREAMS Platform - VPS Initial Setup Script
# Run this on a fresh Ubuntu 22.04/24.04 VPS
#
# Usage: curl -sSL <raw-github-url> | sudo bash
# Or:    sudo bash setup-vps.sh
#
# This script:
# 1. Creates 'dreams' user
# 2. Installs Python 3.11+, Playwright dependencies, Caddy
# 3. Clones the repository
# 4. Sets up Python virtual environment
# 5. Installs systemd services
# 6. Configures Caddy

set -e

# Configuration
DREAMS_USER="dreams"
INSTALL_DIR="/opt/mydreams"
REPO_URL="https://github.com/ipJoseph/myDREAMS.git"
PYTHON_VERSION="3.11"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (use sudo)"
fi

log "=========================================="
log "DREAMS Platform VPS Setup"
log "=========================================="

# Update system
log "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install essential packages
log "Installing essential packages..."
apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    sqlite3 \
    jq

# Install Python 3.11+
log "Installing Python ${PYTHON_VERSION}..."
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-venv \
    python${PYTHON_VERSION}-dev \
    python3-pip

# Set Python 3.11 as default python3 alternative
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1

# Install Playwright system dependencies
log "Installing Playwright dependencies..."
apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0

# Install Caddy
log "Installing Caddy..."
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

# Create dreams user
log "Creating '$DREAMS_USER' user..."
if id "$DREAMS_USER" &>/dev/null; then
    warn "User '$DREAMS_USER' already exists"
else
    useradd -m -s /bin/bash "$DREAMS_USER"
    log "User '$DREAMS_USER' created"
fi

# Create installation directory
log "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/backups"
mkdir -p /var/log/caddy

# Clone repository
log "Cloning repository..."
if [[ -d "$INSTALL_DIR/.git" ]]; then
    warn "Repository already exists, pulling latest..."
    cd "$INSTALL_DIR"
    git fetch origin
    git reset --hard origin/main
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Set ownership
chown -R "$DREAMS_USER:$DREAMS_USER" "$INSTALL_DIR"
chown -R caddy:caddy /var/log/caddy

# Create Python virtual environment
log "Creating Python virtual environment..."
sudo -u "$DREAMS_USER" python${PYTHON_VERSION} -m venv "$INSTALL_DIR/venv"

# Install Python dependencies
log "Installing Python dependencies..."
sudo -u "$DREAMS_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$DREAMS_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Install Playwright browsers
log "Installing Playwright browsers..."
sudo -u "$DREAMS_USER" "$INSTALL_DIR/venv/bin/playwright" install chromium
sudo -u "$DREAMS_USER" "$INSTALL_DIR/venv/bin/playwright" install-deps

# Install systemd services
log "Installing systemd services..."
cp "$INSTALL_DIR/deploy/systemd/mydreams-api.service" /etc/systemd/system/
cp "$INSTALL_DIR/deploy/systemd/mydreams-dashboard.service" /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable services (don't start yet - need .env first)
systemctl enable mydreams-api
systemctl enable mydreams-dashboard

# Install Caddyfile
log "Installing Caddy configuration..."
cp "$INSTALL_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile

# Make scripts executable
chmod +x "$INSTALL_DIR/deploy/scripts/"*.sh

# Create sudoers entry for dreams user to restart services
log "Configuring sudo permissions..."
cat > /etc/sudoers.d/dreams << 'EOF'
# Allow dreams user to restart DREAMS services without password
dreams ALL=(ALL) NOPASSWD: /bin/systemctl restart mydreams-api
dreams ALL=(ALL) NOPASSWD: /bin/systemctl restart mydreams-dashboard
dreams ALL=(ALL) NOPASSWD: /bin/systemctl status mydreams-api
dreams ALL=(ALL) NOPASSWD: /bin/systemctl status mydreams-dashboard
EOF
chmod 440 /etc/sudoers.d/dreams

log "=========================================="
log "VPS Setup Complete!"
log "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Create .env file with your secrets:"
echo "   sudo -u dreams nano $INSTALL_DIR/.env"
echo ""
echo "2. Copy your .env.example and fill in values:"
echo "   sudo -u dreams cp $INSTALL_DIR/config/.env.example $INSTALL_DIR/.env"
echo ""
echo "3. If using Google Sheets, copy service_account.json:"
echo "   sudo -u dreams nano $INSTALL_DIR/config/service_account.json"
echo ""
echo "4. Start services:"
echo "   sudo systemctl start mydreams-api"
echo "   sudo systemctl start mydreams-dashboard"
echo ""
echo "5. Start Caddy (after DNS is configured):"
echo "   sudo systemctl restart caddy"
echo ""
echo "6. Check service status:"
echo "   sudo systemctl status mydreams-api"
echo "   sudo systemctl status mydreams-dashboard"
echo "   sudo systemctl status caddy"
echo ""
echo "7. View logs:"
echo "   journalctl -u mydreams-api -f"
echo "   journalctl -u mydreams-dashboard -f"
echo ""
log "Installation directory: $INSTALL_DIR"
log "Logs directory: $INSTALL_DIR/logs"
