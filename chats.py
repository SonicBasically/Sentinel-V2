"""
Sentinel V2 — saved chats.

One JSON file per chat in ./Chats (git-ignored, so history never reaches GitHub).
The UI autosaves through these routes, so every device that opens Sentinel over
Tailscale sees the same list. All routes need the normal API key.
"""
import json, os, re, threading, time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

CHATS_DIR = Path(__file__).resolve().parent / "Chats"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_BYTES = 8 * 1024 * 1024
_TITLE_MAX = 80
_ROLES = {"user", "assistant"}
_lock = threading.RLock()
_cache = {}          # path -> (mtime_ns, size, meta, haystack)


class ChatSave(BaseModel):
    messages: List[dict]
    title: Optional[str] = None      # only used when the chat has no title yet (new chat / import)
    created: Optional[float] = None  # ms since epoch
    updated: Optional[float] = None  # ms since epoch; honoured only when keep_time is true (imports)
    keep_time: bool = False


class ChatRename(BaseModel):
    title: str


def _now_ms() -> float:
    return round(time.time() * 1000)


def _path(chat_id: str) -> Path:
    if not _ID_RE.match(chat_id or ""):
        raise HTTPException(400, "Bad chat id.")
    return CHATS_DIR / f"{chat_id}.json"


def _clean_title(t: str) -> str:
    t = " ".join(str(t or "").split())
    return (t[: _TITLE_MAX - 1] + "…") if len(t) > _TITLE_MAX else t


def _derive_title(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user" and m.get("content", "").strip():
            first = m["content"].strip().splitlines()[0]
            return _clean_title(first[:60]) or "New chat"
    return "New chat"


def _clean_messages(messages: list) -> list:
    out = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in _ROLES:
            continue
        c = m.get("content")
        if not isinstance(c, str):
            continue
        out.append({"role": m["role"], "content": c})   # drops images and any other keys
    return out


def _write_atomic(path: Path, data: dict) -> None:
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw.encode("utf-8")) > _MAX_BYTES:
        raise HTTPException(413, "Chat is too large to save.")
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.tmp")
    tmp.write_text(raw, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _read(path: Path):
    """Return (meta, haystack) for a chat file, cached by mtime and size."""
    st = path.stat()
    hit = _cache.get(str(path))
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2], hit[3]
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data.get("messages", [])
    meta = {"id": data.get("id", path.stem), "title": data.get("title") or "New chat",
            "created": data.get("created"), "updated": data.get("updated"), "count": len(msgs)}
    hay = (meta["title"] + "\n" + "\n".join(m.get("content", "") for m in msgs)).lower()
    _cache[str(path)] = (st.st_mtime_ns, st.st_size, meta, hay)
    return meta, hay


def _snippet(path: Path, terms: list) -> str:
    try:
        for m in json.loads(path.read_text(encoding="utf-8")).get("messages", []):
            c = m.get("content", "")
            i = c.lower().find(terms[0])
            if i >= 0:
                s = " ".join(c[max(0, i - 24): i + 56].split())
                return ("…" if i > 24 else "") + s
    except Exception:
        pass
    return ""


_TOMB_FILE = ".deleted.json"


def read_tombstones():
    """Chats deleted on this machine: {chat id: when it was deleted, ms}."""
    p = CHATS_DIR / _TOMB_FILE
    try:
        return {str(k): float(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def _write_tombstones(data):
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CHATS_DIR / ".deleted.tmp"
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, CHATS_DIR / _TOMB_FILE)


def write_tombstone(chat_id, when_ms):
    with _lock:
        data = read_tombstones()
        data[chat_id] = when_ms
        _write_tombstones(data)


def clear_tombstone(chat_id):
    with _lock:
        data = read_tombstones()
        if chat_id in data:
            del data[chat_id]
            _write_tombstones(data)


def build_router(verify_key) -> APIRouter:
    r = APIRouter(dependencies=[Depends(verify_key)])

    @r.get("/chats")
    def list_chats(q: Optional[str] = None):
        terms = [t for t in (q or "").lower().split() if t][:8]
        items = []
        with _lock:
            if CHATS_DIR.is_dir():
                for p in CHATS_DIR.glob("*.json"):
                    if p.name.startswith("."):
                        continue
                    try:
                        meta, hay = _read(p)
                    except Exception:
                        continue    # skip unreadable or half-written files
                    if terms and not all(t in hay for t in terms):
                        continue
                    item = dict(meta)
                    if terms:
                        item["snippet"] = _snippet(p, terms)
                    items.append(item)
        items.sort(key=lambda c: c.get("updated") or 0, reverse=True)
        return {"chats": items}

    @r.get("/chats/{chat_id}")
    def get_chat(chat_id: str):
        p = _path(chat_id)
        with _lock:
            if not p.is_file():
                raise HTTPException(404, "Chat not found.")
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                raise HTTPException(500, "Chat file is unreadable.")

    @r.put("/chats/{chat_id}")
    def save_chat(chat_id: str, req: ChatSave):
        p = _path(chat_id)
        msgs = _clean_messages(req.messages)
        if not msgs:
            raise HTTPException(400, "Nothing to save.")
        with _lock:
            old = {}
            if p.is_file():
                try:
                    old = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    old = {}
            now = _now_ms()
            data = {
                "id": chat_id,
                "title": old.get("title") or _clean_title(req.title) or _derive_title(msgs),
                "created": old.get("created") or req.created or now,
                "updated": (req.updated if (req.keep_time and req.updated) else now),
                "messages": msgs,
            }
            _write_atomic(p, data)
            clear_tombstone(chat_id)
        return {"ok": True, "id": chat_id, "title": data["title"], "updated": data["updated"], "count": len(msgs)}

    @r.post("/chats/{chat_id}/rename")
    def rename_chat(chat_id: str, req: ChatRename):
        p = _path(chat_id)
        title = _clean_title(req.title)
        if not title:
            raise HTTPException(400, "Title can't be empty.")
        with _lock:
            if not p.is_file():
                raise HTTPException(404, "Chat not found.")
            data = json.loads(p.read_text(encoding="utf-8"))
            data["title"] = title
            _write_atomic(p, data)    # rename keeps `updated`, so the chat doesn't jump to the top
        return {"ok": True, "id": chat_id, "title": title}

    @r.delete("/chats/{chat_id}")
    def delete_chat(chat_id: str):
        p = _path(chat_id)
        with _lock:
            if not p.is_file():
                raise HTTPException(404, "Chat not found.")
            p.unlink()
            _cache.pop(str(p), None)
            write_tombstone(chat_id, _now_ms())
        return {"ok": True}

    @r.get("/chats-deleted")
    def list_deleted():
        return read_tombstones()

    return r
