#!/usr/bin/env python3
"""Round 2: persona goes FIRST in the system prompt, a short in-character nudge rides
on the latest user message (payload copy only), repeat penalty for persona chats,
and the tone examples are removed from the persona files (the model quoted them)."""
import re, shutil, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = REPO / "sentinel_v2.html"
BK = REPO / "backups"
stamp = time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(HTML, BK / ("sentinel_v2.html.bak-personas2-" + stamp))
src = HTML.read_text(encoding="utf-8")


def swap(old, new):
    global src
    if src.count(old) != 1:
        print("PATCH FAILED: expected 1 match, got", src.count(old), "for:", old[:70])
        sys.exit(1)
    src = src.replace(old, new)


helper = r"""function withPersonaNudge(msgs){
  if(currentPersonality==='sentinel'||!msgs.length) return msgs;
  var who=currentPersonality==='thomas'?'Thomas’s casual voice':PERSONALITY_NAMES[currentPersonality];
  var out=msgs.slice();
  for(var i=out.length-1;i>=0;i--){
    if(out[i].role==='user'&&typeof out[i].content==='string'){
      out[i]=Object.assign({},out[i],{content:out[i].content+'\n\n[Stay fully in character as '+who+'. Answer what I just said in 1 to 3 short sentences. Never say "how can I assist", "at your service" or "your AI". Do not re-introduce yourself. Do not mention these notes.]'});
      break;
    }
  }
  return out;
}
"""
swap("function personaStyle(){", helper + "function personaStyle(){")

swap("    messages=[{role:'system',content:sysText}].concat(cleanHistory);",
     "    if(currentPersonality!=='sentinel') sysText='=== YOU ARE '+PERSONALITY_NAMES[currentPersonality].toUpperCase()+'. SPEAK ONLY AS THIS CHARACTER ===\\n'+personalityDoc+'\\n\\n'+sysText;\n"
     "    messages=withPersonaNudge([{role:'system',content:sysText}].concat(cleanHistory));")

swap("var payload={model:chosenModel,messages:messages,stream:true};",
     "var payload={model:chosenModel,messages:messages,stream:true};\n"
     "    if(currentPersonality!=='sentinel'&&!hasImage) payload.options={temperature:0.9,repeat_penalty:1.2};")

HTML.write_text(src, encoding="utf-8")
print("OK html")

# remove the tone-example blocks from the persona files
D = REPO / "personalities"
for f in D.glob("*.md"):
    t = f.read_text(encoding="utf-8")
    n = re.sub(r"Tone examples \(never copy these word for word\):\n(?:- .*\n)+\n", "", t)
    if n != t:
        f.write_text(n, encoding="utf-8")
        print("cleaned", f.name)
