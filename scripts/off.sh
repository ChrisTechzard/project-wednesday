#!/usr/bin/env bash
# Turn Wednesday off: stop the GUI and the headless background service.
# Sends SIGTERM first for a clean shutdown, then SIGKILL if it will not exit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/logs/jarvis-gui.pid"

PIDS="$(pgrep -f '[a]pp/main.py gui' | tr '\n' ' ' || true)"
if [[ -n "$PIDS" ]]; then
  kill $PIDS 2>/dev/null || true
  # Give the app up to 5 seconds to release the mic/camera and exit.
  for _ in 1 2 3 4 5; do
    sleep 1
    ALIVE=""
    for pid in $PIDS; do
      if kill -0 "$pid" 2>/dev/null && [[ "$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ')" != *Z* ]]; then
        ALIVE="$ALIVE $pid"
      fi
    done
    [[ -z "$ALIVE" ]] && break
  done
  if [[ -n "${ALIVE:-}" ]]; then
    kill -9 $ALIVE 2>/dev/null || true
    echo "Wednesday GUI force-stopped (PID:$ALIVE)"
  else
    echo "Wednesday GUI stopped (PID: $PIDS)"
  fi
else
  echo "Wednesday GUI was not running."
fi
rm -f "$PIDFILE"

if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet jarvis.service 2>/dev/null; then
  systemctl --user stop jarvis.service
  echo "Wednesday background service stopped."
fi

echo "Wednesday is OFF."
