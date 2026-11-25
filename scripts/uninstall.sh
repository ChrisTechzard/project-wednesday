#!/usr/bin/env bash
# Remove Wednesday's launcher and local user data. Requires explicit --yes.
# The source checkout is deliberately left untouched.
set -euo pipefail

DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/Wednesday.desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Jarvis"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/Jarvis"
UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/jarvis.service"

if [[ "${1:-}" != "--yes" ]]; then
  cat <<'EOF'
This will remove:
  - the Wednesday desktop launcher
  - the jarvis.service user unit
  - Wednesday configuration and memory under ~/.config/Jarvis
  - Wednesday data under ~/.local/share/Jarvis

It will NOT remove:
  - this source checkout
  - the virtual environment, models, logs or screenshots inside it
  - Ollama or any system packages
  - your other projects or personal files

To proceed, run: scripts/uninstall.sh --yes
EOF
  exit 1
fi

echo "[wednesday-uninstall] Removing desktop launcher and user unit"
rm -f "$DESKTOP_FILE" "$UNIT_FILE"

echo "[wednesday-uninstall] Removing configuration and memory"
rm -rf "$CONFIG_DIR" "$DATA_DIR"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload 2>/dev/null || true
fi

echo "[wednesday-uninstall] Done. Delete the source checkout manually if you no longer need it."
