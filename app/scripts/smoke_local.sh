#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
PYTHON="${VOICE_RECOGNIZER_PYTHON:-$WORKSPACE_DIR/.venv/bin/python}"
SMOKE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/voice-recognizer-smoke.XXXXXX")"

cd "$WORKSPACE_DIR" || exit 1

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  echo "No Python found. Run setup first or set VOICE_RECOGNIZER_PYTHON."
  exit 1
fi

export PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPYCACHEPREFIX="$SMOKE_TMP/pycache"
export VOICE_RECOGNIZER_SMOKE_TMP="$SMOKE_TMP"

cleanup() {
  rm -rf "$SMOKE_TMP"
}
trap cleanup EXIT

section() {
  echo
  echo "== $1 =="
}

run() {
  echo "+ $*"
  "$@"
}

run_quiet() {
  echo "+ $*"
  "$@" >/dev/null
}

section "Environment"
echo "Workspace: $WORKSPACE_DIR"
echo "App:       $APP_DIR"
echo "Python:    $PYTHON"
if command -v node >/dev/null 2>&1; then
  echo "Node:      $(command -v node) ($(node --version))"
else
  echo "Node:      missing"
fi
echo "Temp:      $SMOKE_TMP"

section "Shell syntax"
shell_files=(app/scripts/*.sh *.command)
for file in "${shell_files[@]}"; do
  run zsh -n "$file"
done

section "Python compile"
run "$PYTHON" -m compileall -q app/src tests docs/asr-benchmark/score.py

section "CLI help"
run_quiet "$PYTHON" -m voice_recognizer.cli --help
run_quiet "$PYTHON" -m voice_recognizer.cli process --help
run_quiet "$PYTHON" -m voice_recognizer.cli batch-process --help
run_quiet "$PYTHON" -m voice_recognizer.cli refresh-quality --help
run_quiet "$PYTHON" -m voice_recognizer.cli web --help

section "Synthetic fixtures"
run "$PYTHON" tests/test_multipart.py
run "$PYTHON" tests/test_local_smoke.py

section "Done"
echo "Local smoke suite passed."
