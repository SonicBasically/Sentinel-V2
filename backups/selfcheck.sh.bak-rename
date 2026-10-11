#!/bin/bash
# Sentinel self-check: syntax checks for the backend and UI, plus a live smoke test.
# Read-only. Prints status codes only, never the API key.
# Usage: bash tools/selfcheck.sh
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
fail=0

echo "== Python syntax =="
for f in server.py backend/ollama_brain.py backend/main.py backend/security_shield.py; do
  [ -f "$f" ] || continue
  if python3 -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" "$f" 2>/tmp/selfcheck.err; then
    echo "ok    $f"
  else
    echo "FAIL  $f"; tail -n 4 /tmp/selfcheck.err; fail=1
  fi
done

echo "== UI JavaScript syntax =="
if python3 - <<'PY'
import re, sys
s = open('sentinel_ui_v3.html', encoding='utf-8').read()
blocks = re.findall(r'<script[^>]*>(.*?)</script>', s, re.S)
if not blocks:
    print('no <script> block found'); sys.exit(1)
open('/tmp/selfcheck_ui.js', 'w', encoding='utf-8').write(max(blocks, key=len))
PY
then
  if node --check /tmp/selfcheck_ui.js 2>/tmp/selfcheck.err; then
    echo "ok    sentinel_ui_v3.html"
  else
    echo "FAIL  sentinel_ui_v3.html"; head -n 6 /tmp/selfcheck.err; fail=1
  fi
else
  echo "FAIL  could not extract UI script"; fail=1
fi

echo "== Mode documents =="
for m in core assistant sysadmin developer security; do
  if [ -f "modes/$m.md" ]; then echo "ok    modes/$m.md ($(wc -c < modes/$m.md) bytes)"; else echo "MISSING modes/$m.md"; fi
done

echo "== Live backend (status codes only) =="
KEY=$(grep '^SENTINEL_API_KEY=' "$HOME/.config/sentinel/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8765/)
echo "GET /                 -> $code"
if [ "$code" = "000" ]; then
  echo "backend is not running (fine if Thomas has not started it)"
elif [ -n "$KEY" ]; then
  for path in /system/info /modes; do
    c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -H "X-Api-Key: $KEY" "http://localhost:8765$path")
    echo "GET $path (authed) -> $c"
  done
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8765/system/info)
  echo "GET /system/info (no key) -> $c (expect 401)"
else
  echo "no API key found in ~/.config/sentinel/.env, skipped authed checks"
fi
echo "(404 on /modes just means the backend has not been restarted since that route was added)"

echo
if [ "$fail" = "0" ]; then echo "SELFCHECK PASSED"; else echo "SELFCHECK FAILED"; exit 1; fi
