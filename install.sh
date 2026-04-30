#!/usr/bin/env bash
# wpa installer
# Usage: curl -fsSL https://raw.githubusercontent.com/huytv35/wpa/main/install.sh | bash

set -euo pipefail

RAW_URL="https://raw.githubusercontent.com/huytv35/wpa/main/wp-source.py"

# Ưu tiên /usr/local/bin nếu ghi được, fallback về ~/.local/bin
if [ -w "/usr/local/bin" ]; then
    INSTALL_PATH="/usr/local/bin/wpa"
else
    INSTALL_PATH="$HOME/.local/bin/wpa"
    mkdir -p "$HOME/.local/bin"

    # Thêm ~/.local/bin vào PATH nếu chưa có
    for rc in "$HOME/.bashrc" "$HOME/.profile"; do
        if [ -f "$rc" ] && ! grep -q '\.local/bin' "$rc"; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
            echo "Added ~/.local/bin to PATH in $rc"
        fi
    done
fi

# Download (< /dev/null tránh inner curl steal stdin khi chạy qua pipe)
if command -v curl &>/dev/null; then
    curl -fsSL "$RAW_URL" -o "$INSTALL_PATH" < /dev/null
elif command -v wget &>/dev/null; then
    wget -qO "$INSTALL_PATH" "$RAW_URL" < /dev/null
else
    echo "Error: cần curl hoặc wget" >&2
    exit 1
fi

chmod +x "$INSTALL_PATH"
echo "Installed: $INSTALL_PATH"
echo ""
echo "Run now : $INSTALL_PATH /var/www/html"
echo "Next session: wpa /var/www/html"
