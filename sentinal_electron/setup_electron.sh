#!/bin/bash
# Sentinel UI V3 — Electron Setup
# Run once: bash setup_electron.sh
# Then launch: bash setup_electron.sh run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install() {
  echo ""
  echo "  Installing Electron..."
  cd "$SCRIPT_DIR"

  # Install Node dependencies
  npm install --save-dev electron electron-builder

  echo "  Done! Run with: bash setup_electron.sh run"
  echo ""
}

run() {
  echo ""
  echo "  Launching Sentinel UI V3..."
  cd "$SCRIPT_DIR"
  npx electron .
}

build() {
  echo ""
  echo "  Building Sentinel UI V3 AppImage..."
  cd "$SCRIPT_DIR"
  npx electron-builder --linux AppImage
  echo ""
  echo "  Build complete! Find it in: $SCRIPT_DIR/dist/"
}

case "$1" in
  run)   run ;;
  build) build ;;
  *)     install ;;
esac
