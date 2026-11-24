#!/bin/bash
# Sentinel V2 — UI file server (run by systemd: sentinel-ui.service).
# Serves ONLY the ui/ folder (symlinks to the UI files), never the project root.
# Binds localhost and the Tailscale IPv4 address on port 8766.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$SCRIPT_DIR/../ui"
cd "$UI_DIR" || exit 1

TS_IP="$(tailscale ip -4 2>/dev/null | head -n1)"
if ! [[ "$TS_IP" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  TS_IP=""
  echo "[ui] Tailscale IPv4 unavailable; serving localhost only."
fi

python3 -m http.server 8766 --bind 127.0.0.1 &
PIDS="$!"
if [ -n "$TS_IP" ]; then
  python3 -m http.server 8766 --bind "$TS_IP" &
  PIDS="$PIDS $!"
fi

# If either listener dies, stop both so systemd restarts the unit cleanly.
trap 'kill $PIDS 2>/dev/null' TERM INT
wait -n
kill $PIDS 2>/dev/null
wait
exit 1
