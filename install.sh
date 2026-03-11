#!/bin/bash
set -e

# ──────────────────────────────────────────────────────────────
# Lightline Node — One-Line Installer (Legacy)
# Prefer: sudo bash -c "$(curl -sL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh)" @ install
# ──────────────────────────────────────────────────────────────

echo "This script is deprecated. Use the new installer instead:"
echo ""
echo '  sudo bash -c "$(curl -sL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh)" @ install'
echo ""
echo "Running it now..."
echo ""

curl -sL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh | bash -s install
