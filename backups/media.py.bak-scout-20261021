#!/usr/bin/env python3
"""media.py - Sentinel media player backend (music only for now; video comes later).

  * Library     - scans MUSIC_DIR for audio files. Tracks are addressed by a stable id,
                  never by a path the client supplies.
  * Streaming   - the browser <audio> element cannot send the X-Api-Key header, so the UI first
                  calls POST /media/token (authenticated) and then streams with ?t=<token>.
                  Tokens are random, kept in memory only, and expire after TOKEN_TTL seconds.
  * Now playing - reads and controls whatever is playing on the desktop through playerctl (MPRIS).
  * Playlists   - saved in ~/.config/sentinel/playlists.json, plus import of Windows Media Player .wpl files.

server.py wires this in with:  app.include_router(media_lib.make_router(verify_key))
Optional: `pip install mutagen` (inside .venv) adds real titles/artists/durations and embedded cover art.
"""
import os, re, json, time, html, hashlib, secrets, mimetypes, subprocess, threading
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

try:
    from mutagen import File as _MFile
except Exception:
    _MFile = None

MUSIC_DIR = Path(os.environ.get("SENTINEL_MUSIC_DIR") or (Path.home() / "Desktop" / "Media_Drive" / "Music")).expanduser()
AUDIO_EXT = {".mp3", ".ogg", ".oga", ".opus", ".wav", ".flac", ".m4a", ".aac"}
SKIP_DIRS = {"Windows Media Player Skins", "Windows Media Player Visualizations", "Songs For WMP"}
PLAYLIST_FILE = Path.home() / ".config" / "sentinel" / "playlists.json"
TOKEN_TTL = 15 * 60

_lock = threading.RLock()
_lib = {"tracks": [], "by_id": {}, "by_rel": {}, "by_name": {}, "scanned": 0.0}
_tokens = {}


# ── library ──────────────────────────────────────────────────────────────────
def _tid(rel):
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]


def _tags(p):
    title = artist = album = ""
    dur = 0.0
    if _MFile:
        try:
            m = _MFile(str(p), easy=True)
            if m is not None:
                if getattr(m, "info", None) is not None and getattr(m.info, "length", None):
                    dur = float(m.info.length)
                t = m.tags or {}

                def g(k):
                    v = t.get(k)
                    if isinstance(v, (list, tuple)):
                        return v[0] if v else ""
                    return v or ""
                title, artist, album = str(g("title")).strip(), str(g("artist")).strip(), str(g("album")).strip()
        except Exception:
            pass
    return title, artist, album, dur


def _scan():
    tracks, by_id, by_rel, by_name = [], {}, {}, {}
    if MUSIC_DIR.is_dir():
        for root, dirs, files in os.walk(MUSIC_DIR):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
            for fn in sorted(files, key=str.lower):
                p = Path(root) / fn
                if p.suffix.lower() not in AUDIO_EXT:
                    continue
                try:
                    rel = p.relative_to(MUSIC_DIR).as_posix()
                    rel.encode("utf-8")
                except Exception:
                    continue
                title, artist, album, dur = _tags(p)
                folder = p.parent.relative_to(MUSIC_DIR).as_posix()
                t = {"id": _tid(rel), "title": title or p.stem, "artist": artist, "album": album,
                     "folder": "" if folder == "." else folder, "dur": round(dur, 1)}
                tracks.append(t)
                by_id[t["id"]] = (t, p, rel)
                by_rel[rel] = t
                by_name.setdefault(fn.lower(), []).append(rel)
    with _lock:
        _lib.update(tracks=tracks, by_id=by_id, by_rel=by_rel, by_name=by_name, scanned=time.time())
    return tracks


def library(refresh=False):
    with _lock:
        need = refresh or not _lib["scanned"]
    if need:
        _scan()
    return _lib


def _track_path(tid):
    hit = library()["by_id"].get(tid)
    if not hit:
        raise HTTPException(404, "Unknown track")
    p = hit[1]
    try:
        p.resolve().relative_to(MUSIC_DIR.resolve())
    except Exception:
        raise HTTPException(404, "Unknown track")
    if not p.is_file():
        raise HTTPException(404, "File is missing - rescan the library")
    return p


# ── stream tokens ────────────────────────────────────────────────────────────
def _new_token():
    now = time.time()
    with _lock:
        for k in [k for k, exp in _tokens.items() if exp < now]:
            del _tokens[k]
        tok = secrets.token_urlsafe(24)
        _tokens[tok] = now + TOKEN_TTL
    return tok


def _check_token(tok):
    with _lock:
        exp = _tokens.get(tok or "")
    if not exp or exp < time.time():
        raise HTTPException(401, "Invalid or expired stream token")


