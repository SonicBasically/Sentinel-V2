import httpx
import json
import logging
import re

OLLAMA_URL = "http://localhost:11434/api/chat"

SYSTEM_PROMPT = """You are Sentinel V2, a deeply integrated local AI system for Thomas.
You control his Pop!_OS machine. When he asks you to do a system task, you MUST use tool calling blocks.

Available Tools you can call:
1. {"tool": "open_app", "target": "terminal"} - open terminal
2. {"tool": "open_app", "target": "files"} - open file manager (Nautilus)
3. {"tool": "open_app", "target": "browser"} - open web browser (Firefox)
4. {"tool": "open_app", "target": "vs code"} - open visual studio code
5. {"tool": "volume_control", "level": 0-100} - set volume level
6. {"tool": "media_toggle"} - pause or play media music
7. {"tool": "get_system_stats"} - check system CPU/RAM metrics

If the user wants you to perform one of these, output the EXACT JSON block inside an <ACTION> tag, like this:
<ACTION>{"tool": "open_app", "target": "terminal"}</ACTION>
Do NOT try to write raw shell code or markdown paths like '✗ open_application' or 'xdg-open'. Always use the tools specified above. Keep your conversational dialogue concise and helpful."""

CONVERSATION_HISTORY = []

async def process_chat_with_brain(user_message: str) -> dict:
    global CONVERSATION_HISTORY
    
    CONVERSATION_HISTORY.append({"role": "user", "content": user_message})
    if len(CONVERSATION_HISTORY) > 20:
        CONVERSATION_HISTORY = CONVERSATION_HISTORY[-20:]
        
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + CONVERSATION_HISTORY
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={"model": "mistral:latest", "messages": messages, "stream": False},
            )
            if response.status_code == 200:
                reply = response.json().get("message", {}).get("content", "")
                CONVERSATION_HISTORY.append({"role": "assistant", "content": reply})
                
                # Rigid extraction matching <ACTION> tags cleanly
                action_match = re.search(r"<ACTION>([\s\S]*?)</ACTION>", reply)
                action_payload = None
                if action_match:
                    try:
                        action_payload = json.loads(action_match.group(1).strip())
                    except Exception as e:
                        logging.error(f"Failed parsing tool block JSON: {e}")
                        
                return {"reply": reply, "action": action_payload}
    except Exception as e:
        logging.error(f"Ollama connection dropped: {e}")
        return {"reply": "I'm having trouble communicating with my local Ollama engine.", "action": None}
