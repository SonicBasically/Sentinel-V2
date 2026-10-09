import ast
import httpx
import json
import logging
import re

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "mistral:latest"

# Tool-calling prompt (used by /api/chat in backend/main.py)
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

# Conversational prompt for voice. Simple commands (apps, volume, media, time) are
# handled by server.py before they ever reach the model, so no tools here.
CHAT_PROMPT = """You are Sentinel V2, Thomas's local AI assistant running on his Pop!_OS desktop (you are not a satellite).
Your replies are spoken aloud: answer in one or two short sentences of plain text, with no markdown, lists, code or emoji.
You cannot open apps or change settings from this chat, so never claim to have done an action.
If you don't know something, say so briefly."""

CONVERSATION_HISTORY = []


def _parse_action(reply: str):
    match = re.search(r"<ACTION>([\s\S]*?)</ACTION>", reply)
    if not match:
        return None
    raw = match.group(1).strip()
    # Mistral often emits single-quoted pseudo-JSON, so try literal_eval as a fallback.
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    logging.error(f"Failed parsing tool block: {raw[:80]}")
    return None


async def process_chat_with_brain(user_message: str, use_tools: bool = True) -> dict:
    global CONVERSATION_HISTORY

    CONVERSATION_HISTORY.append({"role": "user", "content": user_message})
    if len(CONVERSATION_HISTORY) > 20:
        CONVERSATION_HISTORY = CONVERSATION_HISTORY[-20:]

    prompt = SYSTEM_PROMPT if use_tools else CHAT_PROMPT
    messages = [{"role": "system", "content": prompt}] + CONVERSATION_HISTORY

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "30m",  # stay loaded so the next command has no cold start
                    "options": {"num_predict": 400 if use_tools else 150, "temperature": 0.4},
                },
            )
        if response.status_code == 200:
            reply = response.json().get("message", {}).get("content", "").strip()
            CONVERSATION_HISTORY.append({"role": "assistant", "content": reply})
            return {"reply": reply, "action": _parse_action(reply) if use_tools else None}
        logging.error(f"Ollama returned HTTP {response.status_code}")
    except Exception as e:
        logging.error(f"Ollama connection dropped: {e}")

    CONVERSATION_HISTORY.pop()  # keep user/assistant turns paired after a failure
    return {"reply": "I'm having trouble communicating with my local Ollama engine.", "action": None}
