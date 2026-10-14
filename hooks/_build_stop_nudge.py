#!/usr/bin/env python3
"""Non-blocking Stop-hook nudge: reads the Stop hook's JSON (stdin) and CHANGED_COUNT
(env var, set by on_stop.sh from `git status --porcelain`), and prints either nothing or
a complete `{"hookSpecificOutput": ...}` JSON object for on_stop.sh to pass through
verbatim. Never blocks — this only ever adds additionalContext, it has no `decision` key.

Two checks, both best-effort heuristics over the transcript's last consecutive run of
assistant text, not correctness gates:
1. Diff-review reminder — fires whenever something changed this turn.
2. Response-format check — per AGENTS.md's Final response conventions, flags a file path
   shown as a plain code span instead of a markdown link, or a command-looking line not
   in a code span/fence. False positives/negatives are expected and tolerated.
"""
# ruff: noqa: T201, BLE001, S112 — print is this script's output channel; broad excepts
# (including try/except/continue over transcript lines) degrade a malformed
# transcript/line to "no findings" instead of crashing the Stop hook.

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKTICK_SPAN = re.compile(r"`([^`\n]+)`")
PATH_LIKE = re.compile(r"^[\w./-]+/[\w./-]+\.\w+$")
COMMAND_VERBS = ("make", "npm", "npx", "pytest", "python", "python3", "docker", "git", "rg")
MAX_EXAMPLES = 2


def last_assistant_text(transcript_path: str) -> str:
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    texts: list[str] = []
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "assistant":
            break
        content = obj.get("message", {}).get("content", [])
        texts.extend(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return "\n".join(reversed(texts))


def unlinked_real_paths(text: str) -> list[str]:
    found = []
    for match in BACKTICK_SPAN.finditer(text):
        candidate = match.group(1)
        if not PATH_LIKE.match(candidate):
            continue
        if (REPO_ROOT / candidate).is_file() and candidate not in found:
            found.append(candidate)
        if len(found) >= MAX_EXAMPLES:
            break
    return found


def bare_commands(text: str) -> list[str]:
    found: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or "`" in line or line.endswith((".", "!", "?")):
            continue  # real commands don't end in sentence punctuation; prose does
        first_word = line.split(" ", 1)[0] if line else ""
        if first_word in COMMAND_VERBS and len(line) > len(first_word):
            found.append(line[:100])
            if len(found) >= MAX_EXAMPLES:
                break
    return found


def format_findings(transcript_path: str) -> list[str]:
    if not transcript_path:
        return []
    text = last_assistant_text(transcript_path)
    if not text:
        return []
    notes = []
    paths = unlinked_real_paths(text)
    if paths:
        notes.append(
            "file path(s) shown as plain code spans instead of markdown links "
            f"(e.g. `{paths[0]}`) — use [path](path) per AGENTS.md's Final response conventions",
        )
    commands = bare_commands(text)
    if commands:
        notes.append(
            f"command-looking line not in a code span/fence (e.g. `{commands[0]}`) — wrap it so it's copy-pasteable",
        )
    return notes


def main() -> None:
    raw_input = sys.stdin.read()
    try:
        transcript_path = json.loads(raw_input).get("transcript_path", "")
    except Exception:
        transcript_path = ""

    changed_count = os.environ.get("CHANGED_COUNT", "0")

    # changed_count is the whole uncommitted working tree (git status --porcelain), not a
    # per-turn delta — there's no commit history here to diff against. Worded accordingly:
    # a presence check ("is there a diff at all"), not a claimed count of this turn's edits.
    notes: list[str] = []
    if changed_count != "0":
        notes.append(
            "there are uncommitted changes in the working tree — consider the diff-review skill "
            "(.ai/skills/diff-review/SKILL.md) before calling this done, if you haven't already",
        )
    notes.extend(format_findings(transcript_path))

    if notes:
        context = "Reminder: " + "; ".join(notes) + "."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": context}}))


if __name__ == "__main__":
    main()
