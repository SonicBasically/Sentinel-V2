#!/bin/bash
# Sentinel V2 — Setup & Launcher
# Run once to install deps: bash setup.sh install
# Run to start: bash setup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

install() {
  echo ""
  echo "  SENTINEL UI V3 — Setup"
  echo "  ─────────────────────────────"
  echo "  Installing system dependencies..."
  sudo apt-get install -y xdotool 2>/dev/null || true
  echo "  Installing Python dependencies..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
  echo "  Done. Run 'bash setup.sh' to start the server."
  echo ""
}

start() {
  if [ ! -d "$VENV" ]; then
    echo "  First run detected — installing dependencies..."
    install
  fi
  "$VENV/bin/python" "$SCRIPT_DIR/server.py"
}

case "$1" in
  install) install ;;
  *)       start ;;
esac
