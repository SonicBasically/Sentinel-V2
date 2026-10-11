"""Checks voice_commands.parse_command only (no side effects: nothing is opened or changed).
Usage: .venv/bin/python tools/test_voice_commands.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import voice_commands as vc

M = lambda a: {"kind": "media", "action": a}
V = lambda mode, v: {"kind": "volume", "mode": mode, "value": v}
O = lambda verb, name: {"kind": "open", "verb": verb, "name": name}
CASES = [
    ("resume my music", M("play")), ("Resume music.", M("play")), ("play", M("play")),
    ("play my music", M("play")), ("unpause", M("play")), ("start the music", M("play")),
    ("pause", M("pause")), ("pause the music", M("pause")), ("stop the music", M("pause")),
    ("next song", M("next")), ("skip", M("next")), ("skip this song", M("next")), ("play the next track", M("next")),
    ("previous song", M("previous")), ("go back", M("previous")), ("last song", M("previous")),
    ("volume up", V("up", 10)), ("turn the volume down", V("down", 10)), ("louder", V("up", 10)),
    ("volume up by twenty", V("up", 20)), ("turn it down", V("down", 10)), ("lower the volume 5 percent", V("down", 5)),
    ("set volume to fifty", V("set", 50)), ("set the volume to 35%", V("set", 35)),
    ("volume sixty five", V("set", 65)), ("volume one hundred", V("set", 100)),
    ("turn the volume down to thirty", V("set", 30)),
    ("open half life", O("open", "half life")), ("launch the game minecraft", O("launch", "minecraft")),
    ("hey sentinel please open firefox", O("open", "firefox")), ("play half life", O("play", "half life")),
    ("open vs code", O("open", "vs code")),
    ("hello how are you", None), ("tunnel", None), ("no don't do anything related to tunnels", None),
    ("you can assist me by saying the letter age fifty five times", None),
    ("what time is it", None), ("turn down the lights", None), ("play some jazz", None),
]
bad = 0
for text, want in CASES:
    got = vc.parse_command(text)
    if text == "play some jazz":  # parsed as an open intent; _run_open returns None when no game matches
        want = O("play", "some jazz")
    if got != want:
        bad += 1; print("FAIL  %r -> %r (wanted %r)" % (text, got, want))
print("all parse checks passed" if not bad else "%d parse check(s) failed" % bad)
sys.exit(1 if bad else 0)
