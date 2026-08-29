#!/usr/bin/env bash
# PostToolUse(Edit|Write): re-run the import-boundary test when a pure domain
# package is touched. core/, data/ and calculation/ must never import PyQt6 or
# crane_statics.qml_app -- see tests/test_architecture.py. Reaching for QObject
# inside calculation/ is a natural mistake, so catch it at edit time rather than
# in pre-commit.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null)" || exit 0
[ -n "$PY" ] || exit 0

file="$("$PY" -c 'import json,sys;p=json.load(sys.stdin).get("tool_input",{}).get("file_path","");print(p.replace("\\","/"))' 2>/dev/null)" || exit 0

case "$file" in
  */crane_statics/core/*.py|*/crane_statics/data/*.py|*/crane_statics/calculation/*.py) ;;
  *) exit 0 ;;
esac

# --no-cov: pytest addopts enables coverage, which is far too slow for a hook.
# Use rtk pytest for compact output (91% compression via RTK).
if ! out="$(rtk pytest "$ROOT/tests/test_architecture.py" -q --no-cov -p no:cacheprovider 2>&1)"; then
  printf 'Architecture boundary test failed:\n%s\n' "$out" >&2
  exit 2
fi
exit 0
