#!/usr/bin/env bash
# PostToolUse hook for Bash: see _mark_explored.py for the actual logic.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/_mark_explored.py"
exit 0
