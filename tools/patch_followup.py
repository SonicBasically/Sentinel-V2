#!/usr/bin/env python3
"""One-off patch: action follow-ups for sentinel_v2.html.

After an action runs, its output goes back to the model, which can explain it or chain up to
3 follow-up steps. Read-only commands run on their own; anything that changes the system asks first.
Backs up first and refuses to change anything unless every anchor matches exactly once."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "sentinel_v2.html"
BACKUP = ROOT / "backups" / "sentinel_v2.html.bak-followup"

BLOCK = r'''

// ── READONLY-START (tested by tools/test_followup.py) ──
// Decides whether a model-written shell command only reads. Default is "no": anything not recognised asks first.
var RO_PLAIN={pwd:1,whoami:1,id:1,uname:1,uptime:1,free:1,df:1,du:1,ls:1,cat:1,head:1,wc:1,cut:1,tr:1,echo:1,printf:1,stat:1,which:1,whereis:1,type:1,lsblk:1,lscpu:1,lsusb:1,lspci:1,lsmod:1,ps:1,pgrep:1,lsof:1,findmnt:1,w:1,who:1,last:1,grep:1,egrep:1,fgrep:1};
var SENSITIVE_RE=/(\.env\b|\.ssh|id_rsa|id_ed25519|\.gnupg|\/etc\/shadow|\/etc\/sudoers|sentinel\/|\.aws|\.netrc|password|passwd|secret|token|api[_-]?key|\.bash_history|\.zsh_history|\.mozilla|\.librewolf|login\.json|key[34]\.db)/i;
function parseShell(cmd){
  var segs=[],toks=[],cur='',inTok=false,q=null,bad=false;
  function endTok(){if(inTok){toks.push(cur);cur='';inTok=false;}}
  function endSeg(){endTok();if(toks.length)segs.push(toks);toks=[];}
  for(var i=0;i<cmd.length;i++){
    var c=cmd[i],n=cmd[i+1];
    if(q==="'"){if(c==="'")q=null;else cur+=c;continue;}
    if(q==='"'){
      if(c==='"')q=null;
      else if(c==='`'||(c==='$'&&n==='('))bad=true;
      else if(c==='\\'&&n){cur+=n;i++;}
      else cur+=c;
      continue;
    }
    if(c==="'"||c==='"'){q=c;inTok=true;continue;}
    if(c==='\\'&&n){cur+=n;i++;inTok=true;continue;}
    if(c==='`'||(c==='$'&&n==='(')||c==='<'||c==='>'){bad=true;continue;}
    if(c==='&'){if(n==='&'){i++;endSeg();}else bad=true;continue;}
    if(c==='|'){if(n==='|')i++;endSeg();continue;}
    if(c===';'||c==='\n'){endSeg();continue;}
    if(c===' '||c==='\t'||c==='\r'){endTok();continue;}
    cur+=c;inTok=true;
  }
  if(q)bad=true;
  endSeg();
  return {segs:segs,bad:bad};
}
function roSegment(t){
  var c=t[0],a=t.slice(1);
  var pos=a.filter(function(x){return x.charAt(0)!=='-';});
  function has(re){return a.some(function(x){return re.test(x);});}
  if(RO_PLAIN[c]===1)return true;
  switch(c){
    case 'tail':return !has(/^(-[a-zA-Z]*[fF]|--follow)/);
    case 'sort':return !has(/^(-[a-zA-Z]*o|--output)/);
    case 'uniq':return pos.length<=1;
    case 'date':return !has(/^(-[a-zA-Z]*s|--set)/)&&pos.every(function(x){return x.charAt(0)==='+';});
    case 'hostname':return pos.length===0;
    case 'find':return !has(/^-(delete|exec|execdir|ok|okdir|fprint|fprint0|fprintf|fls)$/);
    case 'top':return a.some(function(x){return /^-[a-zA-Z]*b/.test(x);});
    case 'ss':return !has(/^-[a-zA-Z]*K/);
    case 'dmesg':return !has(/^(-[a-zA-Z]*[cCw]|--clear|--read-clear|--follow)/);
    case 'sensors':return !has(/^-[a-zA-Z]*s/);
    case 'ip':return !has(/^(add|del|delete|set|flush|change|replace|append|prepend|save|restore|exec|netns|tuntap|tunnel|up|down)$/);
    case 'awk':return !has(/^(-[a-zA-Z]*[fi]|--file|--include|--source)/)&&!has(/system\s*\(|getline|(print|printf)[^;}]*[>|]/);
    case 'systemctl':return ['status','is-active','is-enabled','is-failed','list-units','list-unit-files','list-timers','list-sockets','show','cat'].indexOf(pos[0])>=0||(pos.length===0&&has(/^--failed$/));
    case 'journalctl':return !has(/^(--(vacuum|rotate|flush|sync|relinquish|smart-relinquish|setup-keys|update-catalog|follow|verify)|-[a-zA-Z]*f)/);
    case 'nvidia-smi':return !has(/^(-(pm|pl|r|e|ac|rac|lgc|rgc|lmc|rmc|c|dm|am|gom|caa|cc|mig)$|--(persistence-mode|power-limit|gpu-reset|ecc-config|applications-clocks|reset-applications-clocks|compute-mode|driver-model|accounting-mode|gom|lock-gpu-clocks|reset-gpu-clocks|lock-memory-clocks|reset-memory-clocks|multi-instance-gpu))/);
    case 'git':return ['status','log','diff','show','rev-parse','ls-files','describe','blame','shortlog'].indexOf(pos[0])>=0&&!has(/^--output/);
    case 'apt':return ['list','show','search','policy'].indexOf(pos[0])>=0;
    case 'apt-cache':return ['policy','show','search','depends','rdepends','madison','showpkg'].indexOf(pos[0])>=0;
    case 'dpkg':return a.length>0&&a.every(function(x){return /^(-l|-L|-s|-S|--list|--listfiles|--status|--search|--get-selections)$/.test(x)||x.charAt(0)!=='-';});
    default:return false;
  }
}
function isReadOnlyCommand(cmd){
  if(typeof cmd!=='string'||!cmd.trim()||cmd.length>500)return false;
  if(SENSITIVE_RE.test(cmd))return false;
  var stripped=cmd.replace(/\s*&>\s*\/dev\/null/g,'').replace(/\s*[0-9]?>\s*\/dev\/null/g,'').replace(/\s*[0-9]?>&[0-9]/g,'');
  var p=parseShell(stripped);
  return !p.bad&&p.segs.length>0&&p.segs.every(roSegment);
}
function needsConfirm(a){
  if(!a)return false;
  if(DANGEROUS[a.type])return true;
  if(a.type==='run_command')return !isReadOnlyCommand(a.command);
  return a.type==='kill_app'||a.type==='close_window';
}
// ── READONLY-END ──

// ── ACTION FOLLOW-UPS: results go back to the model, which can explain them or chain more steps ──
var ACTION_RESULT_TAG='[Action results — output of what Sentinel just ran, not typed by the user]';
var MAX_FOLLOWUPS=3;
function trimOut(s,n){
  s=String(s==null?'':s);
  if(s.length<=n)return s;
  var head=Math.floor(n*0.6),tail=n-head;
  return s.slice(0,head)+'\n…[truncated '+(s.length-n)+' chars]…\n'+s.slice(-tail);
}
function summarizeResults(results){
  return results.map(function(r){
    return 'Action "'+(r.action.description||r.action.type)+'" → '+(r.result.ok?'success':'failed')+': '+trimOut(r.result.output,1500);
  }).join('\n');
}
function needsFollowUp(results){
  return results.some(function(r){
    if(r.result.output==='Cancelled.')return false;
    return r.action.type==='run_command'||!r.result.ok;
  });
}
async function streamFollowUp(model,detail){
  var clean=chatHistory.filter(function(m){return !(m.role==='assistant'&&typeof m.content==='string'&&m.content.indexOf('[Results]')===0);});
  var ctxDoc=await loadModeDoc(currentMode,detail||'brief');
  var sysText=MODES[currentMode]+(ctxDoc?'\n\n=== CONTEXT: '+MODE_META[currentMode].label.toUpperCase()+' MODE ===\n'+ctxDoc:'');
  showTyping();
  var res=await fetch(ollama()+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:model,messages:[{role:'system',content:sysText}].concat(clean),stream:true})});
  hideTyping();
  if(!res.ok)throw new Error('Ollama '+res.status);
  var wrap=document.createElement('div');wrap.className='msg ai';
  var bub=document.createElement('div');bub.className='bubble';
  var meta=document.createElement('div');meta.className='msg-meta';meta.textContent='SENTINEL ['+model+'] · '+ts()+' · after results';
  wrap.appendChild(bub);wrap.appendChild(meta);msgsEl.appendChild(wrap);
  var full='';
  try{
    var reader=res.body.getReader(),dec=new TextDecoder();
    while(true){
      var chunk=await reader.read();
      if(chunk.done)break;
      var lines=dec.decode(chunk.value).split('\n');
      for(var i=0;i<lines.length;i++){
        if(!lines[i].trim())continue;
        try{var j=JSON.parse(lines[i]);if(j.message&&j.message.content){full+=j.message.content;bub.innerHTML=fmt(stripActions(full)||'…');autoScroll();}}catch(e){}
      }
    }
  }catch(se){console.warn('follow-up stream error:',se);}
  return full;
}
async function followUpLoop(model,detail,firstResults){
  var ran={};
  (firstResults||[]).forEach(function(r){ran[JSON.stringify(r.action)]=1;});
  for(var step=1;step<=MAX_FOLLOWUPS;step++){
    stL.textContent='reading the results...';
    var full=await streamFollowUp(model,detail);
    chatHistory.push({role:'assistant',content:full});
    var visible=stripActions(full);
    if(visible)speak(visible);
    var acts=parseActions(full).filter(function(a){var k=JSON.stringify(a);if(ran[k])return false;ran[k]=1;return true;});
    if(!acts.length)break;
    if(step===MAX_FOLLOWUPS){addMsg('ai','Stopped after '+MAX_FOLLOWUPS+' follow-up steps. Tell me to keep going if you want more.');break;}
    var results=await processActions(acts);
    if(!results)break;
    chatHistory.push({role:'user',content:ACTION_RESULT_TAG+'\n'+trimOut(summarizeResults(results),2500)});
    if(!needsFollowUp(results))break;
  }
}
'''

EDITS = [
    # 1. helpers go right after the DANGEROUS table
    ("var DANGEROUS={reboot:1,shutdown:1,suspend:1};",
     "var DANGEROUS={reboot:1,shutdown:1,suspend:1};" + BLOCK),
    # 2. confirmation now depends on what the action does
    ("if(DANGEROUS[action.type]) confirmed=await showConfirm(action);",
     "if(needsConfirm(action)) confirmed=await showConfirm(action);"),
    # 3. send(): results go back to the model instead of being filtered out
    (r"chatHistory.push({role:'assistant',content:'[Results]\n'+summary});",
     r"""chatHistory.push({role:'user',content:ACTION_RESULT_TAG+'\n'+trimOut(summary,2500)});
          if(needsFollowUp(results)){
            await followUpLoop(chosenModel,ctxDetail,results);
            stL.textContent='ready · '+ts();
          }"""),
    # 4. tell the model how this works
    (r"""'- Only reboot/shutdown/suspend need confirmation.\n'+""",
     r"""'- You DO receive the output of your actions: it comes back as a message starting with [Action results]. Read it and explain what it shows in plain language; never claim success without it. If you need more information, output ONE more <ACTION> block (at most 3 follow-up steps per request), and do not repeat an action that already ran.\n'+
'- Commands that only read (df, ls, cat, journalctl, systemctl status, ps, free, ip, nvidia-smi, git status, ...) run automatically. Anything that changes the system (installs, deletes, edits, restarts, kill_app, close_window, reboot, shutdown, suspend) pauses for the user to confirm. A cancelled action comes back as Cancelled; do not retry it.\n'+"""),
]


def main():
    text = TARGET.read_text(encoding="utf-8")
    for i, (old, _new) in enumerate(EDITS, 1):
        n = text.count(old)
        if n != 1:
            print(f"PATCH FAILED: anchor {i} matched {n} times (need exactly 1). Nothing changed.")
            sys.exit(1)
    BACKUP.parent.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BACKUP)
    for old, new in EDITS:
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8")
    print(f"patched {TARGET.name}; backup at {BACKUP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
