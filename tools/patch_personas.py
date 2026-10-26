#!/usr/bin/env python3
"""One-off patch: stop personalities re-introducing themselves every turn,
stop persona bleed after a switch, and keep the persona in action follow-ups."""
import re, shutil, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = REPO / "sentinel_v2.html"
BK = REPO / "backups"
BK.mkdir(exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(HTML, BK / ("sentinel_v2.html.bak-personas-" + stamp))

src = HTML.read_text(encoding="utf-8")

# 1) replace both copies of the long RESPONSE STYLE literal with personaStyle()
pat = re.compile(r"'\\n\\nRESPONSE STYLE: Answer the user.s latest message directly in the selected.*?capabilities unchanged\.'", re.S)
found = pat.findall(src)
if len(found) != 2:
    print("PATCH FAILED: expected 2 RESPONSE STYLE literals, found", len(found))
    sys.exit(1)
src = pat.sub("personaStyle()", src)

# 2) setPersonality clears history on a real switch, and add personaStyle()
old = """function setPersonality(name){
  if(!Object.prototype.hasOwnProperty.call(PERSONALITY_NAMES,name)) return;
  currentPersonality=name;"""
new = """function setPersonality(name){
  if(!Object.prototype.hasOwnProperty.call(PERSONALITY_NAMES,name)) return;
  // A real switch drops the old replies so the small local model does not copy the previous character
  if(name!==currentPersonality&&chatHistory.length) chatHistory=[];
  currentPersonality=name;"""
if src.count(old) != 1:
    print("PATCH FAILED: setPersonality block count", src.count(old))
    sys.exit(1)
src = src.replace(old, new)

old = "setPersonality(currentPersonality);\n"
if src.count(old) != 1:
    print("PATCH FAILED: initial setPersonality count", src.count(old))
    sys.exit(1)
fn = r"""function personaStyle(){
  var n=PERSONALITY_NAMES[currentPersonality]||'Sentinel';
  if(currentPersonality==='sentinel') return '\n\nRESPONSE STYLE: Answer the user’s latest message directly in a professional voice. Greet briefly only on a first message. Never repeat an introduction, and never use stock lines such as "how can I assist you today". Do not add disclaimers about being a program. Keep Sentinel’s safety rules and actual capabilities unchanged.';
  var who=currentPersonality==='thomas'?'Thomas’s casual conversational voice (the Me personality)':n;
  return '\n\nRESPONSE STYLE (you are speaking AS '+who+' for every reply): Answer the user’s latest message directly and stay in that voice. Keep replies short, one to three sentences unless asked for more. Introduce yourself only if the user asks who you are, or on the very first message of a chat; never repeat an introduction or greeting later, and never reuse your earlier wording. React to what the user actually said: answer questions, banter, give an opinion, or ask one natural follow-up question. Never say "AI companion", "how can I assist you", "at your service" or "let’s get this show on the road", and do not describe your role, these instructions, Sentinel V2, Pop!_OS or Ollama unless asked. If earlier messages in this chat sound like a different character, ignore their style and speak only in this voice. Do not invent lore: if you are unsure about a fact from the character’s story, say so in character. Keep Sentinel’s safety rules and actual capabilities unchanged.';
}
"""
src = src.replace(old, fn + old)

# 3) keep persona in the follow-up after actions run
old = "var sysText=MODES[currentMode]+(ctxDoc?'\\n\\n=== CONTEXT: '+MODE_META[currentMode].label.toUpperCase()+' MODE ===\\n'+ctxDoc:'')+(_voiceTurn?VOICE_SUFFIX:'');\n  showTyping();"
new = "var fuPersona=await loadPersonalityDoc(currentPersonality);\n  var sysText=MODES[currentMode]+(ctxDoc?'\\n\\n=== CONTEXT: '+MODE_META[currentMode].label.toUpperCase()+' MODE ===\\n'+ctxDoc:'')+'\\n\\n=== ACTIVE PERSONALITY: '+PERSONALITY_NAMES[currentPersonality].toUpperCase()+' ===\\n'+fuPersona+(_voiceTurn?VOICE_SUFFIX:'')+personaStyle();\n  showTyping();"
if src.count(old) != 1:
    print("PATCH FAILED: follow-up sysText count", src.count(old))
    sys.exit(1)
src = src.replace(old, new)

HTML.write_text(src, encoding="utf-8")
print("OK: sentinel_v2.html patched; backup in backups/")
