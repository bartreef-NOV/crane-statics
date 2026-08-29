#!/usr/bin/env bash
# PostToolUse(Edit|Write): black-format the edited Python file, then flake8 it.
# CI runs `black --check src tests` and `flake8 src tests`, so formatting drift
# is a build failure. Exit 2 hands flake8 findings back to Claude to fix in the
# same turn instead of surfacing them at commit time.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null)" || exit 0
[ -n "$PY" ] || exit 0

# Normalise the Windows backslashes so the case globs below match.
file="$("$PY" -c 'import json,sys;p=json.load(sys.stdin).get("tool_input",{}).get("file_path","");print(p.replace("\\","/"))' 2>/dev/null)" || exit 0

case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# A black failure means a syntax error; flake8 will report it more usefully.
"$PY" -m black -q "$file" >/dev/null 2>&1

# Use rtk format for compact linter output (91% compression via RTK)
if ! out="$(rtk format "$file" 2>&1)"; then
  printf 'flake8 findings in %s (fix these now):\n%s\n' "$file" "$out" >&2
  exit 2
fi
exit 0
