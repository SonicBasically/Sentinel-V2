#!/usr/bin/env python3
"""
Sentinel UI V3 — Backend Server
"""
import subprocess, shutil, os, platform, psutil, json, mimetypes, base64, time, re
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

API_KEY = "27eac5331994fa105cff896827859aa7"

def verify_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

app = FastAPI(title="Sentinel UI V3 Backend", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

BLOCKED = ["rm -rf /", "rm -rf /*", "mkfs", ":(){:|:&};:", "dd if=/dev/zero of=/dev/sd", "> /dev/sda"]

def safe(cmd):
    return not any(b in cmd.lower() for b in BLOCKED)

class CmdReq(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: Optional[int] = 15

class FileReadReq(BaseModel):
    path: str

class FileWriteReq(BaseModel):
    path: str
    content: str

class ClipboardReq(BaseModel):
    text: str

class MemoryReq(BaseModel):
    key: str
    value: str

class SearchReq(BaseModel):
    query: str

# ── MEMORY STORE ──
MEMORY_FILE = Path.home() / ".sentinel_memory.json"
def load_memory():
    try: return json.loads(MEMORY_FILE.read_text())
    except: return {}
def save_memory(data):
    MEMORY_FILE.write_text(json.dumps(data, indent=2))



def _distro():
    try:
        r = subprocess.run(["lsb_release","-ds"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0: return r.stdout.strip().strip('"')
    except: pass
    try: return Path("/etc/os-release").read_text().split('PRETTY_NAME="')[1].split('"')[0]
    except: pass
    return platform.system()


@app.get("/")
def root(): return {"status": "online", "name": "Sentinel UI V3", "version": "3.0.0"}

@app.get("/system/info", dependencies=[Depends(verify_key)])
def system_info():
    cpu_freq = psutil.cpu_freq()
    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime_s = (datetime.now() - boot).total_seconds()
    uptime = f"{int(uptime_s//3600)}h {int((uptime_s%3600)//60)}m"
    gpus = []
    try:
        r = subprocess.run(["nvidia-smi","--query-gpu=name,memory.total,memory.used,temperature.gpu,utilization.gpu","--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 5:
                    gpus.append({"name":p[0],"memory_total_mb":int(p[1]),"memory_used_mb":int(p[2]),"temp_c":int(p[3]),"utilization_pct":int(p[4])})
    except: pass
    return {
        "hostname": platform.node(), "os": f"{platform.system()} {platform.release()}",
        "distro": _distro(), "kernel": platform.version(), "arch": platform.machine(),
        "cpu": {"model":_cpu_model(),"cores_physical":psutil.cpu_count(logical=False),"cores_logical":psutil.cpu_count(logical=True),"usage_pct":psutil.cpu_percent(interval=0.3),"freq_mhz":round(cpu_freq.current) if cpu_freq else None},
        "memory": {"total_gb":round(mem.total/1e9,1),"used_gb":round(mem.used/1e9,1),"available_gb":round(mem.available/1e9,1),"usage_pct":mem.percent},
        "swap": {"total_gb":round(swap.total/1e9,1),"used_gb":round(swap.used/1e9,1),"usage_pct":swap.percent},
        "disk": {"total_gb":round(disk.total/1e9,1),"used_gb":round(disk.used/1e9,1),"free_gb":round(disk.free/1e9,1),"usage_pct":disk.percent},
        "gpus": gpus, "uptime": uptime, "boot_time": boot.strftime("%Y-%m-%d %H:%M:%S"),
        "load_avg": list(os.getloadavg()), "timestamp": datetime.now().isoformat(),
    }

@app.get("/system/history", dependencies=[Depends(verify_key)])
def system_history():
    """Return 60 snapshots for graphs"""
    mem  = psutil.virtual_memory()
    cpu  = psutil.cpu_percent(interval=0.1)
    return {"cpu": cpu, "mem": mem.percent, "timestamp": datetime.now().isoformat()}

@app.get("/system/processes", dependencies=[Depends(verify_key)])
def top_processes(limit: int = 15):
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status","username"]):
        try:
            i = p.info
            i["memory_percent"] = round(i["memory_percent"] or 0, 2)
            i["cpu_percent"]    = round(i["cpu_percent"]    or 0, 2)
            procs.append(i)
        except: pass
    procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    return {"processes": procs[:limit]}

@app.get("/system/network", dependencies=[Depends(verify_key)])
def network_info():
    ifaces = {k:[{"family":str(a.family),"address":a.address,"netmask":a.netmask} for a in v] for k,v in psutil.net_if_addrs().items()}
    stats  = {k:{"isup":s.isup,"speed_mb":s.speed,"mtu":s.mtu} for k,s in psutil.net_if_stats().items()}
    io = psutil.net_io_counters()
    return {"interfaces":ifaces,"stats":stats,"io":{"bytes_sent_mb":round(io.bytes_sent/1e6,2),"bytes_recv_mb":round(io.bytes_recv/1e6,2)}}

@app.get("/system/disks", dependencies=[Depends(verify_key)])
def disk_info():
    parts = []
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            parts.append({"device":p.device,"mountpoint":p.mountpoint,"fstype":p.fstype,"total_gb":round(u.total/1e9,1),"used_gb":round(u.used/1e9,1),"free_gb":round(u.free/1e9,1),"usage_pct":u.percent})
        except: pass
    return {"partitions": parts}

@app.post("/exec", dependencies=[Depends(verify_key)])
def exec_cmd(req: CmdReq):
    if not safe(req.command): raise HTTPException(403, "Command blocked.")
    cwd = req.cwd or str(Path.home())
    if not os.path.isdir(cwd): cwd = str(Path.home())
    cmd = req.command
    # Try sudo -n first (works if user has NOPASSWD in sudoers)
    # then fall back to pkexec for GUI password prompt
    if cmd.strip().startswith('sudo '):
        cmd = f"sudo -n {cmd.strip()[5:]}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=req.timeout, cwd=cwd)
        if r.returncode != 0 and ('password' in r.stderr.lower() or 'askpass' in r.stderr.lower()):
            # Fallback to pkexec which shows a GUI auth dialog
            cmd2 = req.command.replace('sudo ', 'pkexec ', 1)
            r = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=req.timeout, cwd=cwd)
        return {"stdout":r.stdout,"stderr":r.stderr,"returncode":r.returncode,"command":req.command,"cwd":cwd}
    except subprocess.TimeoutExpired: raise HTTPException(408, f"Timeout after {req.timeout}s")
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/file/read", dependencies=[Depends(verify_key)])
def read_file(req: FileReadReq):
    p = Path(req.path).expanduser().resolve()
    if not p.exists(): raise HTTPException(404, f"Not found: {p}")
    if not p.is_file(): raise HTTPException(400, "Not a file")
    if p.stat().st_size > 10*1024*1024: raise HTTPException(413, "Too large")
    mime, _ = mimetypes.guess_type(str(p))
    is_text = (mime and mime.startswith("text")) or p.suffix in [".py",".js",".ts",".sh",".md",".txt",".json",".yaml",".yml",".toml",".cfg",".conf",".log",".csv",".xml",".html",".css",".rs",".go",".c",".cpp",".h",".java"]
    if is_text:
        return {"path":str(p),"content":p.read_text(errors="replace"),"type":"text","mime":mime}
    return {"path":str(p),"content":base64.b64encode(p.read_bytes()).decode(),"type":"binary","mime":mime,"encoding":"base64"}

@app.post("/file/write", dependencies=[Depends(verify_key)])
def write_file(req: FileWriteReq):
    p = Path(req.path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content)
    return {"path": str(p), "ok": True}

@app.get("/file/ls", dependencies=[Depends(verify_key)])
def list_dir(path: str = "~", show_hidden: bool = False):
    p = Path(path).expanduser().resolve()
    if not p.exists(): raise HTTPException(404, "Not found")
    if not p.is_dir(): raise HTTPException(400, "Not a directory")
    entries = []
    for item in sorted(p.iterdir()):
        if not show_hidden and item.name.startswith("."): continue
        try:
            st = item.stat()
            entries.append({"name":item.name,"type":"dir" if item.is_dir() else "file","size_bytes":st.st_size if item.is_file() else None,"modified":datetime.fromtimestamp(st.st_mtime).isoformat(),"permissions":oct(st.st_mode)[-3:]})
        except: pass
    return {"path":str(p),"entries":entries,"count":len(entries)}

@app.get("/screenshot", dependencies=[Depends(verify_key)])
def take_screenshot():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = str(Path.home() / f"sentinel_screenshot_{ts}.png")
    cmds = [f"scrot '{out}'", f"gnome-screenshot -f '{out}'", f"import -window root '{out}'", f"xwd -root -silent | convert xwd:- '{out}'"]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
            if r.returncode == 0 and Path(out).exists():
                img_b64 = base64.b64encode(Path(out).read_bytes()).decode()
                return {"ok": True, "path": out, "image_b64": img_b64}
        except: continue
    raise HTTPException(500, "Screenshot failed. Try: sudo apt install scrot")

@app.get("/clipboard/get", dependencies=[Depends(verify_key)])
def get_clipboard():
    for cmd in ["xclip -selection clipboard -o", "xsel --clipboard --output", "wl-paste"]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if r.returncode == 0: return {"content": r.stdout}
        except: continue
    raise HTTPException(500, "Clipboard read failed. Install xclip: sudo apt install xclip")

@app.post("/clipboard/set", dependencies=[Depends(verify_key)])
def set_clipboard(req: ClipboardReq):
    for cmd in [f"echo -n '{req.text}' | xclip -selection clipboard", f"echo -n '{req.text}' | xsel --clipboard --input", f"echo -n '{req.text}' | wl-copy"]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
            if r.returncode == 0: return {"ok": True}
        except: continue
    raise HTTPException(500, "Clipboard write failed.")

@app.get("/volume/get", dependencies=[Depends(verify_key)])
def get_volume():
    r = subprocess.run("amixer sget Master 2>/dev/null || pactl get-sink-volume @DEFAULT_SINK@", shell=True, capture_output=True, text=True, timeout=5)
    return {"output": r.stdout.strip()}

@app.post("/volume/set", dependencies=[Depends(verify_key)])
def set_volume(level: int):
    level = max(0, min(100, level))
    cmds = [f"pactl set-sink-volume @DEFAULT_SINK@ {level}%", f"amixer sset Master {level}%"]
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        if r.returncode == 0: return {"ok": True, "level": level}
    raise HTTPException(500, "Volume control failed.")

@app.post("/volume/mute", dependencies=[Depends(verify_key)])
def mute_volume():
    subprocess.run("pactl set-sink-mute @DEFAULT_SINK@ toggle || amixer sset Master toggle", shell=True, timeout=5)
    return {"ok": True}

@app.get("/brightness/get", dependencies=[Depends(verify_key)])
def get_brightness():
    r = subprocess.run("brightnessctl get && brightnessctl max", shell=True, capture_output=True, text=True, timeout=5)
    return {"output": r.stdout.strip()}

@app.post("/brightness/set", dependencies=[Depends(verify_key)])
def set_brightness(level: int):
    level = max(0, min(100, level))
    r = subprocess.run(f"brightnessctl set {level}%", shell=True, capture_output=True, timeout=5)
    return {"ok": r.returncode == 0, "level": level}

@app.get("/memory/get", dependencies=[Depends(verify_key)])
def get_mem(key: Optional[str] = None):
    data = load_memory()
    if key: return {"key": key, "value": data.get(key)}
    return {"memory": data}

@app.post("/memory/set", dependencies=[Depends(verify_key)])
def set_mem(req: MemoryReq):
    data = load_memory()
    data[req.key] = req.value
    save_memory(data)
    return {"ok": True, "key": req.key}

@app.delete("/memory/clear", dependencies=[Depends(verify_key)])
def clear_mem():
    save_memory({})
    return {"ok": True}

@app.get("/wifi/status", dependencies=[Depends(verify_key)])
def wifi_status():
    r = subprocess.run("nmcli radio wifi", shell=True, capture_output=True, text=True, timeout=5)
    return {"status": r.stdout.strip()}

@app.post("/wifi/toggle", dependencies=[Depends(verify_key)])
def wifi_toggle():
    r = subprocess.run("nmcli radio wifi", shell=True, capture_output=True, text=True, timeout=5)
    state = "off" if "enabled" in r.stdout else "on"
    subprocess.run(f"nmcli radio wifi {state}", shell=True, timeout=5)
    return {"ok": True, "new_state": state}

@app.get("/git/status", dependencies=[Depends(verify_key)])
def git_status(path: str = "~"):
    p = str(Path(path).expanduser().resolve())
    r = subprocess.run("git status && git log --oneline -5", shell=True, capture_output=True, text=True, cwd=p, timeout=10)
    return {"output": r.stdout or r.stderr}

@app.get("/env", dependencies=[Depends(verify_key)])
def env_vars():
    keys = ["HOME","USER","SHELL","PATH","LANG","TERM","DISPLAY","XDG_SESSION_TYPE","DESKTOP_SESSION","HOSTNAME","PWD","EDITOR","VISUAL"]
    return {k: os.environ.get(k, "") for k in keys}

class TTSReq(BaseModel):
    text: str

@app.post("/tts", dependencies=[Depends(verify_key)])
def tts(req: TTSReq):
    import re
    text = req.text
    text = re.sub(r'<ACTION>[\s\S]*?</ACTION>', '', text)
    text = re.sub(r'```[\s\S]*?```', 'code block', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = text.strip()[:500]
    if not text:
        return {"ok": False, "error": "No text"}
    try:
        import tempfile, glob, stat
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmpfile = tmp.name
        safe_text = text.replace('"', "'").replace('\\', '')
        festival_script = f'(voice_cmu_us_slt_arctic_hts)(utt.save.wave (utt.synth (Utterance Text "{safe_text}")) "{tmpfile}")'
        subprocess.run(['festival', '--pipe'], input=festival_script, text=True, capture_output=True, timeout=15)
        if os.path.exists(tmpfile) and os.path.getsize(tmpfile) > 0:
            env = {**os.environ,
                   'XDG_RUNTIME_DIR': '/run/user/1000',
                   'PULSE_RUNTIME_PATH': '/run/user/1000/pulse',
                   'PULSE_SERVER': 'unix:/run/user/1000/pulse/native'}
            subprocess.Popen(['paplay', tmpfile], env=env)
            return {"ok": True}
        return {"ok": False, "error": "wav generation failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/devices", dependencies=[Depends(verify_key)])
def get_devices():
    results = {}
    # Bluetooth devices
    r = subprocess.run('bluetoothctl devices', shell=True, capture_output=True, text=True, timeout=5)
    results['bluetooth'] = r.stdout.strip()
    # USB devices
    r2 = subprocess.run('lsusb', shell=True, capture_output=True, text=True, timeout=5)
    results['usb'] = r2.stdout.strip()
    # Network interfaces
    r3 = subprocess.run('ip -br addr', shell=True, capture_output=True, text=True, timeout=5)
    results['network'] = r3.stdout.strip()
    return results

@app.get("/notifications", dependencies=[Depends(verify_key)])
def get_notifications():
    r = subprocess.run(
        'gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.DBus.Introspectable.Introspect 2>/dev/null || echo "No notification access"',
        shell=True, capture_output=True, text=True, timeout=5
    )
    # Try dunst history
    r2 = subprocess.run('dunstctl history 2>/dev/null | head -50', shell=True, capture_output=True, text=True, timeout=5)
    return {"notifications": r2.stdout.strip() or "No notification history available. Install dunst for notification tracking."}


    try:
        r = subprocess.run(["grep","-m1","model name","/proc/cpuinfo"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0: return r.stdout.split(":")[1].strip()
    except: pass
    return platform.processor() or "unknown"

def verify_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

app = FastAPI(title="Sentinel UI V3 Backend", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

BLOCKED = ["rm -rf /", "rm -rf /*", "mkfs", ":(){:|:&};:", "dd if=/dev/zero of=/dev/sd", "> /dev/sda"]

def safe(cmd):
    return not any(b in cmd.lower() for b in BLOCKED)

class CmdReq(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: Optional[int] = 15

class FileReadReq(BaseModel):
    path: str

class FileWriteReq(BaseModel):
    path: str
    content: str

class ClipboardReq(BaseModel):
    text: str

class MemoryReq(BaseModel):
    key: str
    value: str

class SearchReq(BaseModel):
    query: str

# ── MEMORY STORE ──
MEMORY_FILE = Path.home() / ".sentinel_memory.json"
def load_memory():
    try: return json.loads(MEMORY_FILE.read_text())
    except: return {}
def save_memory(data):
    MEMORY_FILE.write_text(json.dumps(data, indent=2))

@app.get("/")
def root(): return {"status": "online", "name": "Sentinel UI V3", "version": "3.0.0"}

@app.get("/system/info", dependencies=[Depends(verify_key)])
def system_info():
    cpu_freq = psutil.cpu_freq()
    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime_s = (datetime.now() - boot).total_seconds()
    uptime = f"{int(uptime_s//3600)}h {int((uptime_s%3600)//60)}m"
    gpus = []
    try:
        r = subprocess.run(["nvidia-smi","--query-gpu=name,memory.total,memory.used,temperature.gpu,utilization.gpu","--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 5:
                    gpus.append({"name":p[0],"memory_total_mb":int(p[1]),"memory_used_mb":int(p[2]),"temp_c":int(p[3]),"utilization_pct":int(p[4])})
    except: pass
    return {
        "hostname": platform.node(), "os": f"{platform.system()} {platform.release()}",
        "distro": _distro(), "kernel": platform.version(), "arch": platform.machine(),
        "cpu": {"model":_cpu_model(),"cores_physical":psutil.cpu_count(logical=False),"cores_logical":psutil.cpu_count(logical=True),"usage_pct":psutil.cpu_percent(interval=0.3),"freq_mhz":round(cpu_freq.current) if cpu_freq else None},
        "memory": {"total_gb":round(mem.total/1e9,1),"used_gb":round(mem.used/1e9,1),"available_gb":round(mem.available/1e9,1),"usage_pct":mem.percent},
        "swap": {"total_gb":round(swap.total/1e9,1),"used_gb":round(swap.used/1e9,1),"usage_pct":swap.percent},
        "disk": {"total_gb":round(disk.total/1e9,1),"used_gb":round(disk.used/1e9,1),"free_gb":round(disk.free/1e9,1),"usage_pct":disk.percent},
        "gpus": gpus, "uptime": uptime, "boot_time": boot.strftime("%Y-%m-%d %H:%M:%S"),
        "load_avg": list(os.getloadavg()), "timestamp": datetime.now().isoformat(),
    }

@app.get("/system/history", dependencies=[Depends(verify_key)])
def system_history():
    """Return 60 snapshots for graphs"""
    mem  = psutil.virtual_memory()
    cpu  = psutil.cpu_percent(interval=0.1)
    return {"cpu": cpu, "mem": mem.percent, "timestamp": datetime.now().isoformat()}

@app.get("/system/processes", dependencies=[Depends(verify_key)])
def top_processes(limit: int = 15):
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status","username"]):
        try:
            i = p.info
            i["memory_percent"] = round(i["memory_percent"] or 0, 2)
            i["cpu_percent"]    = round(i["cpu_percent"]    or 0, 2)
            procs.append(i)
        except: pass
    procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    return {"processes": procs[:limit]}

@app.get("/system/network", dependencies=[Depends(verify_key)])
def network_info():
    ifaces = {k:[{"family":str(a.family),"address":a.address,"netmask":a.netmask} for a in v] for k,v in psutil.net_if_addrs().items()}
    stats  = {k:{"isup":s.isup,"speed_mb":s.speed,"mtu":s.mtu} for k,s in psutil.net_if_stats().items()}
    io = psutil.net_io_counters()
    return {"interfaces":ifaces,"stats":stats,"io":{"bytes_sent_mb":round(io.bytes_sent/1e6,2),"bytes_recv_mb":round(io.bytes_recv/1e6,2)}}

@app.get("/system/disks", dependencies=[Depends(verify_key)])
def disk_info():
    parts = []
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            parts.append({"device":p.device,"mountpoint":p.mountpoint,"fstype":p.fstype,"total_gb":round(u.total/1e9,1),"used_gb":round(u.used/1e9,1),"free_gb":round(u.free/1e9,1),"usage_pct":u.percent})
        except: pass
    return {"partitions": parts}

@app.post("/exec", dependencies=[Depends(verify_key)])
def exec_cmd(req: CmdReq):
    if not safe(req.command): raise HTTPException(403, "Command blocked.")
    cwd = req.cwd or str(Path.home())
    if not os.path.isdir(cwd): cwd = str(Path.home())
    cmd = req.command
    # Try sudo -n first (works if user has NOPASSWD in sudoers)
    # then fall back to pkexec for GUI password prompt
    if cmd.strip().startswith('sudo '):
        cmd = f"sudo -n {cmd.strip()[5:]}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=req.timeout, cwd=cwd)
        if r.returncode != 0 and ('password' in r.stderr.lower() or 'askpass' in r.stderr.lower()):
            # Fallback to pkexec which shows a GUI auth dialog
            cmd2 = req.command.replace('sudo ', 'pkexec ', 1)
            r = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=req.timeout, cwd=cwd)
        return {"stdout":r.stdout,"stderr":r.stderr,"returncode":r.returncode,"command":req.command,"cwd":cwd}
    except subprocess.TimeoutExpired: raise HTTPException(408, f"Timeout after {req.timeout}s")
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/file/read", dependencies=[Depends(verify_key)])
def read_file(req: FileReadReq):
    p = Path(req.path).expanduser().resolve()
    if not p.exists(): raise HTTPException(404, f"Not found: {p}")
    if not p.is_file(): raise HTTPException(400, "Not a file")
    if p.stat().st_size > 10*1024*1024: raise HTTPException(413, "Too large")
    mime, _ = mimetypes.guess_type(str(p))
    is_text = (mime and mime.startswith("text")) or p.suffix in [".py",".js",".ts",".sh",".md",".txt",".json",".yaml",".yml",".toml",".cfg",".conf",".log",".csv",".xml",".html",".css",".rs",".go",".c",".cpp",".h",".java"]
    if is_text:
        return {"path":str(p),"content":p.read_text(errors="replace"),"type":"text","mime":mime}
    return {"path":str(p),"content":base64.b64encode(p.read_bytes()).decode(),"type":"binary","mime":mime,"encoding":"base64"}

@app.post("/file/write", dependencies=[Depends(verify_key)])
def write_file(req: FileWriteReq):
    p = Path(req.path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content)
    return {"path": str(p), "ok": True}

@app.get("/file/ls", dependencies=[Depends(verify_key)])
def list_dir(path: str = "~", show_hidden: bool = False):
    p = Path(path).expanduser().resolve()
    if not p.exists(): raise HTTPException(404, "Not found")
    if not p.is_dir(): raise HTTPException(400, "Not a directory")
    entries = []
    for item in sorted(p.iterdir()):
        if not show_hidden and item.name.startswith("."): continue
        try:
            st = item.stat()
            entries.append({"name":item.name,"type":"dir" if item.is_dir() else "file","size_bytes":st.st_size if item.is_file() else None,"modified":datetime.fromtimestamp(st.st_mtime).isoformat(),"permissions":oct(st.st_mode)[-3:]})
        except: pass
    return {"path":str(p),"entries":entries,"count":len(entries)}

@app.get("/screenshot", dependencies=[Depends(verify_key)])
def take_screenshot():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = str(Path.home() / f"sentinel_screenshot_{ts}.png")
    cmds = [f"scrot '{out}'", f"gnome-screenshot -f '{out}'", f"import -window root '{out}'", f"xwd -root -silent | convert xwd:- '{out}'"]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
            if r.returncode == 0 and Path(out).exists():
                img_b64 = base64.b64encode(Path(out).read_bytes()).decode()
                return {"ok": True, "path": out, "image_b64": img_b64}
        except: continue
    raise HTTPException(500, "Screenshot failed. Try: sudo apt install scrot")

@app.get("/clipboard/get", dependencies=[Depends(verify_key)])
def get_clipboard():
    for cmd in ["xclip -selection clipboard -o", "xsel --clipboard --output", "wl-paste"]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if r.returncode == 0: return {"content": r.stdout}
        except: continue
    raise HTTPException(500, "Clipboard read failed. Install xclip: sudo apt install xclip")

@app.post("/clipboard/set", dependencies=[Depends(verify_key)])
def set_clipboard(req: ClipboardReq):
    for cmd in [f"echo -n '{req.text}' | xclip -selection clipboard", f"echo -n '{req.text}' | xsel --clipboard --input", f"echo -n '{req.text}' | wl-copy"]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
            if r.returncode == 0: return {"ok": True}
        except: continue
    raise HTTPException(500, "Clipboard write failed.")

@app.get("/volume/get", dependencies=[Depends(verify_key)])
def get_volume():
    r = subprocess.run("amixer sget Master 2>/dev/null || pactl get-sink-volume @DEFAULT_SINK@", shell=True, capture_output=True, text=True, timeout=5)
    return {"output": r.stdout.strip()}

@app.post("/volume/set", dependencies=[Depends(verify_key)])
def set_volume(level: int):
    level = max(0, min(100, level))
    cmds = [f"pactl set-sink-volume @DEFAULT_SINK@ {level}%", f"amixer sset Master {level}%"]
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        if r.returncode == 0: return {"ok": True, "level": level}
    raise HTTPException(500, "Volume control failed.")

@app.post("/volume/mute", dependencies=[Depends(verify_key)])
def mute_volume():
    subprocess.run("pactl set-sink-mute @DEFAULT_SINK@ toggle || amixer sset Master toggle", shell=True, timeout=5)
    return {"ok": True}

@app.get("/brightness/get", dependencies=[Depends(verify_key)])
def get_brightness():
    r = subprocess.run("brightnessctl get && brightnessctl max", shell=True, capture_output=True, text=True, timeout=5)
    return {"output": r.stdout.strip()}

@app.post("/brightness/set", dependencies=[Depends(verify_key)])
def set_brightness(level: int):
    level = max(0, min(100, level))
    r = subprocess.run(f"brightnessctl set {level}%", shell=True, capture_output=True, timeout=5)
    return {"ok": r.returncode == 0, "level": level}

@app.get("/memory/get", dependencies=[Depends(verify_key)])
def get_mem(key: Optional[str] = None):
    data = load_memory()
    if key: return {"key": key, "value": data.get(key)}
    return {"memory": data}

@app.post("/memory/set", dependencies=[Depends(verify_key)])
def set_mem(req: MemoryReq):
    data = load_memory()
    data[req.key] = req.value
    save_memory(data)
    return {"ok": True, "key": req.key}

@app.delete("/memory/clear", dependencies=[Depends(verify_key)])
def clear_mem():
    save_memory({})
    return {"ok": True}

@app.get("/wifi/status", dependencies=[Depends(verify_key)])
def wifi_status():
    r = subprocess.run("nmcli radio wifi", shell=True, capture_output=True, text=True, timeout=5)
    return {"status": r.stdout.strip()}

@app.post("/wifi/toggle", dependencies=[Depends(verify_key)])
def wifi_toggle():
    r = subprocess.run("nmcli radio wifi", shell=True, capture_output=True, text=True, timeout=5)
    state = "off" if "enabled" in r.stdout else "on"
    subprocess.run(f"nmcli radio wifi {state}", shell=True, timeout=5)
    return {"ok": True, "new_state": state}

@app.get("/git/status", dependencies=[Depends(verify_key)])
def git_status(path: str = "~"):
    p = str(Path(path).expanduser().resolve())
    r = subprocess.run("git status && git log --oneline -5", shell=True, capture_output=True, text=True, cwd=p, timeout=10)
    return {"output": r.stdout or r.stderr}

@app.get("/env", dependencies=[Depends(verify_key)])
def env_vars():
    keys = ["HOME","USER","SHELL","PATH","LANG","TERM","DISPLAY","XDG_SESSION_TYPE","DESKTOP_SESSION","HOSTNAME","PWD","EDITOR","VISUAL"]
    return {k: os.environ.get(k, "") for k in keys}

class TTSReq(BaseModel):
    text: str

@app.post("/tts", dependencies=[Depends(verify_key)])
def tts(req: TTSReq):
    import re
    text = req.text
    text = re.sub(r'<ACTION>[\s\S]*?</ACTION>', '', text)
    text = re.sub(r'```[\s\S]*?```', 'code block', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = text.strip()[:500]
    if not text:
        return {"ok": False, "error": "No text"}
    try:
        import tempfile, glob, stat
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmpfile = tmp.name
        safe_text = text.replace('"', "'").replace('\\', '')
        festival_script = f'(voice_cmu_us_slt_arctic_hts)(utt.save.wave (utt.synth (Utterance Text "{safe_text}")) "{tmpfile}")'
        subprocess.run(['festival', '--pipe'], input=festival_script, text=True, capture_output=True, timeout=15)
        if os.path.exists(tmpfile) and os.path.getsize(tmpfile) > 0:
            env = {**os.environ,
                   'XDG_RUNTIME_DIR': '/run/user/1000',
                   'PULSE_RUNTIME_PATH': '/run/user/1000/pulse',
                   'PULSE_SERVER': 'unix:/run/user/1000/pulse/native'}
            subprocess.Popen(['paplay', tmpfile], env=env)
            return {"ok": True}
        return {"ok": False, "error": "wav generation failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/devices", dependencies=[Depends(verify_key)])
def get_devices():
    results = {}
    # Bluetooth devices
    r = subprocess.run('bluetoothctl devices', shell=True, capture_output=True, text=True, timeout=5)
    results['bluetooth'] = r.stdout.strip()
    # USB devices
    r2 = subprocess.run('lsusb', shell=True, capture_output=True, text=True, timeout=5)
    results['usb'] = r2.stdout.strip()
    # Network interfaces
    r3 = subprocess.run('ip -br addr', shell=True, capture_output=True, text=True, timeout=5)
    results['network'] = r3.stdout.strip()
    return results

@app.get("/notifications", dependencies=[Depends(verify_key)])
def get_notifications():
    r = subprocess.run(
        'gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.DBus.Introspectable.Introspect 2>/dev/null || echo "No notification access"',
        shell=True, capture_output=True, text=True, timeout=5
    )
    # Try dunst history
    r2 = subprocess.run('dunstctl history 2>/dev/null | head -50', shell=True, capture_output=True, text=True, timeout=5)
    return {"notifications": r2.stdout.strip() or "No notification history available. Install dunst for notification tracking."}


    try:
        r = subprocess.run(["grep","-m1","model name","/proc/cpuinfo"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0: return r.stdout.split(":")[1].strip()
    except: pass
    return platform.processor() or "unknown"

def _distro():
    try:
        r = subprocess.run(["lsb_release","-ds"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0: return r.stdout.strip().strip('"')
    except: pass
    try: return Path("/etc/os-release").read_text().split('PRETTY_NAME="')[1].split('"')[0]
    except: pass
    return platform.system()

if __name__ == "__main__":
    import uvicorn
    print("\n  SENTINEL UI V3 — Backend")
    print("  ─────────────────────────")
    print("  http://localhost:8765")
    print("  Docs: http://localhost:8765/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")
