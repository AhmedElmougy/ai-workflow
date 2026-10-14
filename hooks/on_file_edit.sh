#!/usr/bin/env bash
# PostToolUse hook for Edit/Write: lightweight reminder + new-comment nudge.
# Durable memory/index maintenance is conditional, not mandatory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_INPUT=$(cat)

FIELDS=$(printf '%s' "$RAW_INPUT" | python3 "$SCRIPT_DIR/_extract_hook_fields.py")
FILE=$(printf '%s\n' "$FIELDS" | sed -n '1p')
SESSION_ID=$(printf '%s\n' "$FIELDS" | sed -n '2p')

case "$FILE" in
  ""|*/.ai/*) exit 0 ;;
esac

case "$FILE" in
  *.py)
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"Python file changed. Before final answer, run focused verification and inspect diff, then report the exact command verbatim so it can be re-run independently. Pressure-test any new literal threshold/count: derived from an observed run, or guessed? If this introduced a durable structural discovery outside timebox/interview mode, update .ai memory/index."}}'
    ;;
  *.js|*.ts|*.tsx|*.jsx|*.html|*.css|*.sh|*.yaml|*.yml|*.toml)
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"Source/config file changed. Before final answer, run focused verification and inspect diff. Memory update is conditional, not mandatory."}}'
    ;;
esac

NEW_COMMENTS=$(printf '%s' "$RAW_INPUT" | python3 "$SCRIPT_DIR/_detect_new_comments.py")
if [ -n "$NEW_COMMENTS" ]; then
  POLICY_SHOWN="0"
  if [ -n "$SESSION_ID" ]; then
    DEDUP_DIR="/tmp/ai-hook-rules-emitted-${SESSION_ID}"
    mkdir -p "$DEDUP_DIR" 2>/dev/null || DEDUP_DIR=""
    if [ -n "$DEDUP_DIR" ]; then
      [ -f "$DEDUP_DIR/comment-policy" ] && POLICY_SHOWN="1"
      touch "$DEDUP_DIR/comment-policy" 2>/dev/null || true
    fi
  fi
  printf '%s' "$NEW_COMMENTS" | POLICY_SHOWN="$POLICY_SHOWN" python3 -c "
import json, os, sys
lines = sys.stdin.read().rstrip(chr(10)).split(chr(10))
verbose = [l[len('VERBOSE:'):] for l in lines if l.startswith('VERBOSE:')]
plain = [l for l in lines if not l.startswith('VERBOSE:')]
if os.environ.get('POLICY_SHOWN') == '1':
    policy = 'comment policy already shown this session — see .ai/AGENTS.md § Comments (deletion test)'
    tail = ''
else:
    policy = ('apply the deletion test: if removing it loses no information the code does not '
              'already convey, delete it. Keep only a non-obvious WHY (constraint, invariant, '
              'workaround, caller precondition) scoped to this edit — never a restated WHAT, '
              'narrated intent, section banner, step label, edit marker, or a docstring that '
              'just echoes the signature')
    tail = ' If it survives, condense to one short line — do not pad with background or examples.'
parts = []
if plain:
    parts.append('New comment line(s): ' + ' | '.join(plain) + ' — ' + policy + '.')
if verbose:
    parts.append('New multi-line comment block(s): ' + ' || '.join(verbose) + ' — ' + policy + '.' + tail)
msg = ' '.join(parts)
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}}))
"
fi
