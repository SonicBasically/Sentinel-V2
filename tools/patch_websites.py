#!/usr/bin/env python3
"""One-off patch: add website opening and web searches to voice_commands.py.
Backs up first, and refuses to change anything unless every anchor matches exactly once."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "voice_commands.py"
BACKUP = ROOT / "backups" / "voice_commands.py.bak-websites"

HELPERS = r'''# ───────────────────────── websites and web searches ─────────────────────────
# name -> (label, home URL, search URL prefix or None). Opened with xdg-open (system default browser).
SITES = {
    "youtube": ("YouTube", "https://www.youtube.com", "https://www.youtube.com/results?search_query="),
    "google": ("Google", "https://www.google.com", "https://www.google.com/search?q="),
    "gmail": ("Gmail", "https://mail.google.com", "https://mail.google.com/mail/u/0/#search/"),
    "github": ("GitHub", "https://github.com", "https://github.com/search?q="),
    "reddit": ("Reddit", "https://www.reddit.com", "https://www.reddit.com/search/?q="),
    "twitch": ("Twitch", "https://www.twitch.tv", "https://www.twitch.tv/search?term="),
    "crunchyroll": ("Crunchyroll", "https://www.crunchyroll.com", "https://www.crunchyroll.com/search?q="),
    # bare "discord" stays the desktop app (APP_ALIASES); only "discord web" opens the site
    "discord web": ("Discord (web)", "https://discord.com/app", None),
}
# spellings Vosk tends to produce
_SITE_ALIASES = {"you tube": "youtube", "g mail": "gmail", "git hub": "github",
                 "crunchy roll": "crunchyroll", "discord website": "discord web"}
_SITE_RE = "|".join(sorted((re.escape(k) for k in list(SITES) + list(_SITE_ALIASES)), key=len, reverse=True))
_OPEN_VERBS = r"(?:open|launch|go to|visit|pull up|take me to|browse to)(?: up)?"
_BROWSER_TAIL = r"(?: (?:in|on) (?:the |my )?(?:browser|firefox|web|internet))?"
_TLDS = r"(?:com|org|net|io|tv|gg|dev|app|co|ai|me|us|uk|edu|gov)"


def _site_key(name):
    name = _SITE_ALIASES.get(name, name)
    if name in SITES:
        return name
    base = re.sub(r" (?:website|web site|site|dot com)$", "", name).strip()
    base = _SITE_ALIASES.get(base, base)
    return base if base in SITES else None


def _site_intent(site):
    label, home, _search = SITES[site]
    return {"kind": "web", "url": home, "label": label, "reply": "Opening %s." % label}


def _search_intent(site, query):
    label, _home, search = SITES[site]
    query = (query or "").strip()[:200]
    if not search or not query:
        return None
    q = urllib.parse.quote_plus(query)
    if site == "gmail":
        q = q.replace("+", "%20")
    return {"kind": "web", "url": search + q, "label": label,
            "reply": "Searching %s for %s." % (label, query)}


def _strip_polite(t):
    # same polite wrapper removal as _normalize, but keeps dots so domains survive
    t = re.sub(r"^(?:hey |ok |okay )?(?:sentinel[,:]? )?(?:please )?"
               r"(?:(?:can|could|would|will) you )?(?:please )?", "", t)
    t = re.sub(r"[.!?]+$", "", t).strip()
    return re.sub(r"(?: for me)?(?: please)?(?: sentinel)?$", "", t).strip()


def _parse_web(text):
    """Intent for 'open <site>', 'go to <domain>' or 'search ...', else None."""
    raw = _strip_polite(re.sub(r"\s+", " ", (text or "").lower()).strip())
    # a typed or spoken domain: "open github.com", "go to example dot org"
    d = raw.replace(" dot ", ".")
    m = re.match(r"^%s (?:the )?(?:website |site )?((?:[a-z0-9-]+\.)+%s)(/[a-z0-9/_.\-?=&%%#]*)?%s$"
                 % (_OPEN_VERBS, _TLDS, _BROWSER_TAIL), d)
    if m:
        host = m.group(1)
        return {"kind": "web", "url": "https://" + host + (m.group(2) or ""), "label": host,
                "reply": "Opening %s." % host}
    t = _normalize(text)
    # searches: "search youtube for X", "search for X on youtube", "search for X", "google X"
    m = re.match(r"^search (?:up )?(%s) for (.+)$" % _SITE_RE, t)
    if m:
        return _search_intent(_site_key(m.group(1)), m.group(2))
    m = re.match(r"^(?:search|google)(?: for)? (.+?) (?:on|in) (%s)$" % _SITE_RE, t)
    if m:
        return _search_intent(_site_key(m.group(2)), m.group(1))
    m = re.match(r"^search(?: the web| the internet| google)? for (.+)$", t)
    if m:
        return _search_intent("google", m.group(1))
    m = re.match(r"^google (.+)$", t)
    if m:
        return _search_intent("google", m.group(1))
    # open a known site: "open youtube", "go to reddit", "open the crunchyroll website"
    m = re.match(r"^%s (?:the |my )?(.+?)%s$" % (_OPEN_VERBS, _BROWSER_TAIL), t)
    if m:
        key = _site_key(m.group(1).strip())
        if key:
            return _site_intent(key)
    return None


'''

RUN_WEB = r'''def _run_web(intent):
    opener = shutil.which("xdg-open")
    if not opener:
        return _result("I couldn't open the browser: xdg-open is not installed.", False)
    env = media_lib._env()
    env.setdefault("DISPLAY", ":0")
    try:
        p = subprocess.Popen([opener, intent["url"]], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        return _result("I couldn't open the browser.", False)
    try:
        code = p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        code = 0  # still starting the browser, which is fine
    if code != 0:
        return _result("I couldn't open %s in the browser." % intent["label"], False)
    return _result(intent["reply"])


'''

# (anchor, replacement) — each anchor must occur exactly once
EDITS = [
    ("import subprocess\n", "import subprocess\nimport urllib.parse\n"),
    ("def parse_command(text):\n", HELPERS + "def parse_command(text):\n"),
    ("    if not t or len(t.split()) > 12:\n        return None\n\n    # ---- music",
     "    if not t or len(t.split()) > 12:\n        return None\n\n"
     "    # ---- websites and web searches (before volume, so \"search for sound effects\" is not eaten) ----\n"
     "    web = _parse_web(text)\n    if web:\n        return web\n\n    # ---- music"),
    ("def try_command(text, app_aliases=None):\n", RUN_WEB + "def try_command(text, app_aliases=None):\n"),
    ('    if intent["kind"] == "media":\n        return _run_media(intent["action"])\n',
     '    if intent["kind"] == "web":\n        return _run_web(intent)\n'
     '    if intent["kind"] == "media":\n        return _run_media(intent["action"])\n'),
]

src = TARGET.read_text(encoding="utf-8")
if "_parse_web" in src:
    sys.exit("Already patched (found _parse_web). Nothing changed.")
for anchor, _ in EDITS:
    n = src.count(anchor)
    if n != 1:
        sys.exit("Anchor matched %d times (need exactly 1), nothing changed:\n%s" % (n, anchor))
BACKUP.parent.mkdir(exist_ok=True)
shutil.copy2(TARGET, BACKUP)
for anchor, repl in EDITS:
    src = src.replace(anchor, repl, 1)
TARGET.write_text(src, encoding="utf-8")
print("Patched %s (backup: %s)" % (TARGET.name, BACKUP))
