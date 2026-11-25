#!/usr/bin/env bash
# Turn Wednesday on: start the desktop GUI in the background.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/logs/jarvis-gui.pid"

if pgrep -f '[a]pp/main.py gui' >/dev/null 2>&1; then
  echo "Wednesday GUI is already running."
  exit 0
fi

nohup "$ROOT/scripts/launch.sh" gui > "$ROOT/logs/gui-live.log" 2>&1 &
sleep 2

PIDS="$(pgrep -f '[a]pp/main.py gui' | tr '\n' ' ' || true)"
if [[ -z "$PIDS" ]]; then
  echo "Wednesday failed to start. Check $ROOT/logs/gui-live.log" >&2
  exit 1
fi

echo "$PIDS" > "$PIDFILE"
echo "Wednesday is ON (PID: $PIDS)"
echo "Log: $ROOT/logs/gui-live.log"
