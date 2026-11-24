#!/usr/bin/env python3
"""One-off patch: add the Orb tab (UI) and /tts/status (backend). Each anchor must match exactly once."""
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BK = REPO / "backups"
BK.mkdir(exist_ok=True)

def patch(fname, edits):
    p = REPO / fname
    s = p.read_text(encoding="utf-8")
    shutil.copy2(p, BK / (fname + ".bak-orb"))
    for old, new in edits:
        n = s.count(old)
        assert n == 1, f"{fname}: anchor matched {n} times: {old[:60]!r}"
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", fname)

CSS = """
/* ── Orb tab ── */
#viewtabs{flex-shrink:0;display:flex;gap:4px;padding:8px 18px 0;background:var(--bg1);border-bottom:1px solid var(--border);}
.vtab{font-family:var(--mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--text2);background:none;border:1px solid transparent;border-bottom:none;border-radius:8px 8px 0 0;padding:7px 16px;min-height:32px;cursor:pointer;}
.vtab:hover{color:var(--text);}
.vtab.active{color:var(--accent);background:var(--bg);border-color:var(--border2);margin-bottom:-1px;}
#orbview{display:none;flex:1;min-height:0;align-items:center;justify-content:center;position:relative;overflow:hidden;background:var(--bg);}
#chat.orb-open #orbview{display:flex;}
#chat.orb-open #msgs,#chat.orb-open #mp-panel{display:none;}
#orb{--o:var(--mode,var(--accent));width:min(46vmin,280px);aspect-ratio:1;border-radius:50%;background:radial-gradient(circle at 35% 30%,color-mix(in srgb,var(--o) 50%,#fff) 0%,var(--o) 38%,color-mix(in srgb,var(--o) 35%,#000) 100%);box-shadow:0 0 40px -6px var(--o),0 0 90px -24px var(--o);opacity:0.5;transition:opacity 0.4s,box-shadow 0.4s;animation:orbIdle 5s ease-in-out infinite;}
#orb.talk{opacity:1;box-shadow:0 0 70px 2px var(--o),0 0 160px 8px var(--o);animation:orbTalk 0.9s ease-in-out infinite;}
#orb-lb{position:absolute;bottom:18px;left:0;right:0;text-align:center;font-family:var(--mono);font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);}
@keyframes orbIdle{0%,100%{transform:scale(0.97)}50%{transform:scale(1.03)}}
@keyframes orbTalk{0%,100%{transform:scale(1)}30%{transform:scale(1.09)}60%{transform:scale(1.03)}}
"""

HTML = """<div id="viewtabs" role="tablist"><button class="vtab active" id="vt-chat" role="tab" onclick="showView('chat')">Chat</button><button class="vtab" id="vt-orb" role="tab" onclick="showView('orb')">Orb</button></div>
    <div id="orbview"><div id="orb"></div><div id="orb-lb">quiet</div></div>
    <div id="msgs"></div>"""

JS = """var _view='chat',_orbTimer=null,_browserSpeaking=false,_orbOn=false;
function orbSet(on){
  if(on===_orbOn) return;
  _orbOn=on;
  document.getElementById('orb').classList.toggle('talk',on);
  document.getElementById('orb-lb').textContent=on?'speaking':'quiet';
}
function orbTick(){
  if(_browserSpeaking){orbSet(true);return;}
  if(_host!=='localhost'){orbSet(false);return;}
  bfetch(backend()+'/tts/status').then(function(r){return r.json();}).then(function(d){orbSet(!!d.speaking);}).catch(function(){orbSet(false);});
}
function showView(v){
  _view=(v==='orb')?'orb':'chat';
  document.getElementById('chat').classList.toggle('orb-open',_view==='orb');
  document.getElementById('vt-chat').classList.toggle('active',_view==='chat');
  document.getElementById('vt-orb').classList.toggle('active',_view==='orb');
  try{localStorage.setItem('sentinel_view',_view);}catch(e){}
  if(_orbTimer){clearInterval(_orbTimer);_orbTimer=null;}
  if(_view==='orb'){orbTick();_orbTimer=setInterval(orbTick,300);}
  else{orbSet(false);}
}
try{if(localStorage.getItem('sentinel_view')==='orb') showView('orb');}catch(e){}

function showConfirm(action){"""

UI_EDITS = [
    ("</style>", CSS + "</style>"),
    ('<div id="msgs"></div>', HTML),
    ("function showConfirm(action){", JS),
    ("    speechSynthesis.speak(u);",
     "    u.onstart=function(){_browserSpeaking=true;};\n"
     "    u.onend=u.onerror=function(){_browserSpeaking=false;};\n"
     "    speechSynthesis.speak(u);"),
]

SERVER_EDITS = [
    ('@app.get("/devices", dependencies=[Depends(verify_key)])',
     '@app.get("/tts/status", dependencies=[Depends(verify_key)])\n'
     'def tts_status():\n'
     '    """True while the last spoken reply is still playing (the UI orb polls this)."""\n'
     '    return {"speaking": bool(_tts_proc is not None and _tts_proc.poll() is None)}\n\n'
     '@app.get("/devices", dependencies=[Depends(verify_key)])'),
]

patch("sentinel_v2.html", UI_EDITS)
patch("server.py", SERVER_EDITS)
