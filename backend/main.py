#!/usr/bin/env python3
import re
import math
import os
import sys
import json
import asyncio
import shutil
import subprocess
import platform
import psutil
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sounddevice as sd
from vosk import Model, KaldiRecognizer

# Import security guards
from security_shield import verify_key, verify_safe_path, secure_clipboard_set
from ollama_brain import process_chat_with_brain

app = FastAPI(title="Sentinel V2 Core Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Loosened to prevent UI handshake lockouts
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

APP_ALIASES = {
    "firefox": "firefox", "browser": "firefox", "web browser": "firefox",
    "terminal": "gnome-terminal", "files": "nautilus", "vs code": "code", "code": "code"
}

class ChatPayload(BaseModel):
    message: str

class FilePayload(BaseModel):
    path: str
    content: str

# Controlled state tracking
voice_task = None
mic_active = False
vosk_model = None

def get_vosk_model():
    global vosk_model
    if vosk_model is None:
        print("[Voice Stack] Loading Vosk Model into cache...")
        import vosk
        vosk.SetLogLevel(-1)
        vosk_model = Model(lang="en-us")
    return vosk_model

async def continuous_mic_capture():
    global mic_active
    loop = asyncio.get_running_loop()
    async_queue = asyncio.Queue()

    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        loop.call_soon_threadsafe(async_queue.put_nowait, bytes(indata))

    try:
        model = get_vosk_model()
        device_info = sd.query_devices(None, 'input')
        samplerate = int(device_info['default_samplerate'])
        recognizer = KaldiRecognizer(model, samplerate)
        
        stream = sd.RawInputStream(samplerate=samplerate, blocksize=8000, device=None,
                                   dtype='int16', channels=1, callback=callback)
        with stream:
            print("[Voice Stack] Microphone Activated via UI Endpoint.")
            while mic_active:
                # Add a minor timeout so it checks the mic_active flag state frequently
                try:
                    data = await asyncio.wait_for(async_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        print(f"\n[Voice Captured]: {text}")
                        asyncio.create_task(handle_voice_intent(text))
    except Exception as e:
        print(f"[Voice Stack Error]: {e}")
    finally:
        mic_active = False
        print("[Voice Stack] Microphone successfully powered down.")

async def handle_voice_intent(text: str):
    print(f"[Brain Routing] Processing Voice Command: '{text}'...")
    await process_chat_with_brain(text)

@app.post("/api/voice/start", dependencies=[Depends(verify_key)])
async def start_voice_listening():
    global voice_task, mic_active
    if mic_active:
        return {"status": "already_listening"}
    
    mic_active = True
    voice_task = asyncio.create_task(continuous_mic_capture())
    return {"status": "listening_started"}

@app.post("/api/voice/stop", dependencies=[Depends(verify_key)])
async def stop_voice_listening():
    global voice_task, mic_active
    if not mic_active:
        return {"status": "already_stopped"}
    
    mic_active = False
    if voice_task:
        voice_task.cancel()
        voice_task = None
    return {"status": "listening_stopped"}

@app.post("/api/chat", dependencies=[Depends(verify_key)])
async def chat_endpoint(payload: ChatPayload):
    result = await process_chat_with_brain(payload.message)
    action = result.get("action")
    
    execution_notes = ""
    if action and "tool" in action:
        tool_name = action["tool"]
        if tool_name == "open_app":
            tgt = action.get("target", "").lower()
            exec_name = APP_ALIASES.get(tgt, tgt)
            if shutil.which(exec_name):
                subprocess.Popen([exec_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
                execution_notes = f"\n\n[Executed Tool: Opened {exec_name}]"
            else:
                execution_notes = f"\n\n[Tool Error: application {exec_name} not found]"
        elif tool_name == "volume_control":
            lvl = max(0, min(100, int(action.get("level", 50))))
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{lvl}%"], capture_output=True)
            execution_notes = f"\n\n[Executed Tool: Volume calibrated to {lvl}%]"

    clean_reply = re.sub(r"<ACTION>[\s\S]*?</ACTION>", "", result["reply"]).strip()
    return {"reply": f"{clean_reply}{execution_notes}"}

@app.post("/api/file/write", dependencies=[Depends(verify_key)])
def safe_write_file(payload: FilePayload):
    safe_target = verify_safe_path(payload.path)
    safe_target.parent.mkdir(parents=True, exist_ok=True)
    safe_target.write_text(payload.content)
    return {"status": "success", "resolved_path": str(safe_target)}

@app.get("/system/info", dependencies=[Depends(verify_key)])
def dynamic_system_info():
    cpu_usage = psutil.cpu_percent(interval=None)
    if math.isnan(cpu_usage) or math.isinf(cpu_usage): cpu_usage = 0.0
    mem = psutil.virtual_memory()
    return {
        "cpu": {"usage_pct": cpu_usage, "model": platform.processor() or "Intel i7-6700"},
        "memory": {"usage_pct": mem.percent, "total_gb": round(mem.total / 1e9, 2)}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")
