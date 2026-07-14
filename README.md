# Sentinel V2

A Jarvis-style AI assistant powered by Ollama with full Linux system access.

## Quick Start

```bash
# 1. Install Python dependencies (first time only)
bash setup.sh install

# 2. Launch everything
bash launch.sh
```

## Manual Start

```bash
# Terminal 1 — Ollama
OLLAMA_ORIGINS="*" /snap/ollama/current/bin/ollama serve

# Terminal 2 — Backend
bash setup.sh

# Open in browser
xdg-open sentinel.html
```

## Features

- **Chat** — Streams responses from any local Ollama model
- **Voice input** — Click the mic button, speak, auto-sends (Chrome/Edge)
- **File analysis** — Attach or drag & drop any text/code/config file
- **System metrics** — Live CPU, RAM, Disk, GPU, Uptime in the header bar
- **Command execution** — Backend runs real Linux commands
- **Quick commands** — Sidebar shortcuts for sysinfo, processes, network, etc.
- **Modes** — Assistant / Sysadmin / Developer / Security personas
- **Export** — Save the full conversation as a .txt file

## Backend API (port 8765)

| Endpoint | Description |
|---|---|
| GET /system/info | Full system info (CPU, RAM, GPU, etc.) |
| GET /system/processes | Top processes by CPU |
| GET /system/network | Network interfaces and IO |
| GET /system/disks | Disk partitions and usage |
| POST /exec | Run a shell command |
| POST /file/read | Read a file by path |
| GET /file/ls | List directory |
| GET /env | Key environment variables |

## Desktop Shortcut

```bash
cp SentinelV2.desktop ~/.local/share/applications/
# Edit the Exec path if your home dir is different
```

## Models (pull whichever you want)

```bash
ollama pull mistral        # Best all-around, fits in 6GB VRAM
ollama pull llama3.2       # Great for conversation
ollama pull codellama      # Best for coding tasks
ollama pull deepseek-r1    # Reasoning tasks
```
