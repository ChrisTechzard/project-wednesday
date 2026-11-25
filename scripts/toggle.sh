#!/usr/bin/env bash
# Toggle Wednesday: off if anything is running, on otherwise.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if pgrep -f '[a]pp/main.py gui' >/dev/null 2>&1 || \
   { command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet jarvis.service 2>/dev/null; }; then
  exec "$ROOT/scripts/off.sh"
else
  exec "$ROOT/scripts/on.sh"
fi
