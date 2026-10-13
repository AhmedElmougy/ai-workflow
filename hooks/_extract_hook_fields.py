#!/usr/bin/env python3
"""Read a Claude Code hook's JSON payload from stdin and print three lines:
file_path (or path), session_id, tool_name. Shared by on_file_access.sh / on_file_edit.sh.

Must be invoked as a separate process (not `python3 - <<HEREDOC`), so that
sys.stdin still carries the hook's actual JSON payload rather than being
consumed by the heredoc as the program source itself.
"""
# ruff: noqa: T201, BLE001 — print is the output mechanism; the broad except is
# deliberate (malformed hook input should degrade to empty fields, not crash the hook).

import json
import sys

try:
    data = json.load(sys.stdin)
    inp = data.get("tool_input", data)
    print(inp.get("file_path") or inp.get("path") or "")
    print(data.get("session_id") or "")
    print(data.get("tool_name") or "")
except Exception:
    print("")
    print("")
    print("")
