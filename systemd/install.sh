#!/bin/bash
# Sentinel V2 — install the systemd USER services (no sudo needed).
# Run once from the repo:  bash systemd/install.sh
# Afterwards launch.sh restarts these units instead of spawning its own copies.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR/sentinel-backend.service" "$SCRIPT_DIR/sentinel-ui.service" "$UNIT_DIR/"
echo "  Copied unit files to $UNIT_DIR"

systemctl --user daemon-reload
systemctl --user enable sentinel-backend.service sentinel-ui.service
echo "  Enabled sentinel-backend and sentinel-ui (start at login)."
echo "  Start now with: systemctl --user restart sentinel-backend sentinel-ui"
