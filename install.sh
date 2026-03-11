#!/bin/bash
set -e

# ──────────────────────────────────────────────────────────────
# Lightline Node — One-Line Installer
# Usage: sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/install.sh)"
# ──────────────────────────────────────────────────────────────

REPO="https://github.com/Lightline-Panel/lightline-node.git"
INSTALL_DIR="/opt/lightline-node"

log()  { echo -e "\033[1;34m[LIGHTLINE-NODE]\033[0m $1"; }
ok()   { echo -e "\033[1;32m[✓]\033[0m $1"; }
err()  { echo -e "\033[1;31m[✗]\033[0m $1"; exit 1; }

# Check root
if [ "$EUID" -ne 0 ]; then
  err "Please run as root: sudo bash install.sh"
fi

# Install Docker if needed
if ! command -v docker &>/dev/null; then
  log "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  ok "Docker installed"
fi

# Install Git if needed
if ! command -v git &>/dev/null; then
  log "Installing Git..."
  apt-get update -qq && apt-get install -y -qq git
  ok "Git installed"
fi

# Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
  log "Updating existing installation..."
  cd "$INSTALL_DIR"
  git pull origin main
else
  log "Cloning lightline-node..."
  git clone "$REPO" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# Configure .env if not present
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  log "Setting up configuration..."
  echo ""
  echo "  Lightline Node — Configuration"
  echo "  ==============================="
  echo ""

  read -p "  Outline API URL (e.g. https://127.0.0.1:12345/AbCdEf): " OUTLINE_URL
  read -p "  Outline API Key (leave blank if included in URL): " OUTLINE_KEY
  read -p "  Node authentication token (from panel): " NODE_AUTH_TOKEN
  read -p "  Node port [9090]: " NODE_PORT
  NODE_PORT=${NODE_PORT:-9090}

  cat > "$ENV_FILE" <<EOF
# Lightline Node Configuration
NODE_PORT=$NODE_PORT
NODE_HOST=0.0.0.0
NODE_TOKEN=$NODE_AUTH_TOKEN

OUTLINE_API_URL=$OUTLINE_URL
OUTLINE_API_KEY=$OUTLINE_KEY

SSL_CERT_FILE=/var/lib/lightline-node/cert.pem
SSL_KEY_FILE=/var/lib/lightline-node/key.pem
EOF

  ok "Configuration saved to $ENV_FILE"
fi

# Build and start
log "Building and starting lightline-node..."
docker compose up -d --build

echo ""
ok "Lightline Node installed and running!"
echo ""
echo "  Port:    $(grep NODE_PORT $ENV_FILE | cut -d= -f2)"
echo "  Config:  $ENV_FILE"
echo "  Logs:    docker compose -f $INSTALL_DIR/docker-compose.yml logs -f"
echo ""
echo "  Add this node in the Lightline Panel with:"
echo "    IP:       $(curl -s ifconfig.me 2>/dev/null || echo '<this-server-ip>')"
echo "    Port:     $(grep NODE_PORT $ENV_FILE | cut -d= -f2)"
echo "    API Key:  $(grep NODE_TOKEN $ENV_FILE | cut -d= -f2)"
echo ""
