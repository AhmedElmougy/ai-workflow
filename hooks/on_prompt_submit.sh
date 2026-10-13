#!/usr/bin/env bash
# UserPromptSubmit hook: workflow pointer every turn + once-per-session MEMORY.md index preload (area files stay on-demand).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_INDEX="$SCRIPT_DIR/../memory/MEMORY.md"

SESSION_ID=$(python3 "$SCRIPT_DIR/_extract_hook_fields.py" | sed -n '2p')

if [ -n "$SESSION_ID" ] && [ -f "$MEMORY_INDEX" ]; then
  DEDUP_DIR="/tmp/ai-hook-rules-emitted-${SESSION_ID}"
  mkdir -p "$DEDUP_DIR" 2>/dev/null || DEDUP_DIR=""
  MARKER="${DEDUP_DIR:+$DEDUP_DIR/session-memory-preload}"

  if [ -z "$MARKER" ] || [ ! -f "$MARKER" ]; then
    # Marker set before printing so an interrupted dump (e.g. SIGPIPE) still leaves consistent dedup state.
    [ -n "$MARKER" ] && touch "$MARKER" 2>/dev/null || true
    printf '%s\n' "=== MEMORY INDEX (.ai/memory/MEMORY.md, first 200 lines, loaded once this session) ==="
    head -n 200 "$MEMORY_INDEX"
    printf '%s\n' "=== END MEMORY INDEX — area files are on-demand only, read them when their \"when to read\" condition applies ==="
    printf '\n'
  fi
fi

printf '%s\n' "=== CODING COMPANION WORKFLOW ==="
printf '%s\n' "- Canonical instructions: .ai/AGENTS.md"
printf '%s\n' "- First retrieval call: repo_lookup tool, or fallback: python3 .ai/scripts/repo_lookup.py \"<task terms>\""
printf '%s\n' "- Generated map fallback: .ai/repo-map.md"
printf '%s\n' "- Loop: clarify → explore → plan → implement → verify → review → report."
printf '%s\n' "- Optional modifiers: timebox=<minutes>, context=interview|research|maintenance."
printf '%s\n' "- Do not load all memory/skills/rules by default."
printf '%s\n' "=== END WORKFLOW ==="
