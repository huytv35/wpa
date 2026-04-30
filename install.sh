#!/usr/bin/env bash
# wpa installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/YOURUSER/YOURREPO/main/install.sh)

set -euo pipefail

RAW_URL="https://raw.githubusercontent.com/YOURUSER/YOURREPO/main/wp-source.py"
INSTALL_PATH="/usr/local/bin/wpa"

# Download
if command -v curl &>/dev/null; then
    curl -fsSL "$RAW_URL" -o "$INSTALL_PATH"
elif command -v wget &>/dev/null; then
    wget -qO "$INSTALL_PATH" "$RAW_URL"
else
    echo "Error: cần curl hoặc wget" >&2
    exit 1
fi

chmod +x "$INSTALL_PATH"
echo "Installed: $INSTALL_PATH"
echo ""
echo "Usage: wpa /var/www/html"
