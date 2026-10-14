#!/usr/bin/env bash
# Stop hook: lints changed Python files once; blocks on failure but never twice in a row
# (`stop_hook_active` guards against looping). Also emits a non-blocking nudge (diff-review
# skill reminder + response-format check) once lint either passed or didn't apply.

set -uo pipefail  # no -e: a failing lint command must not abort the hook itself

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RAW_INPUT=$(cat)

STOP_ACTIVE=$(printf '%s' "$RAW_INPUT" | python3 -c "
import json, sys
try:
    print(bool(json.load(sys.stdin).get('stop_hook_active', False)))
except Exception:
    print(False)
" 2>/dev/null)
[ "$STOP_ACTIVE" = "True" ] && exit 0

cd "$REPO_ROOT" || exit 0
command -v git >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# git status --porcelain works whether or not HEAD exists yet (this repo has
# zero commits as of this writing) — unlike `git diff HEAD`, which would fail.
mapfile -t CHANGED_ALL < <(git status --porcelain 2>/dev/null | awk '{print $NF}' | sort -u)
[ "${#CHANGED_ALL[@]}" -gt 0 ] || exit 0

mapfile -t CHANGED < <(printf '%s\n' "${CHANGED_ALL[@]}" | grep '\.py$')

emit_nudge() {
  printf '%s' "$RAW_INPUT" | CHANGED_COUNT="${#CHANGED_ALL[@]}" python3 "$SCRIPT_DIR/_build_stop_nudge.py"
}

if [ "${#CHANGED[@]}" -eq 0 ]; then
  emit_nudge
  exit 0
fi

RUFF_BIN="$REPO_ROOT/venv/bin/ruff"
if [ ! -x "$RUFF_BIN" ]; then
  if command -v ruff >/dev/null 2>&1; then
    RUFF_BIN="ruff"
  else
    emit_nudge  # no known lint tool available — don't block on what we can't run
    exit 0
  fi
fi

"$RUFF_BIN" check --force-exclude --fix "${CHANGED[@]}" >/dev/null 2>&1
"$RUFF_BIN" format --force-exclude "${CHANGED[@]}" >/dev/null 2>&1
RECHECK=$("$RUFF_BIN" check --force-exclude "${CHANGED[@]}" 2>&1)
RECHECK_STATUS=$?

if [ "$RECHECK_STATUS" -ne 0 ]; then
  printf '%s' "$RECHECK" | python3 -c "
import json, sys
output = sys.stdin.read()[:2000]
reason = ('ruff check is still failing on changed files after one auto-fix attempt:\n' + output +
          '\nFix this before finishing, or explicitly report it as a known-failing check if you '
          'genuinely cannot resolve it — do not keep retrying blindly.')
print(json.dumps({'decision': 'block', 'reason': reason}))
"
  exit 0
fi

emit_nudge
exit 0
