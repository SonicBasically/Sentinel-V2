"""Wake phrase ("Hey Sentinel") helpers for the always-listening voice stack.

server.py keeps the mic open while wake listening is on and calls into this module:
  strip_wake(text)   -> (heard, rest): finds "hey sentinel" at the start of a sentence, tolerant of Vosk mishearings
  acknowledge()      -> beep plus a random spoken phrase ("Yes?", "Sup", ...), blocks until it has played
  chime()            -> just the beep (used when the command comes in the same breath as the phrase)
  prepare()          -> builds the beep and spoken phrases once (festival) into ~/.cache/sentinel/wake/
  load_enabled() / save_enabled(on) -> remembers the wake listening on/off toggle across restarts
Everything runs locally. Audio is never sent anywhere.
"""
import difflib, json, math, os, random, re, shutil, struct, subprocess, wave
from pathlib import Path

WAKE_TIMEOUT = float(os.environ.get("SENTINEL_WAKE_TIMEOUT", "6"))   # seconds of silence after waking before going back to idle

# Spoken after the beep. Edit freely: new phrases are built the next time the backend starts.
ACK_PHRASES = [
    "Hmm?", "Yes?", "Yes sir", "What's up man", "Sup", "Huh?",
    "Yeah?", "I'm listening", "Go ahead", "At your service", "What do you need?",
]

CACHE_DIR = Path(os.environ.get("SENTINEL_WAKE_CACHE", str(Path.home() / ".cache" / "sentinel" / "wake")))
SETTINGS = Path.home() / ".config" / "sentinel" / "voice.json"
_BEEP = CACHE_DIR / "beep.wav"
_last_phrase = None

# ── finding the wake phrase ──
# What Vosk tends to write for "hey": the first word has to be one of these, then "sentinel" (or a close
# mishearing, possibly split into two or three words) has to follow. "open sentinel" or "play sentinel" do not count.
_HEY = {"hey", "hay", "hi", "ay", "a", "eh", "hate", "he"}
_NOISE = {"the", "a", "uh", "um", "huh", "hm", "hmm", "mm", "oh", "ah"}

def strip_wake(text):
    """Returns (heard, rest). rest is what was said after the phrase ("" if nothing)."""
    orig = (text or "").split()
    norm = [re.sub(r"[^a-z']", "", w.lower()) for w in orig]
    for i in range(min(3, len(orig))):          # allow up to two filler words before the phrase
        if norm[i] not in _HEY:
            continue
        best_n, best = 0, 0.0
        for n in (1, 2, 3):                      # "sentinel" may come out as one, two or three words
            if i + 1 + n > len(orig):
                break
            cand = "".join(norm[i + 1:i + 1 + n])
            if abs(len(cand) - len("sentinel")) > 3:
                continue
            r = difflib.SequenceMatcher(None, cand, "sentinel").ratio()
            if r > best:
                best_n, best = n, r
        if best >= 0.75:
            return True, " ".join(orig[i + 1 + best_n:]).strip(" ,.!?")
    return False, (text or "")

def is_noise(text):
    """True for stray one-word blips Vosk writes for background noise ("the", "uh")."""
    words = [re.sub(r"[^a-z']", "", w.lower()) for w in (text or "").split()]
    return not words or all(w in _NOISE for w in words)

# ── remembering the toggle ──
def load_enabled():
    try:
        return bool(json.loads(SETTINGS.read_text()).get("wake_enabled", True))
    except Exception:
        return True   # on by default

def save_enabled(on):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({"wake_enabled": bool(on)}))
    except Exception as e:
        print(f"[Wake] could not save the setting: {e}")

# ── sounds ──
def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")

def _phrase_file(t):
    return CACHE_DIR / (_slug(t) + ".wav")

def _write_beep(path):
    rate, frames = 22050, bytearray()
    for freq, dur in ((880, 0.09), (1175, 0.12)):          # two quick rising tones
        n = int(rate * dur)
        for i in range(n):
            env = max(0.0, min(1.0, i / (rate * 0.01), (n - 1 - i) / (rate * 0.015)))
            frames += struct.pack("<h", int(32767 * 0.3 * env * math.sin(2 * math.pi * freq * i / rate)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))

def prepare():
    """Builds the beep and the spoken phrases if they are missing. Safe to call every startup."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not _BEEP.exists():
            _write_beep(_BEEP)
        todo = [t for t in ACK_PHRASES if not (_phrase_file(t).exists() and _phrase_file(t).stat().st_size > 0)]
        if todo and shutil.which("festival"):
            lines = ["(voice_cmu_us_slt_arctic_hts)"]
            for t in todo:
                safe = t.replace('"', "").replace("\\", "")
                lines.append('(utt.save.wave (utt.synth (Utterance Text "%s")) "%s")' % (safe, _phrase_file(t)))
            subprocess.run(["festival", "--pipe"], input="\n".join(lines), text=True, capture_output=True, timeout=180)
        have = sum(1 for t in ACK_PHRASES if _phrase_file(t).exists())
        print(f"[Wake] Acknowledgement sounds ready: beep plus {have}/{len(ACK_PHRASES)} phrases.")
    except Exception as e:
        print(f"[Wake] could not prepare sounds: {e}")

def _play(path):
    uid = os.getuid()
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{uid}",
           "PULSE_SERVER": f"unix:/run/user/{uid}/pulse/native"}   # same PulseAudio setup as /tts in server.py
    try:
        subprocess.run(["paplay", str(path)], env=env, capture_output=True, timeout=10)
    except Exception as e:
        print(f"[Wake] could not play {path}: {e}")

def chime():
    if not _BEEP.exists():
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _write_beep(_BEEP)
        except Exception:
            return
    _play(_BEEP)

def acknowledge():
    """Beep, then a random spoken phrase (never the same one twice in a row). Blocks until done."""
    global _last_phrase
    chime()
    ready = [t for t in ACK_PHRASES if _phrase_file(t).exists() and _phrase_file(t).stat().st_size > 0]
    if len(ready) > 1 and _last_phrase in ready:
        ready.remove(_last_phrase)
    if ready:
        _last_phrase = random.choice(ready)
        _play(_phrase_file(_last_phrase))
        return _last_phrase
    return None
