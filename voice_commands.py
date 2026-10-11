"""Voice and chat commands that run directly, without asking the language model.

Handles: open a game or app, music controls (play/pause/resume/next/previous via
playerctl, so desktop players like Spotify or a browser), and volume (up, down, set).

parse_command(text) is pure (no side effects) and returns an intent or None.
try_command(text, app_aliases) runs the intent and returns {"handled", "ok", "reply"}
or None when the text is not a command. Replies only claim success if the action ran.
"""
import os
import re
import shutil
import subprocess
import urllib.parse

import games as game_lib
import media as media_lib

VOLUME_STEP = 10  # percent used for "volume up" / "volume down" when no amount is said

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

_MEDIA_NOUN = r"(?:music|song|songs|track|tracks|audio|playback|media|tunes|it)"
_NEXT_NOUN = r"(?:song|track|one|tune)"


def _normalize(text):
    t = (text or "").lower().replace("%", " percent ")
    t = re.sub(r"[^a-z0-9' ]+", " ", t).replace("'", "")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:hey |ok |okay )?(?:sentinel )?(?:please )?"
               r"(?:(?:can|could|would|will) you )?(?:please )?", "", t)
    t = re.sub(r"(?: for me)?(?: please)?(?: sentinel)?$", "", t).strip()
    return t


def _find_number(t):
    """First number in the text, as digits or spoken words (Vosk says 'fifty', not '50')."""
    m = re.search(r"\b(\d{1,3})\b", t)
    if m:
        return int(m.group(1))
    total, cur, seen = 0, 0, False
    for w in t.split() + [""]:
        if w in _UNITS:
            cur += _UNITS[w]; seen = True
        elif w in _TENS:
            cur += _TENS[w]; seen = True
        elif w == "hundred" and seen:
            cur = (cur or 1) * 100
        elif w == "a" and not seen:
            continue
        elif seen:
            return total + cur
    return None


# ───────────────────────── websites and web searches ─────────────────────────
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


def parse_command(text):
    """Return an intent dict, or None if the text is not a command we handle."""
    t = _normalize(text)
    if not t or len(t.split()) > 12:
        return None

    # ---- websites and web searches (before volume, so "search for sound effects" is not eaten) ----
    web = _parse_web(text)
    if web:
        return web

    # ---- music: generic words only, so "play half life" still reaches the game rule ----
    m = re.match(r"^(resume|continue|unpause|play|start|keep playing)(?: playing)?"
                 r"(?: (?:my|the))?(?: (%s))?$" % _MEDIA_NOUN, t)
    if m and (m.group(2) or m.group(1) != "start"):
        return {"kind": "media", "action": "play"}
    if re.match(r"^(?:pause|stop)(?: (?:my|the))?(?: %s)?$" % _MEDIA_NOUN, t) and \
            (t.startswith("pause") or re.search(_MEDIA_NOUN + "$", t)):
        return {"kind": "media", "action": "pause"}
    if re.match(r"^(?:(?:play|go to|skip to) (?:the )?)?next(?: %s)?$|"
                r"^skip(?: (?:this|the|that|my))?(?: %s)?$" % (_NEXT_NOUN, _NEXT_NOUN), t):
        return {"kind": "media", "action": "next"}
    if re.match(r"^(?:(?:play|go to|skip to|go back to) (?:the )?)?previous(?: %s)?$|"
                r"^(?:play |go to )?(?:the )?last %s$|^go back$" % (_NEXT_NOUN, _NEXT_NOUN), t):
        return {"kind": "media", "action": "previous"}

    # ---- volume ----
    words = set(t.split())
    if words & {"volume", "sound", "louder", "quieter", "softer"} or \
            t in ("turn it up", "turn it down"):
        num = _find_number(t)
        absolute = re.search(r"\b(?:to|at)\b", t) and num is not None
        if not absolute and re.match(r"^volume (?:\d|%s)" % "|".join(list(_UNITS) + list(_TENS)), t) \
                and num is not None:
            absolute = True
        if absolute:
            return {"kind": "volume", "mode": "set", "value": max(0, min(100, num))}
        up = bool(words & {"up", "louder", "raise", "increase", "higher", "boost"})
        down = bool(words & {"down", "quieter", "lower", "decrease", "softer", "reduce"})
        if up != down:
            amount = num if num is not None else VOLUME_STEP
            return {"kind": "volume", "mode": "up" if up else "down", "value": max(1, min(100, amount))}
        return None

    # ---- open a game or app ----
    m = re.match(r"^(open|launch|start|run|play)(?: up)? (?:the |my )?(.+?)(?: (?:game|app|application))?$", t)
    if m:
        name = re.sub(r"^(?:the )?(?:game|app|application) ", "", m.group(2).strip())
        if name and not re.match(r"^(?:some |any )?%s$" % _MEDIA_NOUN, name):
            return {"kind": "open", "verb": m.group(1), "name": name}
    return None


