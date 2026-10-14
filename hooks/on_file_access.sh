#!/usr/bin/env bash
# PreToolUse hook for Read/Edit/Write: inject relevant scoped rules, once per session.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_DIR="$SCRIPT_DIR/../rules"

INPUT=$(python3 "$SCRIPT_DIR/_extract_hook_fields.py")
FILE_PATH=$(printf '%s\n' "$INPUT" | sed -n '1p')
SESSION_ID=$(printf '%s\n' "$INPUT" | sed -n '2p')
TOOL_NAME=$(printf '%s\n' "$INPUT" | sed -n '3p')

[ -n "$FILE_PATH" ] || exit 0

DEDUP_DIR=""
if [ -n "$SESSION_ID" ]; then
  DEDUP_DIR="/tmp/ai-hook-rules-emitted-${SESSION_ID}"
  mkdir -p "$DEDUP_DIR" 2>/dev/null || DEDUP_DIR=""
fi

# Exploration gate: block the first real-source Edit/Write until repo_lookup.py has run
# this session, or at least MIN_READS_FALLBACK real-source files were Read first (the
# manual fallback AGENTS.md step 3/4 documents when the tool itself is unavailable).
# Deterministic, once-per-session — on_mark_explored.sh (PostToolUse on Bash) is what
# sets the "explored" marker this checks for.
MIN_READS_FALLBACK=2

is_exempt_path() {
  case "$1" in
    .ai/*|*/.ai/*|.claude/*|*/.claude/*|/tmp/*|*/scratchpad/*|"") return 0 ;;
    *) return 1 ;;
  esac
}

# Repo-init gate: step 2 before step 3. Blocks Read *and* Edit/Write of real source (the
# exploration gate below only covers Edit/Write, so a read-only session would otherwise
# never be forced through this step) until .ai/repo-map.md exists with real content. No
# session marker needed — the file's own existence is the signal, so it unblocks the
# moment the agent complies, mid-session. is_exempt_path already covers .ai/repo-map.md
# itself via its `.ai/*` pattern.
BUILD_MAP_SCRIPT="$SCRIPT_DIR/../scripts/build_repo_map.py"
REPO_MAP_FILE="$SCRIPT_DIR/../repo-map.md"
if [ -f "$BUILD_MAP_SCRIPT" ] \
  && { [ "$TOOL_NAME" = "Read" ] || [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; } \
  && ! is_exempt_path "$FILE_PATH" \
  && { [ ! -f "$REPO_MAP_FILE" ] || ! grep -q "AI-REPO-MAP:TOOLING START" "$REPO_MAP_FILE" 2>/dev/null; }; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Per AGENTS.md step 2, .ai/repo-map.md does not exist yet (or is empty) in this project — run `python3 .ai/scripts/build_repo_map.py` first (this is what /repo-init does). No session marker here: this unblocks the moment the file exists with real content."}}\n'
  exit 0
fi

if [ "$TOOL_NAME" = "Read" ] && [ -n "$DEDUP_DIR" ] && ! is_exempt_path "$FILE_PATH"; then
  READ_COUNT_FILE="$DEDUP_DIR/read_count"
  COUNT=$(( $(cat "$READ_COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
  echo "$COUNT" > "$READ_COUNT_FILE" 2>/dev/null || true
fi

if { [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; } && [ -n "$DEDUP_DIR" ] && ! is_exempt_path "$FILE_PATH"; then
  REPO_LOOKUP_SCRIPT="$SCRIPT_DIR/../scripts/repo_lookup.py"
  if [ -f "$REPO_LOOKUP_SCRIPT" ] && [ ! -f "$DEDUP_DIR/explored" ]; then
    READ_COUNT=$(cat "$DEDUP_DIR/read_count" 2>/dev/null || echo 0)
    if [ "$READ_COUNT" -lt "$MIN_READS_FALLBACK" ]; then
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Per AGENTS.md step 3, explore before editing real source: run `python3 .ai/scripts/repo_lookup.py \\"<task terms>\\"` first, or read at least %s real-source files as a manual fallback (you have read %s so far this session). This is a once-per-session gate — it will not block again after either condition is met."}}\n' "$MIN_READS_FALLBACK" "$READ_COUNT"
      exit 0
    fi
  fi
fi

# Hard-block repeat Reads of memory files — they have no other interception point, unlike rules which just re-emit as a reminder.
if [ "$TOOL_NAME" = "Read" ] && [ -n "$DEDUP_DIR" ]; then
  case "$FILE_PATH" in
    */.ai/memory/*.md|.ai/memory/*.md)
      MEMORY_MARKER="$DEDUP_DIR/memory-$(basename "$FILE_PATH")"
      # Only block if unchanged since last read (file mtime <= marker); a newer edit means stale cache, so allow the reread.
      if [ -f "$MEMORY_MARKER" ] && [ -f "$FILE_PATH" ] && [ ! "$FILE_PATH" -nt "$MEMORY_MARKER" ]; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s was already read this session and has not changed since (see earlier tool_result). Re-reading an unchanged memory file wastes context; use what you already have."}}\n' "$FILE_PATH"
        exit 0
      fi
      touch "$MEMORY_MARKER" 2>/dev/null || true
      ;;
  esac
fi

emit_rule() {
  local name="$1"
  local file="$2"
  [ -f "$file" ] || return 0

  if [ -n "$DEDUP_DIR" ] && [ -f "$DEDUP_DIR/$name" ]; then
    printf '\n(RULE: %s already shown this session — see %s)\n' "$name" "$file"
    return 0
  fi

  [ -n "$DEDUP_DIR" ] && touch "$DEDUP_DIR/$name" 2>/dev/null || true

  printf '\n=== RULE: %s (%s) ===\n' "$name" "$FILE_PATH"
  cat "$file"
  printf '\n'
}

case "$FILE_PATH" in
  *.py) emit_rule "imports" "$RULES_DIR/imports.md" ;;
esac

case "$FILE_PATH" in
  */models.py) emit_rule "models" "$RULES_DIR/models.md" ;;
esac

case "$FILE_PATH" in
  */services.py) emit_rule "services" "$RULES_DIR/services.md" ;;
esac

case "$FILE_PATH" in
  */views.py|*/serializers.py|*/selectors.py|*/validators.py|*/urls.py)
    emit_rule "api" "$RULES_DIR/api.md"
    ;;
esac

case "$FILE_PATH" in
  *test*.py|*/tests/*)
    emit_rule "testing" "$RULES_DIR/testing.md"
    ;;
esac

exit 0
