#!/usr/bin/env python3
"""PostToolUse hook for Bash: once `repo_lookup.py` or `build_repo_map.py` is actually
invoked this session, touch a session-scoped marker file. `on_file_access.sh`'s PreToolUse
gate checks for this marker before allowing the first real-source Edit/Write — this is
the thing that *writes* what that gate reads.
"""
# ruff: noqa: BLE001, S108, S110 — malformed hook input should degrade to a no-op, not
# crash; the /tmp dedup path is an established pattern shared with on_file_access.sh.

import json
import sys
from pathlib import Path

EXPLORE_MARKERS = ("repo_lookup.py", "build_repo_map.py")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    session_id = data.get("session_id") or ""
    if not session_id or not any(marker in command for marker in EXPLORE_MARKERS):
        return

    dedup_dir = Path(f"/tmp/ai-hook-rules-emitted-{session_id}")
    try:
        dedup_dir.mkdir(parents=True, exist_ok=True)
        (dedup_dir / "explored").touch()
    except Exception:
        pass


if __name__ == "__main__":
    main()
