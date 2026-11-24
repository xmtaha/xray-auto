#!/bin/sh
# ==============================================================================
# Alpine Linux - Xray-Auto Web Panel OpenRC Installer
# ==============================================================================
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Root privileges required."
    exit 1
fi

PANEL_DIR="/opt/xray-panel"
PANEL_PORT="${XRAY_PANEL_PORT:-8080}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

apk add --no-cache python3

mkdir -p "$PANEL_DIR" /etc/xray/panel
cp -r "$SCRIPT_DIR/server.py" "$SCRIPT_DIR/xray_crypto.py" "$SCRIPT_DIR/static" "$PANEL_DIR/"
chmod +x "$PANEL_DIR/server.py"

cat <<EOF > /etc/init.d/xray-panel
#!/sbin/openrc-run

name="xray-panel"
description="Xray-Auto Lightweight Web Panel"

export XRAY_PANEL_PORT="${PANEL_PORT}"
export XRAY_PANEL_DATA="/etc/xray/panel"
export XRAY_CONFIG_PATH="/etc/xray/config.json"

command="/usr/bin/python3"
command_args="${PANEL_DIR}/server.py"
command_background="yes"
pidfile="/run/xray-panel.pid"

output_log="/dev/null"
error_log="/dev/null"

depend() {
    need net
    after xray
}
EOF

chmod +x /etc/init.d/xray-panel
rc-update add xray-panel default
rc-service xray-panel restart

echo "Xray-Auto Web Panel started on port ${PANEL_PORT}."
echo "Default login: admin / admin123 (please change immediately after login)."
