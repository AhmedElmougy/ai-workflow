#!/usr/bin/env python3
"""Flag comment lines introduced by an Edit/Write call, so the PostToolUse hook
can ask whether each explains WHY (keep) or just WHAT/this-task-context (remove).
Heuristic, Python-only (`#`), not a parser — false positives/negatives are fine,
this is a nudge, not a gate. Prints each flagged line, one per output line.
"""
# ruff: noqa: T201, BLE001, S110 — print is the output mechanism; the broad except
# is deliberate best-effort (malformed input should degrade to "nothing flagged", not crash).

import json
import sys


def comment_lines(text: str) -> set[str]:
    out = set()
    for block in comment_blocks(text):
        out.update(block)
    return out


def comment_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("#!"):
            current.append(stripped)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def flag(text: str, old_comments: set[str]) -> None:
    for block in comment_blocks(text):
        new_lines = [line for line in block if line not in old_comments]
        if not new_lines:
            continue
        # A contiguous run of 2+ brand-new lines is a verbosity problem on its own,
        # regardless of whether each individual line passes the WHY-vs-WHAT bar —
        # flag it as one block so the nudge can ask for condensing, not per-line WHY review.
        if len(new_lines) > 1:
            print("VERBOSE:" + " / ".join(new_lines))
        else:
            print(new_lines[0])


try:
    data = json.load(sys.stdin)
    inp = data.get("tool_input", {})
    file_path = inp.get("file_path") or inp.get("path") or ""
    if file_path.endswith(".py"):
        old_string = inp.get("old_string")
        new_string = inp.get("new_string")
        if new_string is not None:
            flag(new_string, comment_lines(old_string) if old_string is not None else set())
        else:
            content = inp.get("content")
            if content is not None:
                flag(content, set())
except Exception:
    pass
