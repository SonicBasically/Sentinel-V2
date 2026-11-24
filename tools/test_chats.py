#!/usr/bin/env python3
"""Isolated test of chats.py: temp folder, fake key check. Does not touch Chats/ or the live server."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chats
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.testclient import TestClient

chats.CHATS_DIR = Path(tempfile.mkdtemp(prefix="sentinel-chats-test-"))

def verify_key(x_api_key: str = Header(default="")):
    if x_api_key != "k":
        raise HTTPException(401, "Unauthorized")

app = FastAPI()
app.include_router(chats.build_router(verify_key))
c = TestClient(app)
H = {"X-Api-Key": "k"}
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

check("no key -> 401 (list)", c.get("/chats").status_code == 401)
check("no key -> 401 (save)", c.put("/chats/a", json={"messages": []}).status_code == 401)
check("no key -> 401 (delete)", c.delete("/chats/a").status_code == 401)
check("empty list", c.get("/chats", headers=H).json() == {"chats": []})

m = [{"role": "user", "content": "How do I restart nginx?", "images": ["AAAA"]},
     {"role": "assistant", "content": "Run sudo systemctl restart nginx."},
     {"role": "system", "content": "ignored"}]
r = c.put("/chats/one", headers=H, json={"messages": m})
check("save ok + auto title", r.status_code == 200 and r.json()["title"] == "How do I restart nginx?")
check("images/system dropped", c.get("/chats/one", headers=H).json()["messages"] == m[:2][0:0] + [
    {"role": "user", "content": "How do I restart nginx?"}, {"role": "assistant", "content": "Run sudo systemctl restart nginx."}])
check("empty save rejected", c.put("/chats/two", headers=H, json={"messages": []}).status_code == 400)
check("path traversal id rejected", c.get("/chats/..%2Fserver", headers=H).status_code in (400, 404))
check("dotted id rejected", c.put("/chats/a.b", headers=H, json={"messages": m}).status_code == 400)

c.put("/chats/two", headers=H, json={"messages": [{"role": "user", "content": "Minecraft server lag"}]})
names = [x["id"] for x in c.get("/chats", headers=H).json()["chats"]]
check("newest first", names == ["two", "one"])
check("search by message text", [x["id"] for x in c.get("/chats?q=nginx", headers=H).json()["chats"]] == ["one"])
check("search by title, case-insensitive", [x["id"] for x in c.get("/chats?q=MINECRAFT", headers=H).json()["chats"]] == ["two"])
check("search no match", c.get("/chats?q=zzzz", headers=H).json()["chats"] == [])
check("search snippet", "nginx" in c.get("/chats?q=nginx", headers=H).json()["chats"][0]["snippet"].lower())

c.post("/chats/one/rename", headers=H, json={"title": "Nginx help"})
c.put("/chats/one", headers=H, json={"messages": m[:2] + [{"role": "user", "content": "thanks"}]})
d = c.get("/chats/one", headers=H).json()
check("custom title survives later saves", d["title"] == "Nginx help" and len(d["messages"]) == 3)
check("rename blank rejected", c.post("/chats/one/rename", headers=H, json={"title": "  "}).status_code == 400)

r = c.put("/chats/old123", headers=H, json={"messages": m[:2], "created": 1000, "updated": 2000, "keep_time": True})
check("import keeps old time", r.json()["updated"] == 2000)
check("old import sorts last", [x["id"] for x in c.get("/chats", headers=H).json()["chats"]][-1] == "old123")

check("delete ok", c.delete("/chats/two", headers=H).status_code == 200)
check("deleted gone", c.get("/chats/two", headers=H).status_code == 404)
check("delete missing -> 404", c.delete("/chats/two", headers=H).status_code == 404)
big = [{"role": "user", "content": "x" * (9 * 1024 * 1024)}]
check("oversize rejected", c.put("/chats/big", headers=H, json={"messages": big}).status_code == 413)
check("no temp files left", not [p for p in chats.CHATS_DIR.iterdir() if p.name.startswith(".")])

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
