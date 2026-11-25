#!/usr/bin/env bash
# Install/refresh Wednesday in the project directory. User-level only: no sudo required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
MODELS="$ROOT/models"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/Wednesday.desktop"
LOG_DIR="$ROOT/logs"

log() { printf '\n[wednesday-install] %s\n' "$*"; }

mkdir -p "$MODELS" "$LOG_DIR" "$DESKTOP_DIR"

log "Creating/refreshing Python virtual environment"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip -q

log "Installing Python dependencies (this can take several minutes)"
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"

echo "NOTE: Optional offline OCR (screen text extraction) is not installed by default."
echo "      To enable it later: $VENV/bin/python -m pip install -r $ROOT/requirements-optional.txt"

log "Verifying local Ollama"
if command -v ollama >/dev/null 2>&1; then
  if ! ollama list >/dev/null 2>&1; then
    echo "WARNING: Ollama is installed but not responding. Start it with 'systemctl start ollama'." >&2
  else
    echo "Ollama models available:"
    ollama list
  fi
else
  echo "WARNING: Ollama not found. Install it from https://ollama.com to enable AI chat." >&2
fi

log "Checking model files"
MODEL_FILES=(
  "embedding_model.onnx"
  "melspectrogram.onnx"
  "hey_jarvis_v0.1.onnx"
  "en_US-lessac-medium.onnx"
  "en_US-lessac-medium.onnx.json"
)
MISSING=0
for file in "${MODEL_FILES[@]}"; do
  if [[ ! -s "$MODELS/$file" ]]; then
    echo "MISSING: $file"
    MISSING=1
  fi
done
if [[ "$MISSING" -eq 1 ]]; then
  echo "Some model files are missing. Re-run the model download commands in docs/INSTALL.md." >&2
fi

log "Installing desktop launcher"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Wednesday
GenericName=Personal AI Assistant
Comment=Offline-capable personal AI workstation
Exec="$ROOT/scripts/launch.sh" gui
Icon=$ROOT/assets/wednesday.svg
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=true
EOF
chmod +x "$DESKTOP_FILE"
chmod +x "$ROOT/scripts/launch.sh" "$ROOT/scripts/uninstall.sh" "$ROOT/scripts/install.sh"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

log "Running health check"
"$VENV/bin/python" app/main.py doctor > "$LOG_DIR/doctor.json" 2>&1 || true
cat "$LOG_DIR/doctor.json"

log "Installation complete. Launch with: $ROOT/scripts/launch.sh"
