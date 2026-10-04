import os
import shutil
import subprocess
from pathlib import Path
from fastapi import HTTPException, Header

# 1. Safe Token Access: No hardcoded fallbacks exposed
API_KEY = os.environ.get("SENTINEL_API_KEY")
if not API_KEY:
    # If not set in terminal env, use standard secure local configuration tree
    config_path = Path.home() / ".config" / "sentinel" / ".env"
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.startswith("SENTINEL_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip('"')
                
if not API_KEY:
    raise RuntimeError("SENTINEL_API_KEY not set (env var or ~/.config/sentinel/.env)")

def verify_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Sentinel access handshake failed.")

# 2. Strict Directory Sandboxing for File Alteration Actions
SAFE_PATHS = [
    Path.home() / "Sentinel",
    Path.home() / "Documents",
    Path.home() / ".sentinel_memory.json"
]

def verify_safe_path(target_path: str) -> Path:
    p = Path(target_path).expanduser().resolve()
    # Check if target sits cleanly inside allowed user sandboxes
    for safe_dir in SAFE_PATHS:
        try:
            if p == safe_dir or safe_dir in p.parents:
                return p
        except:
            pass
    raise HTTPException(status_code=403, detail="File operation rejected: Access restricted to Sentinel directories.")

# 3. Clean Array-based Execution to totally avoid Shell Injection Vulns
def secure_clipboard_set(text: str):
    for tool in ["xclip", "xsel"]:
        if shutil.which(tool):
            cmd = [tool, "-selection", "clipboard"] if tool == "xclip" else [tool, "--clipboard", "--input"]
            try:
                subprocess.run(cmd, input=text, text=True, check=True, capture_output=True, timeout=5)
                return True
            except:
                continue
    return False
