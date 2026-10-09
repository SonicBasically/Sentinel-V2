"""Sentinel game library: Steam (installed + non-Steam shortcuts) and custom launchers.

Games are launched by library ID only; nothing here runs free-form commands.
Custom launchers live in custom_games.json (edit it by hand, it is never written by the API).
"""
import os, re, json, glob, shutil, struct, subprocess, threading, time, difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUSTOM_FILE = HERE / "custom_games.json"
POLL_SECONDS = 10

STEAM_ROOTS = [
    "~/.steam/debian-installation",
    "~/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
]
# Steam tools that have appmanifests but are not games
JUNK_PREFIXES = ("proton", "steam linux runtime", "steamworks common redistributables", "steam linux")
JUNK_NAMES = {"spacewar"}
STOPWORDS = {"the", "a", "an", "game", "please", "for", "me", "up", "my", "on", "steam", "can", "you", "to"}

_lock = threading.RLock()
_library = []
_signature = None
_last_scan = 0.0
_watcher_started = False


# ── helpers ──────────────────────────────────────────────────────────
def _steam_roots():
    seen, out = set(), []
    for r in STEAM_ROOTS:
        p = Path(os.path.expanduser(r))
        if (p / "steamapps").is_dir():
            real = str(p.resolve())
            if real not in seen:
                seen.add(real)
                out.append(p.resolve())
    return out


def _library_dirs(root):
    """All steamapps folders for one Steam root (default + extra drives)."""
    dirs = [root / "steamapps"]
    for vdf in (root / "steamapps" / "libraryfolders.vdf", root / "config" / "libraryfolders.vdf"):
        try:
            text = vdf.read_text(errors="replace")
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
            if p.is_dir() and p not in dirs:
                dirs.append(p)
    return dirs


def _parse_manifest(path):
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None
    def grab(key):
        m = re.search(r'"%s"\s+"([^"]*)"' % key, text)
        return m.group(1) if m else None
    appid, name, flags = grab("appid"), grab("name"), grab("StateFlags")
    if not appid or not name:
        return None
    return {"appid": appid, "name": name, "flags": int(flags or 0)}


def _parse_binary_vdf(data):
    pos = 0
    def read_str():
        nonlocal pos
        end = data.index(b"\x00", pos)
        s = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return s
    def read_obj():
        nonlocal pos
        obj = {}
        while pos < len(data):
            t = data[pos]; pos += 1
            if t == 8:
                return obj
            key = read_str()
            if t == 0:
                obj[key.lower()] = read_obj()
            elif t == 1:
                obj[key.lower()] = read_str()
            elif t == 2:
                obj[key.lower()] = struct.unpack_from("<I", data, pos)[0]; pos += 4
            else:
                raise ValueError("bad vdf type %d" % t)
        return obj
    return read_obj()


def _shortcuts(root):
    out = []
    for f in glob.glob(str(root / "userdata" / "*" / "config" / "shortcuts.vdf")):
        try:
            tree = _parse_binary_vdf(Path(f).read_bytes())
        except Exception:
            continue
        for entry in (tree.get("shortcuts") or {}).values():
            if not isinstance(entry, dict):
                continue
            name, appid = entry.get("appname"), entry.get("appid")
            if name and isinstance(appid, int):
                out.append({"appid": appid, "name": name, "icon": entry.get("icon") or ""})
    return out


def _load_custom():
    try:
        items = json.loads(CUSTOM_FILE.read_text())
    except (OSError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("id") and i.get("name") and isinstance(i.get("command"), list)]


def _norm(s):
    words = re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
    return " ".join(w for w in words if w not in STOPWORDS)


def _pub(g):
    out = {k: v for k, v in g.items() if k not in ("command", "_art")}
    found = find_art(g["id"])
    out["art"] = found[1] if found else None
    return out


# ── art ──────────────────────────────────────────────────────────────
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg")


