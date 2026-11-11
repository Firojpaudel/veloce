#!/usr/bin/env bash
# Registers Veloce Native Messaging Host for Chrome, Chromium, Brave, and Edge on Linux.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_PY="$SCRIPT_DIR/native_host.py"
MANIFEST_NAME="com.veloce.native_host.json"

MANIFEST_CONTENT=$(cat <<EOF
{
  "name": "com.veloce.native_host",
  "description": "Veloce Open Source Native Messaging Host",
  "path": "$HOST_PY",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://*/"
  ]
}
EOF
)

TARGET_DIRS=(
  "$HOME/.config/google-chrome/NativeMessagingHosts"
  "$HOME/.config/chromium/NativeMessagingHosts"
  "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts"
  "$HOME/.config/microsoft-edge/NativeMessagingHosts"
)

for DIR in "${TARGET_DIRS[@]}"; do
  mkdir -p "$DIR"
  echo "$MANIFEST_CONTENT" > "$DIR/$MANIFEST_NAME"
  echo "Registered native host in: $DIR/$MANIFEST_NAME"
done

chmod +x "$HOST_PY"
echo "Veloce Native Messaging Host successfully installed!"
