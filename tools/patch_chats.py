#!/usr/bin/env python3
"""One-off patch: saved-chats panel on the left, command sidebar on the right.
Every replacement asserts the old text appears exactly once. Backups were made first."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "sentinel_v2.html"
SERVER = ROOT / "server.py"
GIT = ROOT / ".gitignore"
T = Path(__file__).resolve().parent


def once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT: {label}: expected 1 match, found {n}. Nothing written.")
    return text.replace(old, new)


def between(text, start, end, new, label, max_lines):
    if text.count(start) != 1 or text.count(end) != 1:
        sys.exit(f"ABORT: {label}: start/end markers not unique. Nothing written.")
    a, b = text.index(start), text.index(end)
    if b < a or text[a:b].count("\n") > max_lines:
        sys.exit(f"ABORT: {label}: block is not the size expected. Nothing written.")
    return text[:a] + new + text[b:]


h = HTML.read_text(encoding="utf-8")
css = (T / "chats_new.css").read_text(encoding="utf-8")
markup = (T / "chats_new.html").read_text(encoding="utf-8")
js = (T / "chats_new.js").read_text(encoding="utf-8")

# ── CSS ──
h = once(h, "#main{display:grid;grid-template-columns:236px 1fr;",
         "#main{display:grid;grid-template-columns:250px 1fr 236px;", "main grid")
h = once(h, "/* Safe area for notches */", css + "/* Safe area for notches */", "css insert")

# ── HTML ──
h = once(h, '<div id="main">\n  <div id="sidebar">',
         '<div id="main">\n' + markup + '  <div id="sidebar">', "chathist markup")
h = once(h, '<button class="stab" id="tab-history" onclick="showTab(\'history\')" title="Past sessions" aria-label="Past sessions"><span class="stab-ic">↺</span><span class="stab-lb">hist</span></button>\n      ',
         "", "hist tab")
h = once(h, '    <div class="sidebar-panel" id="panel-history">\n      <div class="sb-sec">Past Sessions</div>\n      <div id="hist-list"></div>\n    </div>\n',
         "", "hist panel")
h = once(h, '<button id="mobile-menu-btn" onclick="toggleSidebar()">☰</button>',
         '<button id="mobile-menu-btn" onclick="toggleChats()" aria-label="Saved chats" title="Saved chats">☰</button>'
         '<button id="mobile-cmd-btn" onclick="toggleSidebar()" aria-label="Commands" title="Commands">⌘</button>',
         "mobile buttons")
h = once(h, '<div id="sidebar-overlay" onclick="toggleSidebar()"></div>',
         '<div id="sidebar-overlay" onclick="closeDrawers()"></div>', "overlay")

# ── JS ──
h = once(h, "  if(tab==='history') renderHistory();\n", "", "showTab history")
h = between(h, "function saveSession(){", "var ACTION_SCHEMA=", js, "session block", 40)
h = once(h, "function clearChat(){\n  saveSession();\n  msgsEl.innerHTML='';chatHistory=[];\n  addMsg('ai','History cleared.');\n  stL.textContent='ready';stR.textContent='';\n}",
         "function clearChat(){ newChat(); }", "clearChat")
h = once(h, "if(window.speechSynthesis) window.speechSynthesis.getVoices();\nrenderHistory();\n",
         "if(window.speechSynthesis) window.speechSynthesis.getVoices();\nchatMigrateOld().then(loadChatList);\n", "init")
h = once(h, "function toggleSidebar() {\n  var sb = document.getElementById('sidebar');\n  var ov = document.getElementById('sidebar-overlay');\n  sb.classList.toggle('mobile-open');\n  ov.classList.toggle('show');\n}",
         "function toggleSidebar() { toggleDrawer('sidebar'); }\n"
         "function toggleChats() { toggleDrawer('chathist'); }\n"
         "function closeDrawers() {\n"
         "  document.getElementById('sidebar').classList.remove('mobile-open');\n"
         "  document.getElementById('chathist').classList.remove('mobile-open');\n"
         "  document.getElementById('sidebar-overlay').classList.remove('show');\n"
         "}\n"
         "function toggleDrawer(id) {\n"
         "  var el = document.getElementById(id);\n"
         "  var wasOpen = el.classList.contains('mobile-open');\n"
         "  closeDrawers();\n"
         "  if (!wasOpen) { el.classList.add('mobile-open'); document.getElementById('sidebar-overlay').classList.add('show'); }\n"
         "}", "toggleSidebar")

# leftovers must be gone
for gone in ("saveSession", "renderHistory", "loadSession", "hist-list", "panel-history"):
    if gone in h:
        sys.exit(f"ABORT: '{gone}' is still referenced. Nothing written.")

# ── server.py ──
s = SERVER.read_text(encoding="utf-8")
s = once(s, '@app.get("/wifi/status", dependencies=[Depends(verify_key)])',
         "# ── SAVED CHATS (chats.py): one JSON file per chat in Chats/, git-ignored ──\n"
         "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
         "from chats import build_router as _build_chats_router\n"
         "app.include_router(_build_chats_router(verify_key))\n\n"
         '@app.get("/wifi/status", dependencies=[Depends(verify_key)])', "server router")

# ── .gitignore ──
g = GIT.read_text(encoding="utf-8")
if "Chats/" not in g.splitlines():
    g = g.rstrip("\n") + "\n\n# Saved chats (private history, local only)\nChats/\n"

HTML.write_text(h, encoding="utf-8")
SERVER.write_text(s, encoding="utf-8")
GIT.write_text(g, encoding="utf-8")
print("OK: sentinel_v2.html, server.py and .gitignore patched.")
