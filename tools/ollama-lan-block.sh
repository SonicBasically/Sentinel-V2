#!/bin/bash
# Blocks the Ollama port (11434) from everything except this machine and the Tailscale interface.
# Installed as root-owned /usr/local/sbin/ollama-lan-block.sh (see ollama-lan-block.service).
# Run with "remove" to take the rules out again.
set -e
PORT=11434
for ipt in iptables ip6tables; do
  command -v "$ipt" >/dev/null || continue
  if [ "$1" = "remove" ]; then
    for r in "-i tailscale0 -j ACCEPT" "-i lo -j ACCEPT" "-j DROP"; do
      while $ipt -C INPUT -p tcp --dport $PORT $r 2>/dev/null; do $ipt -D INPUT -p tcp --dport $PORT $r; done
    done
    continue
  fi
  # DROP goes in first; the two ACCEPT rules are then inserted above it, so they are checked first.
  $ipt -C INPUT -p tcp --dport $PORT -j DROP 2>/dev/null || $ipt -I INPUT -p tcp --dport $PORT -j DROP
  $ipt -C INPUT -p tcp --dport $PORT -i lo -j ACCEPT 2>/dev/null || $ipt -I INPUT -p tcp --dport $PORT -i lo -j ACCEPT
  $ipt -C INPUT -p tcp --dport $PORT -i tailscale0 -j ACCEPT 2>/dev/null || $ipt -I INPUT -p tcp --dport $PORT -i tailscale0 -j ACCEPT
done