def _embedded_art(p):
    """Return (bytes, mime) for embedded cover art, or None. Needs mutagen."""
    if not _MFile:
        return None
    try:
        m = _MFile(str(p))
        if m is None:
            return None
        tags = getattr(m, "tags", None)
        if tags is not None and hasattr(tags, "keys"):
            for k in list(tags.keys()):
                if str(k).startswith("APIC"):
                    fr = tags[k]
                    return fr.data, (fr.mime or "image/jpeg")
            if "covr" in tags and tags["covr"]:
                c = tags["covr"][0]
                return bytes(c), ("image/png" if getattr(c, "imageformat", 0) == 14 else "image/jpeg")
        pics = getattr(m, "pictures", None)
        if pics:
            return pics[0].data, (pics[0].mime or "image/jpeg")
    except Exception:
        pass
    return None


# ── playlists (saved + .wpl import) ──────────────────────────────────────────
def _pl_load():
    try:
        d = json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
        return [p for p in d.get("playlists", []) if isinstance(p, dict) and p.get("name")]
    except Exception:
        return []


def _pl_save(pls):
    PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PLAYLIST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"playlists": pls}, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PLAYLIST_FILE)


def _pl_view():
    lib = library()
    out = []
    for p in _pl_load():
        ids, missing = [], 0
        for rel in p.get("tracks", []):
            t = lib["by_rel"].get(rel)
            if t:
                ids.append(t["id"])
            else:
                missing += 1
        out.append({"name": p["name"], "source": p.get("source", "user"), "ids": ids, "missing": missing})
    return out


def _wpl_parse(path):
    data = path.read_bytes()
    title, srcs = path.stem, []
    try:
        root = ET.fromstring(data)
        t = root.find("./head/title")
        if t is not None and (t.text or "").strip():
            title = t.text.strip()
        srcs = [m.get("src") for m in root.iter("media") if m.get("src")]
    except ET.ParseError:
        text = data.decode("utf-8", "replace")
        srcs = [html.unescape(s) for s in re.findall(r'<media\s+[^>]*src="([^"]+)"', text)]
    return title, srcs


def _wpl_resolve(src, wpl_dir, lib):
    """Windows paths in .wpl files are relative to the playlist's old folder, which no longer
    matches this machine, so try the literal path first, then fall back to matching by file name."""
    s = src.replace("\\", "/")
    try:
        rel = (wpl_dir / s).resolve().relative_to(MUSIC_DIR.resolve()).as_posix()
        if rel in lib["by_rel"]:
            return rel
    except Exception:
        pass
    parts = [x for x in s.split("/") if x not in ("", ".", "..")]
    if not parts:
        return None
    matches = lib["by_name"].get(parts[-1].lower(), [])
    if not matches:
        return None
    if len(parts) > 1:
        want = parts[-2].lower()
        for rel in matches:
            rp = rel.split("/")
            if len(rp) > 1 and rp[-2].lower() == want:
                return rel
    return matches[0]


def _wpl_import():
    lib = library()
    pls = _pl_load()
    files = []
    if MUSIC_DIR.is_dir():
        files = sorted(p for p in MUSIC_DIR.rglob("*") if p.is_file() and p.suffix.lower() == ".wpl")
    results = []
    for f in files:
        try:
            title, srcs = _wpl_parse(f)
        except Exception:
            results.append({"name": f.stem, "matched": 0, "missing": 0, "status": "unreadable"})
            continue
        rels, missing = [], 0
        for s in srcs:
            rel = _wpl_resolve(s, f.parent, lib)
            if rel:
                rels.append(rel)
            else:
                missing += 1
        if not rels:
            results.append({"name": title, "matched": 0, "missing": missing, "status": "empty"})
            continue
        existing = next((p for p in pls if p["name"].casefold() == title.casefold()), None)
        if existing and existing.get("source", "user") != "wpl":
            results.append({"name": title, "matched": len(rels), "missing": missing, "status": "skipped (you already have a playlist with this name)"})
            continue
        entry = {"name": title, "source": "wpl", "tracks": rels}
        if existing:
            pls[pls.index(existing)] = entry
        else:
            pls.append(entry)
        results.append({"name": title, "matched": len(rels), "missing": missing, "status": "updated" if existing else "imported"})
    _pl_save(pls)
    return results


# ── now playing (playerctl / MPRIS) ──────────────────────────────────────────
_SEP = "\x1f"
_FMT = _SEP.join(["{{playerInstance}}", "{{status}}", "{{title}}", "{{artist}}", "{{album}}",
                  "{{mpris:length}}", "{{mpris:artUrl}}", "{{position}}", "{{volume}}"])
ACTIONS = {"play", "pause", "play-pause", "next", "previous", "stop"}


def _env():
    e = os.environ.copy()
    uid = os.getuid()
    e.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if not e.get("DBUS_SESSION_BUS_ADDRESS") or e["DBUS_SESSION_BUS_ADDRESS"].startswith("disabled"):
        e["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    return e


def _pctl(*args):
    try:
        r = subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=3, env=_env())
        return r.returncode, r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, "", "playerctl unavailable"


