"""Health readings for the devices Sentinel can see: this computer, the linked peer (MemEx), and the phone.

Every reading is normalized to one shape, so the Devices panel and the chat summary read the same keys.
The phone cannot be queried, so it pushes a heartbeat (POST /devices/phone/heartbeat) while its app is open.
"""
import threading
import time
from urllib.parse import urlparse

PHONE_FRESH_S = 90   # the phone counts as connected while its last heartbeat is this recent
LOCAL = None         # set by server.py: the function that reads this machine (system_info)

_lock = threading.Lock()
_phone = {"raw": None, "at": 0.0}


def _f(v, nd=1):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def normalize(raw):
    """One shape for every device. Missing readings come back as None rather than being guessed."""
    raw = raw or {}
    cpu = raw.get("cpu") or {}
    mem = raw.get("memory") or {}
    disk = raw.get("disk") or {}
    bat = raw.get("battery") or None
    gpus = []
    for g in raw.get("gpus") or []:
        gpus.append({
            "name": g.get("name"),
            "util_pct": _i(g.get("utilization_pct")),
            "temp_c": _i(g.get("temp_c")),
            "vram_used_gb": _f((g.get("memory_used_mb") or 0) / 1024),
            "vram_total_gb": _f((g.get("memory_total_mb") or 0) / 1024),
        })
    return {
        "cpu": {"usage_pct": _f(cpu.get("usage_pct")), "temp_c": _i(cpu.get("temp_c")),
                "cores": _i(cpu.get("cores_logical"))},
        "memory": {"used_gb": _f(mem.get("used_gb")), "total_gb": _f(mem.get("total_gb")),
                   "usage_pct": _f(mem.get("usage_pct"))},
        "disk": {"used_gb": _f(disk.get("used_gb")), "total_gb": _f(disk.get("total_gb")),
                 "usage_pct": _f(disk.get("usage_pct"))},
        "gpus": gpus,
        "battery": None if bat is None else {
            "level_pct": _i(bat.get("level_pct")),
            "charging": bool(bat.get("charging")),
            "temp_c": _f(bat.get("temp_c")),
        },
        "uptime": raw.get("uptime"),
    }


def record_phone(raw):
    with _lock:
        _phone["raw"] = raw
        _phone["at"] = time.time()


def _ago(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "%d seconds" % seconds
    return "%d minutes" % (seconds // 60)


def phone_reading():
    with _lock:
        raw, at = _phone["raw"], _phone["at"]
    if raw is None:
        return {"ok": False, "error": "Your phone hasn't reported yet. Open the Sentinel app on it."}
    age = time.time() - at
    if age > PHONE_FRESH_S:
        return {"ok": False, "age_s": round(age),
                "error": "Your phone stopped reporting %s ago. Open the Sentinel app on it." % _ago(age)}
    return {"ok": True, "age_s": round(age), "stats": normalize(raw)}


def peer_host():
    """Tailscale IP (host) of the linked Sentinel machine, or '' when no link is set up."""
    import link as link_lib
    url, _ = link_lib._peer()
    return (urlparse(url).hostname or "") if url else ""


def peer_reading():
    import link as link_lib
    try:
        raw = link_lib._peer_call("GET", "/system/info", timeout=6)
    except Exception as e:
        return {"ok": False, "error": str(getattr(e, "detail", "") or "The other machine is unreachable.")}
    return {"ok": True, "stats": normalize(raw)}


def local_reading():
    if LOCAL is None:
        return {"ok": False, "error": "This machine's stats aren't available yet."}
    try:
        return {"ok": True, "stats": normalize(LOCAL())}
    except Exception as e:
        return {"ok": False, "error": "Could not read this machine: %s" % e}


def read(kind):
    """kind: 'local' (this computer), 'peer' (the linked MemEx), or 'phone'."""
    if kind == "phone":
        return phone_reading()
    if kind == "peer":
        return peer_reading()
    return local_reading()


def classify(device, peer_ip):
    """Which kind of Sentinel reading a tailnet device can give: local, peer, phone, or other."""
    if device.get("self"):
        return "local"
    if (device.get("os") or "").lower() == "android":
        return "phone"
    if peer_ip and device.get("ip") == peer_ip:
        return "peer"
    return "other"


def describe(label, reading):
    """A short spoken/chat summary of one reading, e.g. 'papa-s: CPU 14% at 52°C; RAM 9.1 of 15.6 GB ...'."""
    if not reading.get("ok"):
        return reading.get("error") or "I couldn't read %s." % label
    s = reading["stats"]
    parts = []
    cpu = s["cpu"]
    if cpu["usage_pct"] is not None:
        t = "CPU %d%%" % round(cpu["usage_pct"])
        if cpu["temp_c"] is not None:
            t += " at %d°C" % cpu["temp_c"]
        parts.append(t)
    mem = s["memory"]
    if mem["used_gb"] is not None and mem["total_gb"]:
        parts.append("RAM %.1f of %.1f GB (%d%%)" % (mem["used_gb"], mem["total_gb"], round(mem["usage_pct"] or 0)))
    disk = s["disk"]
    if disk["usage_pct"] is not None:
        parts.append("disk %d%% full" % round(disk["usage_pct"]))
    for g in s["gpus"][:1]:
        t = "GPU %s" % ("%d%%" % g["util_pct"] if g["util_pct"] is not None else "load unknown")
        if g["temp_c"] is not None:
            t += " at %d°C" % g["temp_c"]
        parts.append(t)
    bat = s["battery"]
    if bat and bat["level_pct"] is not None:
        t = "battery %d%%" % bat["level_pct"]
        if bat["charging"]:
            t += " and charging"
        if bat["temp_c"] is not None:
            t += ", %.0f°C" % bat["temp_c"]
        parts.append(t)
    if s["uptime"]:
        parts.append("up " + str(s["uptime"]))
    if not parts:
        return "%s is online, but it isn't reporting any readings yet." % label
    return "%s: %s." % (label, "; ".join(parts))
