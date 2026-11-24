#!/usr/bin/env python3
"""One-off patch 2: orb follows the loudness of the voice. Anchors must match exactly once."""
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BK = REPO / "backups"

def patch(fname, edits, tag):
    p = REPO / fname
    s = p.read_text(encoding="utf-8")
    shutil.copy2(p, BK / (fname + ".bak-" + tag))
    for old, new in edits:
        n = s.count(old)
        assert n == 1, f"{fname}: anchor matched {n} times: {old[:60]!r}"
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", fname)

ENV_FUNC = '''_tts_env = []      # loudness (0..1) of the current spoken reply, one value per _TTS_WIN seconds (the UI orb follows it)
_tts_t0 = 0.0      # time.monotonic() when that reply started playing
_TTS_WIN = 0.05

def _wav_envelope(path):
    """Loudness per 50 ms window of a 16-bit wav, scaled so the loud parts reach about 1. [] if unreadable."""
    try:
        import wave, array
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2: return []
            ch, rate = w.getnchannels(), w.getframerate()
            data = array.array("h"); data.frombytes(w.readframes(w.getnframes()))
        step = max(1, int(rate * _TTS_WIN)) * ch
        vals = []
        for i in range(0, len(data), step):
            seg = data[i:i + step]
            if seg: vals.append(math.sqrt(sum(x * x for x in seg) / len(seg)))
        if not vals: return []
        top = sorted(vals)[int(len(vals) * 0.95) - 1 if len(vals) > 20 else -1] or 1.0
        return [min(1.0, v / top) for v in vals]
    except Exception:
        return []

def _cleanup_tts_file(proc, path):'''

SERVER_EDITS = [
    ("def _cleanup_tts_file(proc, path):", ENV_FUNC),
    ("    global _tts_proc, _tts_count\n", "    global _tts_proc, _tts_count, _tts_env, _tts_t0\n"),
    ('            _tts_proc = subprocess.Popen(["paplay", tmpfile], env=env)\n',
     '            _tts_env = _wav_envelope(tmpfile)\n'
     '            _tts_proc = subprocess.Popen(["paplay", tmpfile], env=env)\n'
     '            _tts_t0 = time.monotonic()\n'),
    ('    return {"speaking": bool(_tts_proc is not None and _tts_proc.poll() is None)}\n',
     '    speaking = bool(_tts_proc is not None and _tts_proc.poll() is None)\n'
     '    level = 0.0\n'
     '    if speaking and _tts_env:\n'
     '        i = int((time.monotonic() - _tts_t0) / _TTS_WIN)\n'
     '        if 0 <= i < len(_tts_env): level = round(_tts_env[i], 2)\n'
     '    return {"speaking": speaking, "level": level}\n'),
]

UI_EDITS = [
    ("#orb.talk{opacity:1;box-shadow:0 0 70px 2px var(--o),0 0 160px 8px var(--o);animation:orbTalk 0.9s ease-in-out infinite;}",
     "#orb.talk{opacity:calc(0.75 + var(--lv,0)*0.25);box-shadow:0 0 70px 2px var(--o),0 0 160px 8px var(--o);animation:none;transform:scale(calc(1 + var(--lv,0)*0.14));transition:transform 0.1s linear,opacity 0.1s linear,box-shadow 0.4s;}"),
    ("function orbSet(on){\n  if(on===_orbOn) return;\n",
     "function orbSet(on,lv){\n  if(on) document.getElementById('orb').style.setProperty('--lv',lv||0);\n  if(on===_orbOn) return;\n"),
    ("  if(_browserSpeaking){orbSet(true);return;}\n",
     "  if(_browserSpeaking){orbSet(true,0.5+0.5*Math.sin(Date.now()/130)*Math.sin(Date.now()/370+1));return;}\n"),
    ("then(function(d){orbSet(!!d.speaking);})", "then(function(d){orbSet(!!d.speaking,d.level);})"),
    ("setInterval(orbTick,300)", "setInterval(orbTick,100)"),
]

patch("server.py", SERVER_EDITS, "orb-level")
patch("sentinel_v2.html", UI_EDITS, "orb-level")
