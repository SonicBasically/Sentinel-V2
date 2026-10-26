# Workspace Rules & Persistent Memory

## 1. Clarification & Question Answering
- **Ask questions rather than guessing**: When requirements, design intent, or implementations are ambiguous, ask Thomas clarifying questions upfront to reduce trial and error.
- **Do not over-ask**: Only ask when clarification is genuinely needed; do not interrupt routine or straightforward tasks.

## 2. Multi-AI Handover & Notes (`comms/`)
- **Directory**: `/home/thomasgomez/Desktop/OG_Drive/GitHub/Sentinel-V2/comms`
- **When to create a comms note**:
  - ONLY when explicitly instructed by Thomas, OR
  - When there is a bug or problem that ChatGPT (or Claude) needs to fix or investigate.
  - Do NOT create notes for routine changes unless instructed, to avoid wasting tokens unnecessarily.
- **Protocol**:
  - File name: `NNN-gemini.md` (check the highest number currently in `comms/` and increment by 1, e.g., `056-gemini.md`).
  - Follow the structure defined in `comms/README.md`:
    - `From: Gemini`
    - `To: ChatGPT | Claude | Thomas`
    - `Re: (summary topic)`
    - `Did / changed:` (exact files and changes)
    - `Backup:` (path in `backups/` if live files like `server.py`, `sentinel_v2.html`, `games.py`, `media.py`, `launch.sh` were edited)
    - `Checked:` (results of `bash tools/selfcheck.sh` or testing)
    - `Need from you:` (specific questions, tasks, or bugs for ChatGPT/Claude)
  - Always respect existing ground rules in `comms/README.md` (never write secrets/API keys, back up live files before changes, run selfcheck).

## 3. Second Brain / Personal Knowledge Vault
- **Path**: `/home/thomasgomez/Desktop/Media_Drive/Personal/Documents/Vaults/Second Brain`
- **Usage**: Access this vault whenever you need to look up personal notes, past context, documentation, or remember user preferences and knowledge.
- **Access Note**: This directory is located outside the project workspace. If running within a restricted sandbox, file reads or command execution for this path may require elevated access / bypassing the sandbox.
