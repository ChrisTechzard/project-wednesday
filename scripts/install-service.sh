#!/usr/bin/env bash
# Install (but do not enable) a user-level systemd service for headless Wednesday.
# This never touches the system service directory and requires no sudo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/jarvis.service"
ENABLE=0
START=0

usage() {
  cat <<EOF
Usage: scripts/install-service.sh [--enable] [--start]

Installs ~/.config/systemd/user/jarvis.service, a user-level service that runs
Wednesday in headless wake-word mode (the GUI is not required).

  --enable  also enable the service to start at login
  --start   also start the service now

By default the unit is installed but NOT enabled or started.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) ENABLE=1 ;;
    --start) START=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=J.A.R.V.I.S. personal AI assistant (headless voice mode)
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONPATH=$ROOT
ExecStart=$ROOT/scripts/launch.sh voice
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo "[jarvis-service] Installed $UNIT_FILE"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$UNIT_FILE" 2>/dev/null || true
  fi
  if [[ "$ENABLE" -eq 1 ]]; then
    systemctl --user enable jarvis.service
    echo "[jarvis-service] Enabled at login"
  fi
  if [[ "$START" -eq 1 ]]; then
    systemctl --user start jarvis.service
    echo "[jarvis-service] Started"
  fi
  echo "[jarvis-service] Status:"
  systemctl --user status jarvis.service --no-pager 2>&1 | head -20 || true
else
  echo "WARNING: systemctl not available; unit file created but not activated." >&2
fi

echo
echo "Useful commands:"
echo "  systemctl --user start|stop|restart|status jarvis.service"
echo "  journalctl --user -u jarvis.service -f"
echo "  systemctl --user disable jarvis.service   # stop autostart"
