"""Checks for the voice follow-up (the mic opens by itself after Sentinel asks a question).
No microphone, speakers or network are used. Usage: .venv/bin/python tools/test_followup_voice.py"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("SENTINEL_API_KEY", "test-key-not-real")
import wake, voice_commands as vc

bad = 0
def check(label, got, want):
    global bad
    if got != want:
        bad += 1; print("FAIL  %s -> %r (wanted %r)" % (label, got, want))

# ── is_question ──
for text, want in [
    ("Which one did you mean: Half-Life, Half-Life 2?", True),
    ("I found two. Do you want me to open the first one?", True),
    ("Do you want me to open it?", True), ('He asked "are you sure?"', True),
    ("Opening YouTube.", False), ("Playing Kalimba by Mr. Scruff.", False),
    ("Done. Is there anything else I can help with?", False), ("How can I help you today?", False),
    ("Anything else?", False), ("Which game, S.T.A.L.K.E.R.?", True),
    ("What would you like to listen to?", True), ("", False), ("?", False),
]:
    check("is_question(%r)" % text, wake.is_question(text), want)

# ── pick_choice ──
C2 = [{"id": "a", "name": "Half-Life"}, {"id": "b", "name": "Half-Life 2"}]
C3 = [{"id": "x", "name": "Sonic Mania"}, {"id": "y", "name": "Sonic Forces"}, {"id": "z", "name": "Portal 2"}]
pick = lambda t, c: (lambda r: r if isinstance(r, str) or r is None else r["id"])(vc.pick_choice(t, c))
for text, c, want in [
    ("half life", C2, "a"), ("half life two", C2, "b"), ("half life 2", C2, "b"),
    ("the first one", C2, "a"), ("the second one", C2, "b"), ("second", C2, "b"), ("two", C2, "b"),
    ("number one", C2, "a"), ("the last one", C3, "z"), ("third", C3, "z"), ("hey sentinel the second", C3, "y"),
    ("sonic mania", C3, "x"), ("forces", C3, "y"), ("portal", C3, "z"),
    ("never mind", C3, "cancel"), ("cancel", C3, "cancel"), ("no", C3, "cancel"),
    ("sonic", C3, None), ("third", C2, None), ("what time is it", C3, None), ("open youtube", C3, None),
]:
    check("pick_choice(%r)" % text, pick(text, c), want)

# ── server-side behavior (everything slow or physical is faked) ──
import server

class FakeProc:
    def __init__(self, secs): self.end = time.monotonic() + secs
    def poll(self): return None if time.monotonic() < self.end else 0

async def run():
    server.voice_replies.clear()
    # a command that asks "Which one?" stores the choices, and the very next answer launches one
    asked = {"handled": True, "ok": False, "reply": "Which one did you mean: Half-Life, Half-Life 2?", "choices": C2}
    server.voice_commands.try_command = lambda text, aliases=None: asked
    item = await server.handle_voice_intent("open half life")
    check("question reply is marked followup", item["followup"], True)
    check("choices remembered", bool(server.pending_choice), True)
    launched = []
    server.voice_commands.game_lib.launch = lambda gid: launched.append(gid) or {"ok": True}
    item = await server.handle_voice_intent("the second one")
    check("answer launches the second choice", (launched, item["reply"]), (["b"], "Launching Half-Life 2."))
    check("answer is not a question", item["followup"], False)
    check("choices cleared after one answer", server.pending_choice, None)
    # an unrelated next sentence drops the choices and is handled as a normal command
    server.pending_choice = {"choices": C2, "until": time.monotonic() + 60}
    server.voice_commands.try_command = lambda text, aliases=None: {"handled": True, "ok": True, "reply": "Opening YouTube."}
    item = await server.handle_voice_intent("open youtube")
    check("unrelated sentence runs normally", (item["reply"], server.pending_choice), ("Opening YouTube.", None))
    # expired choices are ignored
    server.pending_choice = {"choices": C2, "until": time.monotonic() - 1}
    launched.clear()
    await server.handle_voice_intent("the second one")
    check("expired choices ignored", launched, [])

    # follow-up timing: wait for the UI to take the reply, then for the spoken reply to finish
    server.mic_active = True
    async def scenario(pop_after, speak_secs, gen_bump=False, wake="busy"):
        server.voice_replies.clear(); server.listen_request = False
        server.wake_state = wake; server.cmd_gen += 1; gen = server.cmd_gen
        it = server._push_reply("q", "What do you want to open?")
        t0, seen = time.monotonic(), {}
        async def ui():
            if pop_after is None: return
            await asyncio.sleep(pop_after); server.voice_replies.remove(it)
            if speak_secs is not None:
                await asyncio.sleep(0.3); server._tts_proc = FakeProc(speak_secs); server._tts_count += 1
        done = {"v": False}
        async def follow():
            await server._open_followup(it, gen); done["v"] = True
        async def loop_side():       # stands in for the capture loop picking up listen_request
            while not done["v"]:
                if server.listen_request:
                    seen["t"] = time.monotonic() - t0; server.listen_request = False; server.wake_state = "awake"; return
                await asyncio.sleep(0.05)
        async def bump():
            if gen_bump: await asyncio.sleep(0.5); server.cmd_gen += 1
        await asyncio.gather(follow(), ui(), loop_side(), bump())
        return seen.get("t"), server.wake_state
    t, st = await scenario(0.3, 1.0)
    check("mic opens after the spoken reply ends", (t is not None and t >= 0.3 + 0.3 + 1.0 + 0.4 - 0.05, st), (True, "awake"))
    t, st = await scenario(None, None)
    check("gives up if nobody picks up the reply", (t, st), (None, "idle"))
    t, st = await scenario(0.3, 0.5, gen_bump=True)
    check("a newer command cancels the follow-up", (t, st), (None, "busy"))
    t, st = await scenario(0.3, 0.5, wake="awake")
    check("already awake: nothing to do", t, None)
    # speech that is not a command is handed to the chat window, which answers it like typed chat
    server.mic_active = True
    server.voice_replies.clear()
    server.voice_commands.try_command = lambda text, aliases=None: None
    item = await server.handle_voice_intent("why is my disk full")
    check("non-command speech is handed over", (item.get("handoff"), list(server.voice_replies) == [item]), (True, True))
    out = await server.get_last_voice_response()
    check("poll reports the handoff", (out["status"], out["handoff"], out["transcript"]), ("new", True, "why is my disk full"))
    # when the chat window has spoken its final reply it reports it
    server.wake_state = "idle"
    r = await server.voice_question(server.VoiceQuestionReq(reply="That is the answer.", spoken=True))
    check("a statement does not open the mic", (r["followup"], server.wake_state), (False, "idle"))
    server.listen_request = False
    server._tts_proc = FakeProc(0.5); server._tts_count += 1   # the question is being spoken right now
    t0 = time.monotonic()
    r = await server.voice_question(server.VoiceQuestionReq(reply="Want me to clear the caches?", spoken=True))
    check("a question starts the follow-up", (r["followup"], server.wake_state), (True, "busy"))
    while not server.listen_request and time.monotonic() - t0 < 5:
        await asyncio.sleep(0.05)
    check("mic opens only after the speech ended", (server.listen_request, time.monotonic() - t0 >= 0.5 + 0.4 - 0.05), (True, True))
    server.listen_request = False; server.wake_state = "awake"
    await asyncio.sleep(0.2)
    r = await server.voice_question(server.VoiceQuestionReq(reply="Want more?", spoken=True))
    check("not while a newer command is running", (r["followup"], server.wake_state), (False, "awake"))
    server.wake_state = "idle"; server.mic_active = False
    r = await server.voice_question(server.VoiceQuestionReq(reply="Want more?", spoken=True))
    check("not when the mic is off", r["followup"], False)
    server.wake_state = "idle"
    server.mic_active = False

asyncio.run(run())
print("all follow-up checks passed" if not bad else "%d follow-up check(s) failed" % bad)
sys.exit(1 if bad else 0)