def _theme_icon(name):
    """Largest hicolor/pixmaps icon for an icon name (png preferred, svg as fallback)."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return None
    def size(p):
        m = re.search(r"/(\d+)x\d+/", p)
        return int(m.group(1)) if m else 0
    pngs = sorted(glob.glob("/usr/share/icons/hicolor/*/apps/%s.png" % name), key=size)
    if pngs:
        return Path(pngs[-1])
    for pat in ("/usr/share/icons/hicolor/*/apps/%s.svg" % name, "/usr/share/pixmaps/%s.png" % name,
                "/usr/share/pixmaps/%s.svg" % name):
        hits = glob.glob(pat)
        if hits:
            return Path(hits[0])
    return None


def find_art(game_id):
    """Return (path, kind) for a library id, or None. kind: wide | portrait | icon."""
    kind, _, ident = game_id.partition(":")
    if kind in ("steam", "shortcut"):
        if not ident.isdigit():
            return None
        for root in _steam_roots():
            if kind == "steam":
                d = root / "appcache" / "librarycache" / ident
                if not d.is_dir():
                    continue
                for name, k in (("library_header.jpg", "wide"), ("header.jpg", "wide"), ("library_hero.jpg", "wide"),
                                ("library_600x900.jpg", "portrait"), ("library_capsule.jpg", "portrait")):
                    hits = sorted(d.glob(name)) or sorted(d.glob("*/" + name))
                    if hits:
                        return hits[0], k
            else:
                for grid in glob.glob(str(root / "userdata" / "*" / "config" / "grid")):
                    for stem, k in ((ident + "_hero", "wide"), (ident, "wide"), (ident + "p", "portrait")):
                        for ext in _IMG_EXT:
                            f = Path(grid) / (stem + ext)
                            if f.is_file():
                                return f, k
    with _lock:
        game = next((g for g in _library if g["id"] == game_id), None)
    hint = (game or {}).get("_art") or ""
    if hint:
        p = Path(os.path.expanduser(hint))
        if not p.is_absolute():
            p = HERE / p
        if p.is_file() and p.suffix.lower() in _IMG_EXT:
            return p, "icon"
        icon = _theme_icon(hint)
        if icon:
            return icon, "icon"
    return None


# ── scanning ─────────────────────────────────────────────────────────
def _compute_signature():
    sig = []
    for root in _steam_roots():
        for d in _library_dirs(root):
            for f in glob.glob(str(d / "appmanifest_*.acf")):
                try: sig.append((f, os.stat(f).st_mtime))
                except OSError: pass
        for f in glob.glob(str(root / "userdata" / "*" / "config" / "shortcuts.vdf")) + [str(root / "steamapps" / "libraryfolders.vdf")]:
            try: sig.append((f, os.stat(f).st_mtime))
            except OSError: pass
    try: sig.append((str(CUSTOM_FILE), CUSTOM_FILE.stat().st_mtime))
    except OSError: pass
    return tuple(sorted(sig))


def scan():
    games, seen = [], set()
    def add(g):
        key = _norm(g["name"])
        if key and key not in seen:
            seen.add(key); games.append(g)
    for c in _load_custom():
        add({"id": "custom:" + str(c["id"]), "name": c["name"], "source": "custom", "installed": True,
             "aliases": [str(a) for a in c.get("aliases", [])], "command": [str(x) for x in c["command"]],
             "_art": str(c.get("image") or c.get("icon") or c["command"][0])})
    for root in _steam_roots():
        for d in _library_dirs(root):
            for f in sorted(glob.glob(str(d / "appmanifest_*.acf"))):
                m = _parse_manifest(f)
                if not m or m["name"].lower().startswith(JUNK_PREFIXES) or m["name"].lower() in JUNK_NAMES:
                    continue
                add({"id": "steam:" + m["appid"], "name": m["name"], "source": "steam",
                     "installed": bool(m["flags"] & 4), "aliases": []})
        for s in _shortcuts(root):
            add({"id": "shortcut:%d" % s["appid"], "name": s["name"], "source": "steam-shortcut",
                 "installed": True, "aliases": [], "_art": s["icon"]})
    games.sort(key=lambda g: g["name"].lower())
    return games


def refresh(force=False):
    global _library, _signature, _last_scan
    sig = _compute_signature()
    with _lock:
        if force or sig != _signature:
            _library = scan()
            _signature = sig
            _last_scan = time.time()


def _watch():
    while True:
        time.sleep(POLL_SECONDS)
        try: refresh()
        except Exception: pass


def get_library():
    global _watcher_started
    if not _watcher_started:
        _watcher_started = True
        refresh(force=True)
        threading.Thread(target=_watch, daemon=True).start()
    with _lock:
        return [_pub(g) for g in _library]


def last_scan():
    return _last_scan


# ── matching ─────────────────────────────────────────────────────────
def _score(q, g):
    best = 0.0
    for label in [g["name"]] + g.get("aliases", []):
        n = _norm(label)
        if not n:
            continue
        if q == n:
            return 1.0
        if len(q) >= 3 and set(q.split()) <= set(n.split()):
            best = max(best, 0.92)
        elif len(q) >= 3 and (q in n or n in q) and len(n) >= 3:
            best = max(best, 0.88)
        else:
            best = max(best, difflib.SequenceMatcher(None, q, n).ratio())
    return best


def resolve(query):
    get_library()
    q = _norm(query)
    if not q:
        return {"best": None, "candidates": []}
    with _lock:
        scored = sorted(((_score(q, g), g) for g in _library), key=lambda x: -x[0])
    pub = _pub
    cands = [dict(pub(g), score=round(s, 2)) for s, g in scored[:5] if s >= 0.5]
    best = None
    if scored and scored[0][0] >= 0.85:
        lead_ok = scored[0][0] == 1.0 or len(scored) < 2 or scored[0][0] - scored[1][0] >= 0.08
        if lead_ok:
            best = pub(scored[0][1])
    return {"best": best, "candidates": cands}


# ── launching ────────────────────────────────────────────────────────
def _steam_cmd():
    exe = shutil.which("steam") or ("/usr/games/steam" if os.path.exists("/usr/games/steam") else None)
    if exe:
        return [exe]
    if shutil.which("flatpak"):
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    return None


def launch(game_id):
    get_library()
    with _lock:
        game = next((g for g in _library if g["id"] == game_id), None)
    if not game:
        return {"ok": False, "error": "Unknown game id: %s" % game_id}
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    kind, _, ident = game_id.partition(":")
    if kind in ("steam", "shortcut"):
        cmd = _steam_cmd()
        if not cmd:
            return {"ok": False, "error": "Steam was not found on this machine."}
        gid = int(ident) if kind == "steam" else (int(ident) << 32) | 0x02000000
        argv = cmd + ["steam://rungameid/%d" % gid]
    else:
        argv = game["command"]
        if not shutil.which(argv[0]) and not os.path.exists(os.path.expanduser(argv[0])):
            return {"ok": False, "error": "Launcher not found: %s" % argv[0]}
        argv = [os.path.expanduser(argv[0])] + argv[1:]
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=env)
    note = "" if game.get("installed", True) else " (not fully installed, Steam may ask to finish installing)"
    return {"ok": True, "message": "Launching %s%s" % (game["name"], note), "game": game["name"]}
