#!/bin/bash
# Sentinel V2 — Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║   SENTINEL V2  ONLINE      ║"
echo "  ╚═══════════════════════════════╝"
echo ""

TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -n1)
if [[ "$TAILSCALE_IP" =~ ^100\.([6-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  echo "  Network: localhost + Tailscale ($TAILSCALE_IP)"
else
  TAILSCALE_IP=""
  echo "  WARNING: Tailscale IPv4 unavailable; services will use localhost only."
fi

# Kill everything that might conflict
echo "  [0/4] Clearing ports and processes..."
pkill -9 -f "ollama" 2>/dev/null
pkill -9 -f "server.py" 2>/dev/null
pkill -9 -f "http.server 8766" 2>/dev/null
fuser -k 8765/tcp 2>/dev/null
fuser -k 8766/tcp 2>/dev/null
fuser -k 11434/tcp 2>/dev/null
sleep 2
echo "        Done."

# Start backend and wait for it
echo "  [1/4] Starting backend server..."
bash "$SCRIPT_DIR/setup.sh" &
BACKEND_PID=$!
echo -n "        Waiting for backend"
for i in $(seq 1 20); do
  sleep 1
  if curl -s http://localhost:8765/ > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  echo -n "."
done

# Start Ollama on all interfaces and wait for it
echo "  [2/4] Starting Ollama..."
OLLAMA_HOST=0.0.0.0 OLLAMA_ORIGINS="*" /snap/ollama/current/bin/ollama serve > /tmp/ollama.log 2>&1 &
echo -n "        Waiting for Ollama"
for i in $(seq 1 20); do
  sleep 1
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  echo -n "."
done

# Electron starts the UI server on localhost and the Tailscale address.
# Launch Electron app instead of Chrome
echo "  [3/3] Launching Sentinel Electron app and UI listeners..."
cd "$SCRIPT_DIR/sentinal_electron" && ./node_modules/.bin/electron . &

echo ""
echo "  Backend:  http://localhost:8765"
echo "  Ollama:   http://localhost:11434"
echo "  UI:       http://localhost:8766/sentinel_v2.html"
echo ""
if [[ -n "$TAILSCALE_IP" ]]; then
  echo "  📱 Phone (Tailscale): http://$TAILSCALE_IP:8766/sentinel_v2.html"
else
  echo "  📱 Phone access unavailable until Tailscale is connected."
fi
SENTINEL_KEY_VAL=$(grep '^SENTINEL_API_KEY=' "$HOME/.config/sentinel/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')
echo "  🔑 API key: ${SENTINEL_KEY_VAL:-NOT FOUND — check ~/.config/sentinel/.env}"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

wait $BACKEND_PID
