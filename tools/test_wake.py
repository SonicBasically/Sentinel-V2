"""Checks wake.strip_wake and wake.is_noise only (no audio, no mic).
Usage: .venv/bin/python tools/test_wake.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wake

CASES = [
    # (what Vosk wrote, (heard, rest))
    ("hey sentinel", (True, "")), ("Hey Sentinel.", (True, "")), ("hey, sentinel", (True, "")),
    ("hay sentinel", (True, "")), ("hey sentinal", (True, "")), ("hey centinel", (True, "")),
    ("a sentinel", (True, "")), ("hey sent null", (True, "")), ("hey sent in el", (True, "")),
    ("hey sentinel open half life", (True, "open half life")),
    ("hey sentinel, set the volume to 35%", (True, "set the volume to 35%")),
    ("okay hey sentinel pause", (True, "pause")), ("i said hey sentinel next song", (True, "next song")),
    ("open half life", (False, "open half life")), ("hello how are you", (False, "hello how are you")),
    ("open sentinel", (False, "open sentinel")), ("play sentinel", (False, "play sentinel")),
    ("sentinel", (False, "sentinel")), ("hey siri", (False, "hey siri")), ("hey send it", (False, "hey send it")),
    ("hey central station", (False, "hey central station")), ("he said sentinel", (False, "he said sentinel")),
    ("pause", (False, "pause")), ("", (False, "")),
]
NOISE = [("the", True), ("uh", True), ("the uh", True), ("pause", False), ("the music", False), ("", True)]

bad = 0
for text, want in CASES:
    got = wake.strip_wake(text)
    if got != want:
        bad += 1; print("FAIL  %r -> %r (wanted %r)" % (text, got, want))
for text, want in NOISE:
    got = wake.is_noise(text)
    if got != want:
        bad += 1; print("FAIL  is_noise(%r) -> %r (wanted %r)" % (text, got, want))
print("all wake checks passed" if not bad else "%d wake check(s) failed" % bad)
sys.exit(1 if bad else 0)
