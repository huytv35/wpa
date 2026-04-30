#!/usr/bin/env bash
# wpa installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/huytv35/wpa/main/install.sh)

set -euo pipefail

RAW_URL="https://raw.githubusercontent.com/huytv35/wpa/main/wp-source.py"
INSTALL_PATH="/usr/local/bin/wpa"
TMP_FILE="$(mktemp)"

# Download to temp file first
if command -v curl &>/dev/null; then
    curl -fsSL "$RAW_URL" -o "$TMP_FILE"
elif command -v wget &>/dev/null; then
    wget -qO "$TMP_FILE" "$RAW_URL"
else
    echo "Error: cần curl hoặc wget" >&2
    exit 1
fi

chmod +x "$TMP_FILE"

# Install (dùng sudo nếu cần)
if [ -w "$(dirname "$INSTALL_PATH")" ]; then
    mv "$TMP_FILE" "$INSTALL_PATH"
else
    sudo mv "$TMP_FILE" "$INSTALL_PATH"
fi
echo "Installed: $INSTALL_PATH"
echo ""
echo "Usage: wpa /var/www/html"