# ───────────────────────── running the intent ─────────────────────────
def _result(reply, ok=True):
    return {"handled": True, "ok": ok, "reply": reply}


def _run_media(action):
    try:
        players = media_lib.now_playing()
    except Exception:
        players = []
    if not players:
        return _result("I don't see a music player running.", False)
    playing = [p for p in players if p["status"] == "Playing"]
    if action == "play":
        if playing:
            return _result("Music is already playing.")
        target = players[0]  # now_playing() lists Paused players before Stopped ones
    elif action == "pause":
        if not playing:
            return _result("Nothing is playing right now.")
        target = playing[0]
    else:
        target = (playing or players)[0]
    try:
        media_lib.control(action, target["player"], None)
    except Exception as e:
        detail = getattr(e, "detail", None) or str(e)
        return _result("I couldn't control %s: %s" % (target["name"], str(detail)[:80]), False)
    title = target.get("title") or ""
    if action == "play":
        return _result("Resuming %s." % (title or target["name"]))
    if action == "pause":
        return _result("Paused.")
    return _result("Next track." if action == "next" else "Previous track.")


def _pactl(*args):
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5, env=media_lib._env())


def _current_volume():
    try:
        m = re.search(r"(\d+)%", _pactl("get-sink-volume", "@DEFAULT_SINK@").stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _set_volume(level):
    level = max(0, min(100, int(level)))
    try:
        if _pactl("set-sink-volume", "@DEFAULT_SINK@", "%d%%" % level).returncode == 0:
            return True
        r = subprocess.run(["amixer", "sset", "Master", "%d%%" % level], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _run_volume(intent):
    if intent["mode"] == "set":
        target = intent["value"]
    else:
        cur = _current_volume()
        if cur is None:
            return _result("I couldn't read the current volume.", False)
        delta = intent["value"] if intent["mode"] == "up" else -intent["value"]
        target = max(0, min(100, cur + delta))
    if not _set_volume(target):
        return _result("I couldn't change the volume.", False)
    return _result("Volume %d percent." % target)


def _run_open(intent, app_aliases):
    name, verb = intent["name"], intent["verb"]
    exe = (app_aliases or {}).get(name)
    if exe:
        if not shutil.which(exe):
            return _result("I couldn't find %s on this computer." % name, False)
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         preexec_fn=os.setpgrp)
        return _result("Opening %s." % name)
    try:
        res = game_lib.resolve(name)
    except Exception:
        res = {"best": None, "candidates": []}
    if res.get("best"):
        out = game_lib.launch(res["best"]["id"])
        if out.get("ok"):
            return _result("Launching %s." % res["best"]["name"])
        return _result("I found %s but couldn't launch it." % res["best"]["name"], False)
    near = [c["name"] for c in res.get("candidates", []) if c.get("score", 0) >= 0.6][:3]
    if near:
        return _result("Which one did you mean: %s?" % ", ".join(near), False)
    if verb in ("open", "launch"):
        return None  # unknown open/launch targets can be handled by the chat model
    return None  # "play/start/run <something else>" is not ours; let the chat model answer


def _run_web(intent):
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


def try_command(text, app_aliases=None):
    """Run a recognized command. Returns None if `text` is not a command."""
    intent = parse_command(text)
    if not intent:
        return None
    if intent["kind"] == "web":
        return _run_web(intent)
    if intent["kind"] == "media":
        return _run_media(intent["action"])
    if intent["kind"] == "volume":
        return _run_volume(intent)
    return _run_open(intent, app_aliases)
