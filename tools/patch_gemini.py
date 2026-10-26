#!/usr/bin/env python3
"""One-time patch: add the optional Gemini provider route to server.py and the toggle / 'gemini:' trigger to sentinel_v2.html.
Backs both files up to backups/*.bak-gemini first and asserts every anchor matches exactly once."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch(path, pairs):
    p = ROOT / path
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = s.count(old)
        assert n == 1, f"{path}: anchor matched {n} times: {old[:70]!r}"
    shutil.copy2(p, ROOT / "backups" / (p.name + ".bak-gemini"))
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", path)


SERVER_ROUTES = '''# ── OPTIONAL GEMINI PROVIDER (Ollama stays the default; the UI opts in per message or with a toggle) ──
@app.get("/api/gemini/status", dependencies=[Depends(verify_key)])
async def gemini_status():
    import gemini_proxy
    return {"configured": bool(gemini_proxy.api_key()), "model": gemini_proxy.model_name()}

@app.post("/api/gemini/chat", dependencies=[Depends(verify_key)])
async def gemini_chat(req: Request):
    """Same shape the UI sends to Ollama; answers as Ollama-style NDJSON. Any failure returns a non-200 so the UI can fall back."""
    from fastapi.responses import JSONResponse, StreamingResponse
    import gemini_proxy
    try:
        payload = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bad JSON")
    gen = gemini_proxy.stream_chat(payload.get("messages") or [], payload.get("options"))
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        first = None
    except gemini_proxy.GeminiError as e:
        print(f"[Gemini] {e.status}: {e.message}")
        return JSONResponse({"error": e.message}, status_code=e.status)
    except Exception as e:
        print(f"[Gemini] unreachable: {type(e).__name__}")
        return JSONResponse({"error": "Could not reach Gemini."}, status_code=502)

    async def body():
        if first is not None:
            yield first
        try:
            async for line in gen:
                yield line
        except Exception as e:
            print(f"[Gemini] stream broke: {type(e).__name__}")
            yield json.dumps({"error": "Gemini stream ended early."}) + "\\n"
    return StreamingResponse(body(), media_type="application/x-ndjson")

'''

UI_JS = '''// ── Gemini (optional provider; Ollama stays the default) ──
var geminiOn=(function(){try{return localStorage.getItem('sentinel_gemini')==='1';}catch(e){return false;}})();
var _geminiOnce=false;   // true for one message that started with "gemini:" or "ask gemini"
function updateGeminiBadge(){
  var b=document.getElementById('gemBadge'),l=document.getElementById('gemLabel');
  if(!b||!l)return;
  l.textContent=geminiOn?'GEMINI ON':'GEMINI OFF';
  b.style.opacity=geminiOn?'1':'0.55';
}
async function toggleGemini(){
  if(!geminiOn){
    try{
      var r=await bfetch(backend()+'/api/gemini/status');
      var d=await r.json();
      if(!d.configured){addMsg('ai','⚠ Gemini has no key yet. Add GEMINI_API_KEY to ~/.config/sentinel/.env and restart the backend.');return;}
    }catch(e){addMsg('ai','⚠ Could not check Gemini (restart the backend so it picks up the new route).');return;}
  }
  geminiOn=!geminiOn;
  try{localStorage.setItem('sentinel_gemini',geminiOn?'1':'0');}catch(e){}
  updateGeminiBadge();
}
function useGeminiNow(){return !_voiceTurn&&(geminiOn||_geminiOnce);}
async function chatFetch(payload){
  if(useGeminiNow()){
    try{
      var gr=await bfetch(backend()+'/api/gemini/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:payload.messages,options:payload.options})});
      if(gr.ok){gr._label='gemini';return gr;}
      var why='';try{why=(await gr.json()).error||'';}catch(e){}
      addMsg('ai','⚠ Gemini unavailable ('+(why||gr.status)+'). Answering with Ollama instead.');
    }catch(e){addMsg('ai','⚠ Could not reach Gemini. Answering with Ollama instead.');}
  }
  return fetch(ollama()+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
}
setTimeout(updateGeminiBadge,0);
'''

patch("server.py", [
    ('@app.get("/modes", dependencies=[Depends(verify_key)])', SERVER_ROUTES + '@app.get("/modes", dependencies=[Depends(verify_key)])'),
])

patch("sentinel_v2.html", [
    # toggle pill next to the mode badge
    ('<span class="mb-auto" id="mbAuto">AUTO</span></div>\n',
     '<span class="mb-auto" id="mbAuto">AUTO</span></div>\n'
     '  <div class="mode-badge" id="gemBadge" onclick="toggleGemini()" title="Send chat to Gemini. Click to toggle. Or start one message with gemini: to use it just for that message"><span>✦</span><span id="gemLabel">GEMINI OFF</span></div>\n'),
    # helpers
    ('function logOllamaPayload(stage,payload){', UI_JS + 'function logOllamaPayload(stage,payload){'),
    # per-message trigger
    ("  if(!text&&!att) return;\n  if(!voice&&text&&!att&&await tryGameCommand(text)) return;",
     "  if(!text&&!att) return;\n"
     "  _geminiOnce=false;\n"
     "  if(!voice){var gm=text.match(/^(?:ask\\s+gemini\\s*[:,]?\\s*|gemini\\s*:\\s*)([\\s\\S]+)/i);if(gm){text=gm[1].trim();_geminiOnce=true;}}\n"
     "  if(!voice&&text&&!att&&await tryGameCommand(text)) return;"),
    # chat call
    ("    logOllamaPayload('chat',payload);\n    var res=await fetch(ollama()+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});",
     "    logOllamaPayload('chat',payload);\n    var res=await chatFetch(payload);"),
    ("meta.textContent='SENTINEL ['+chosenModel+'] · '+ts()+(ctxTag?' · ctx:'+ctxTag:'');",
     "meta.textContent='SENTINEL ['+(res._label||chosenModel)+'] · '+ts()+(ctxTag?' · ctx:'+ctxTag:'');"),
    # follow-up call
    ("  logOllamaPayload('follow-up',payload);\n  var res=await fetch(ollama()+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});",
     "  logOllamaPayload('follow-up',payload);\n  var res=await chatFetch(payload);"),
    ("meta.textContent='SENTINEL ['+model+'] · '+ts()+' · after results';",
     "meta.textContent='SENTINEL ['+(res._label||model)+'] · '+ts()+' · after results';"),
])
