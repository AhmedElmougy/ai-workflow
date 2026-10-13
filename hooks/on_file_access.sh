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
