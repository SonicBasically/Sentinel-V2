#!/usr/bin/env python3
"""patch_once.py FILE OLD_TXT NEW_TXT

Safe single-spot edit for Sentinel's own source files.

  FILE     file to edit (must be inside the Sentinel repo)
  OLD_TXT  path to a text file holding the exact text to replace
  NEW_TXT  path to a text file holding the replacement

Rules enforced:
  * OLD text must match EXACTLY ONE place in FILE, otherwise nothing changes.
  * A backup FILE.bak-<timestamp> is written before any change.
  * Refuses to touch modes/, tools/, .env files or anything outside the repo.
"""
import sys, shutil, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def fail(msg):
    print("PATCH FAILED: " + msg)
    sys.exit(1)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    target = Path(sys.argv[1]).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()
    old_p = Path(sys.argv[2]).expanduser()
    new_p = Path(sys.argv[3]).expanduser()

    try:
        rel = target.relative_to(REPO)
    except ValueError:
        fail(f"{target} is outside the Sentinel repo ({REPO})")
    if rel.parts[0] in ("modes", "tools", ".git", ".venv") or target.name.startswith(".env"):
        fail(f"{rel} is protected and cannot be edited with this tool")
    if not target.is_file():
        fail(f"{target} does not exist")
    for p in (old_p, new_p):
        if not p.is_file():
            fail(f"{p} does not exist (write it first)")

    src = target.read_text(encoding="utf-8")
    old = old_p.read_text(encoding="utf-8")
    new = new_p.read_text(encoding="utf-8")
    if not old.strip():
        fail("OLD text is empty")

    count = src.count(old)
    if count == 0 and old.endswith("\n"):
        # snippet files often gain a trailing newline the real file does not have
        old, new = old.rstrip("\n"), new.rstrip("\n")
        count = src.count(old)
    if count != 1:
        fail(f"OLD text matched {count} places (need exactly 1). Nothing was changed. "
             "Copy the text exactly from the file, including spaces, and include a line or two of surrounding context.")

    line = src[:src.index(old)].count("\n") + 1
    backup = target.with_name(f"{target.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(target, backup)
    target.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH OK: {rel} line {line}, {len(old)} -> {len(new)} chars")
    print(f"backup:   {backup.name}")
    print(f"undo:     cp '{backup}' '{target}'")


if __name__ == "__main__":
    main()
