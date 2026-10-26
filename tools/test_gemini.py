"""Checks for the optional Gemini provider (gemini_proxy.py and its two routes in server.py).
No network is used: Google's API is faked with httpx.MockTransport. Usage: .venv/bin/python tools/test_gemini.py"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("SENTINEL_API_KEY", "test-key-not-real")
import httpx
import gemini_proxy as gp

bad = 0
def check(label, got, want):
    global bad
    if got != want:
        bad += 1; print("FAIL  %s -> %r (wanted %r)" % (label, got, want))

gp.api_key = lambda: "fake-gemini-key"
gp.model_name = lambda: "test-model"

# ── message conversion ──
png = "iVBORw0KGgo="
body = gp.to_gemini([
    {"role": "system", "content": "SYS A"}, {"role": "system", "content": "SYS B"},
    {"role": "user", "content": "hi"}, {"role": "user", "content": "again", "images": [png]},
    {"role": "assistant", "content": "hello"}, {"role": "user", "content": ""},
])
check("system merged", body["systemInstruction"]["parts"][0]["text"], "SYS A\n\nSYS B")
check("roles", [c["role"] for c in body["contents"]], ["user", "model"])
check("consecutive user merged", len(body["contents"][0]["parts"]), 3)
check("png mime", body["contents"][0]["parts"][2]["inline_data"]["mime_type"], "image/png")
check("starts with user", gp.to_gemini([{"role": "assistant", "content": "x"}])["contents"][0]["role"], "user")

# ── streaming ──
def sse(*texts):
    return "".join("data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": t}]}}]}) + "\r\n\r\n" for t in texts)

seen = {}
def ok_handler(request):
    seen["key"] = request.headers.get("x-goog-api-key"); seen["url"] = str(request.url)
    seen["body"] = json.loads(request.content)
    return httpx.Response(200, text=sse("Hel", "lo"), headers={"content-type": "text/event-stream"})

async def collect(gen):
    return [line async for line in gen]

lines = asyncio.run(collect(gp.stream_chat([{"role": "user", "content": "hi"}], {"temperature": 0.9, "repeat_penalty": 1.2},
                                           transport=httpx.MockTransport(ok_handler))))
texts = [json.loads(l)["message"]["content"] for l in lines if "message" in json.loads(l)]
check("streamed text", "".join(texts), "Hello")
check("ends with done", json.loads(lines[-1]), {"done": True})
check("key sent as header, not in url", (seen["key"], "fake-gemini-key" in seen["url"]), ("fake-gemini-key", False))
check("temperature passed", seen["body"]["generationConfig"]["temperature"], 0.9)
check("repeat_penalty not sent", "repeat_penalty" in json.dumps(seen["body"]), False)

def err_status(status, payload=None, content=None):
    handler = lambda request: httpx.Response(status, json=payload) if payload is not None else httpx.Response(status, text=content or "")
    try:
        asyncio.run(collect(gp.stream_chat([{"role": "user", "content": "hi"}], transport=httpx.MockTransport(handler))))
    except gp.GeminiError as e:
        return e.status
    return None

check("429 -> 429", err_status(429, {"error": {"message": "quota"}}), 429)
check("403 -> 403", err_status(403, {"error": {"message": "denied"}}), 403)
check("500 non-json -> 500", err_status(500, content="oops"), 500)
check("blocked prompt -> 422", err_status(200, content="data: " + json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}) + "\n\n"), 422)
check("empty answer -> 502", err_status(200, content="data: " + json.dumps({"candidates": [{"content": {"parts": []}}]}) + "\n\n"), 502)

real_key = gp.api_key
gp.api_key = lambda: ""
check("no key -> 503", err_status(200, content=""), 503)
gp.api_key = real_key

# ── server routes ──
import server
from fastapi.testclient import TestClient
client = TestClient(server.app)
H = {"X-Api-Key": os.environ["SENTINEL_API_KEY"]}
orig = gp.stream_chat

def fake(handler):
    return lambda messages, options=None: orig(messages, options, transport=httpx.MockTransport(handler))

check("status needs key", client.get("/api/gemini/status").status_code, 401)
check("chat needs key", client.post("/api/gemini/chat", json={"messages": []}).status_code, 401)
st = client.get("/api/gemini/status", headers=H).json()
check("status", st, {"configured": True, "model": "test-model"})

gp.stream_chat = fake(ok_handler)
r = client.post("/api/gemini/chat", headers=H, json={"messages": [{"role": "user", "content": "hi"}]})
check("chat 200", r.status_code, 200)
got = "".join(json.loads(l)["message"]["content"] for l in r.text.splitlines() if l.strip() and "message" in json.loads(l))
check("chat streamed text", got, "Hello")

gp.stream_chat = fake(lambda req: httpx.Response(429, json={"error": {"message": "quota"}}))
r = client.post("/api/gemini/chat", headers=H, json={"messages": [{"role": "user", "content": "hi"}]})
check("chat 429 passes through", (r.status_code, "rate limit" in r.json()["error"].lower()), (429, True))
gp.stream_chat = orig

print("FAILED: %d" % bad if bad else "ALL GEMINI CHECKS PASSED")
sys.exit(1 if bad else 0)