def _num(s, scale=1.0):
    try:
        return float(s) / scale
    except (TypeError, ValueError):
        return 0.0


def now_playing():
    rc, out, _ = _pctl("-a", "metadata", "--format", _FMT)
    players = []
    if rc == 0:
        for line in out.splitlines():
            f = line.split(_SEP)
            if len(f) < 9 or not f[0].strip():
                continue
            art = f[6].strip()
            players.append({
                "player": f[0].strip(), "name": f[0].strip().split(".")[0], "status": f[1].strip() or "Stopped",
                "title": f[2].strip(), "artist": f[3].strip(), "album": f[4].strip(),
                "length": _num(f[5], 1e6), "position": _num(f[7], 1e6), "volume": _num(f[8]),
                "art": art if art.startswith(("http://", "https://")) else "",
            })
    rank = {"Playing": 0, "Paused": 1}
    players.sort(key=lambda p: rank.get(p["status"], 2))
    return players


def control(action, player, value):
    rc, out, _ = _pctl("-l")
    if rc != 0 or player not in [l.strip() for l in out.splitlines()]:
        raise HTTPException(404, "That player is not running")
    if action in ACTIONS:
        args = [action]
    elif action == "seek" and value is not None and value >= 0:
        args = ["position", f"{float(value):.2f}"]
    elif action == "volume" and value is not None:
        args = ["volume", f"{min(max(float(value), 0.0), 1.0):.2f}"]
    else:
        raise HTTPException(400, "Unsupported action")
    rc, _, err = _pctl("-p", player, *args)
    if rc != 0:
        raise HTTPException(502, (err or "playerctl failed").strip()[:200])
    return {"ok": True}


# ── routes ───────────────────────────────────────────────────────────────────
class ControlReq(BaseModel):
    action: str
    player: str = ""
    value: Optional[float] = None


class PlaylistReq(BaseModel):
    name: str
    ids: List[str]


def make_router(verify_key):
    r = APIRouter(prefix="/media", tags=["media"])
    auth = [Depends(verify_key)]

    @r.get("/library", dependencies=auth)
    def media_library(refresh: bool = False):
        lib = library(refresh)
        return {"ok": True, "tracks": lib["tracks"], "count": len(lib["tracks"]), "updated": lib["scanned"],
                "dir": str(MUSIC_DIR), "dir_exists": MUSIC_DIR.is_dir(), "tags": _MFile is not None}

    @r.post("/token", dependencies=auth)
    def media_token():
        return {"ok": True, "token": _new_token(), "ttl": TOKEN_TTL}

    # Stream and art are authenticated by the short-lived token, not the header (see module docstring).
    @r.get("/stream/{tid}")
    def media_stream(tid: str, t: str = ""):
        _check_token(t)
        p = _track_path(tid)
        mt = mimetypes.guess_type(str(p))[0] or "audio/mpeg"
        return FileResponse(str(p), media_type=mt, headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/art/{tid}")
    def media_art(tid: str, t: str = ""):
        _check_token(t)
        art = _embedded_art(_track_path(tid))
        if not art:
            raise HTTPException(404, "No embedded art")
        return Response(content=art[0], media_type=art[1], headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/nowplaying", dependencies=auth)
    def media_nowplaying():
        return {"ok": True, "players": now_playing()}

    @r.post("/control", dependencies=auth)
    def media_control(req: ControlReq):
        return control(req.action, req.player, req.value)

    @r.get("/playlists", dependencies=auth)
    def media_playlists():
        return {"ok": True, "playlists": _pl_view()}

    @r.post("/playlists", dependencies=auth)
    def media_playlist_save(req: PlaylistReq):
        name = req.name.strip()
        if not name or len(name) > 80:
            raise HTTPException(400, "Playlist name must be 1-80 characters")
        if len(req.ids) > 5000:
            raise HTTPException(400, "Too many tracks")
        by_id = library()["by_id"]
        rels = [by_id[i][2] for i in req.ids if i in by_id]
        pls = _pl_load()
        entry = {"name": name, "source": "user", "tracks": rels}
        for i, p in enumerate(pls):
            if p["name"].casefold() == name.casefold():
                pls[i] = entry
                break
        else:
            pls.append(entry)
        _pl_save(pls)
        return {"ok": True, "playlists": _pl_view()}

    @r.delete("/playlists", dependencies=auth)
    def media_playlist_delete(name: str):
        pls = _pl_load()
        keep = [p for p in pls if p["name"].casefold() != name.strip().casefold()]
        if len(keep) == len(pls):
            raise HTTPException(404, "No playlist with that name")
        _pl_save(keep)
        return {"ok": True, "playlists": _pl_view()}

    @r.post("/playlists/import", dependencies=auth)
    def media_playlist_import():
        results = _wpl_import()
        return {"ok": True, "results": results, "playlists": _pl_view()}

    return r
