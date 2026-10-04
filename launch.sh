#!/bin/bash
# Sentinel UI V3 — Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║   SENTINEL UI V3  ONLINE      ║"
echo "  ╚═══════════════════════════════╝"
echo ""

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

# Serve UI on all interfaces (for phone access)
echo "  [3/4] Starting UI server on port 8766..."
cd "$SCRIPT_DIR" && python3 -m http.server 8766 --bind 0.0.0.0 > /tmp/sentinel-ui.log 2>&1 &
sleep 1

# Get local IP for phone access
LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i=="src"){print $(i+1);exit}}}')

# Launch Electron app instead of Chrome
echo "  [4/4] Launching Sentinel Electron app..."
cd "$SCRIPT_DIR/sentinal_electron" && ./node_modules/.bin/electron . &

echo ""
echo "  Backend:  http://localhost:8765"
echo "  Ollama:   http://localhost:11434"
echo "  UI:       http://localhost:8766/sentinel_ui_v3.html"
echo ""
echo "  📱 Phone: http://$LOCAL_IP:8766/sentinel_ui_v3.html"
SENTINEL_KEY_VAL=$(grep '^SENTINEL_API_KEY=' "$HOME/.config/sentinel/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')
echo "  🔑 API key: ${SENTINEL_KEY_VAL:-NOT FOUND — check ~/.config/sentinel/.env}"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

wait $BACKEND_PID
