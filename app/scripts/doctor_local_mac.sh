#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
VENV_DIR="$WORKSPACE_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$WORKSPACE_DIR/.env"
GIGASTT_BIN="$WORKSPACE_DIR/tools/bin/gigastt"
GIGASTT_MODEL_DIR="$WORKSPACE_DIR/.models/gigastt"
INBOX_NAME="${VOICE_RECOGNIZER_INBOX:-Inbox}"
OUTPUTS_DIR="$WORKSPACE_DIR/outputs"
LOG_DIR="$WORKSPACE_DIR/logs"
LOG_FILE=""
PORTS_TEXT="${VOICE_RECOGNIZER_PORTS:-8765 8766}"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"

cd "$WORKSPACE_DIR" || exit 1

ok_count=0
warn_count=0
fail_count=0

init_logging() {
  local stamp
  mkdir -p "$LOG_DIR"
  stamp="$(date +%Y%m%d-%H%M%S)"
  LOG_FILE="$LOG_DIR/doctor-$stamp.log"
  ln -sf "$(basename "$LOG_FILE")" "$LOG_DIR/doctor-latest.log"
  exec > >(tee -a "$LOG_FILE") 2>&1
  echo "Doctor log: $LOG_FILE"
  echo "Latest doctor log: $LOG_DIR/doctor-latest.log"
  echo "Лог не печатает HF token. Не пересылайте .env, аудио или outputs."
  echo
}

pause_before_close() {
  if [[ "$PAUSE_ON_EXIT" == "0" ]]; then
    return
  fi
  echo
  read -r "reply?Нажмите Enter, чтобы закрыть это окно..."
}

ok() {
  ok_count=$((ok_count + 1))
  echo "[OK] $1"
}

warn() {
  warn_count=$((warn_count + 1))
  echo "[WARN] $1"
}

fail() {
  fail_count=$((fail_count + 1))
  echo "[FAIL] $1"
}

next_step() {
  echo "      -> $1"
}

find_brew() {
  if command -v brew >/dev/null 2>&1; then
    command -v brew
    return 0
  fi
  if [[ -x "/opt/homebrew/bin/brew" ]]; then
    echo "/opt/homebrew/bin/brew"
    return 0
  fi
  if [[ -x "/usr/local/bin/brew" ]]; then
    echo "/usr/local/bin/brew"
    return 0
  fi
  return 1
}

activate_brew_path() {
  local brew_bin
  brew_bin="$(find_brew 2>/dev/null || true)"
  if [[ -n "$brew_bin" ]]; then
    eval "$("$brew_bin" shellenv)"
  fi
}

read_env_value() {
  local key="$1"
  local line
  if [[ ! -f "$ENV_FILE" ]]; then
    return 1
  fi
  while IFS= read -r line; do
    if [[ "$line" == "$key="* ]]; then
      line="${line#*=}"
      line="${line%\"}"
      line="${line#\"}"
      line="${line%\'}"
      line="${line#\'}"
      echo "$line"
      return 0
    fi
  done < "$ENV_FILE"
  return 1
}

python_is_compatible() {
  local python_bin="$1"
  "$python_bin" - <<'PY'
import sys
version = sys.version_info[:2]
raise SystemExit(0 if (3, 10) <= version < (3, 13) else 1)
PY
}

check_machine() {
  local arch
  arch="$(uname -m)"
  echo "Machine"
  echo "-------"
  echo "macOS: $(sw_vers -productVersion 2>/dev/null || echo unknown)"
  echo "arch:  $arch"
  if [[ "$arch" == "arm64" ]]; then
    ok "Apple Silicon detected."
  else
    warn "This is not Apple Silicon. The current happy path targets Apple Silicon Macs."
  fi
  echo
}

check_homebrew() {
  echo "Homebrew"
  echo "--------"
  activate_brew_path
  local brew_bin
  brew_bin="$(find_brew 2>/dev/null || true)"
  if [[ -n "$brew_bin" ]]; then
    ok "Homebrew found: $brew_bin"
  else
    warn "Homebrew is not installed or not in PATH."
    next_step "Run Настроить Диктум.command and allow Homebrew installation when asked."
  fi
  echo
}

check_ffmpeg() {
  echo "Audio Tools"
  echo "-----------"
  if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg found: $(command -v ffmpeg)"
  else
    fail "ffmpeg not found."
    next_step "Run Настроить Диктум.command and allow ffmpeg installation."
  fi
  if command -v ffprobe >/dev/null 2>&1; then
    ok "ffprobe found: $(command -v ffprobe)"
  else
    fail "ffprobe not found."
    next_step "Run Настроить Диктум.command and allow ffmpeg installation."
  fi
  echo
}

check_python() {
  echo "Python"
  echo "------"
  local python_bin=""
  if [[ -x "$VENV_PYTHON" ]]; then
    python_bin="$VENV_PYTHON"
    ok ".venv Python found: $VENV_PYTHON"
  else
    fail ".venv Python not found."
    next_step "Run Настроить Диктум.command to create .venv."
  fi

  if [[ -n "$python_bin" ]]; then
    local version
    version="$("$python_bin" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo unknown)"
    if python_is_compatible "$python_bin"; then
      ok "Python version is compatible: $version"
    else
      fail "Python version is not compatible: $version"
      next_step "Use Python 3.10-3.12. The setup can install Python 3.12 via Homebrew."
    fi
  fi

  if PYTHONPATH="$APP_DIR/src" "$VENV_PYTHON" -m voice_recognizer.cli --help >/dev/null 2>&1; then
    ok "Диктум CLI imports from app/src."
  else
    fail "Диктум CLI cannot be imported."
    next_step "Run Настроить Диктум.command to install Python dependencies."
  fi
  echo
}

check_python_packages() {
  echo "Python Packages"
  echo "---------------"
  if [[ ! -x "$VENV_PYTHON" ]]; then
    warn "Package checks skipped because .venv is missing."
    echo
    return
  fi

  local packages=(typer rich numpy pyannote.audio)
  local report_file="$LOG_DIR/python-packages.$$"
  rm -f "$report_file"
  if ! "$VENV_PYTHON" - "${packages[@]}" > "$report_file" 2>/dev/null <<'PY'
import importlib.metadata
import sys
for name in sys.argv[1:]:
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        print(f"{name}\tmissing\t")
    else:
        print(f"{name}\tok\t{version}")
PY
  then
    fail "Could not inspect Python package metadata."
    next_step "Run Настроить Диктум.command and allow Python dependency installation."
    rm -f "$report_file"
    echo
    return
  fi

  local package
  local package_state
  local version
  while IFS=$'\t' read -r package package_state version; do
    if [[ "$package_state" == "ok" && -n "$version" ]]; then
      ok "Python package installed: $package ${version}"
    else
      if [[ "$package" == "pyannote.audio" ]]; then
        fail "Python package missing or broken: $package"
        next_step "Run Настроить Диктум.command and allow Python dependency installation."
      else
        fail "Python package missing or broken: $package"
        next_step "Run Настроить Диктум.command and allow Python dependency installation."
      fi
    fi
  done < "$report_file"
  rm -f "$report_file"
  echo
}

check_env() {
  echo "Secrets"
  echo "-------"
  if [[ -f "$ENV_FILE" ]]; then
    ok ".env exists."
  else
    fail ".env is missing."
    next_step "Run Настроить Диктум.command to create .env and add HF_TOKEN."
    echo
    return
  fi

  local hf_token
  hf_token="$(read_env_value HF_TOKEN 2>/dev/null || true)"
  if [[ -n "$hf_token" && "$hf_token" != "hf_your_token_here" ]]; then
    ok "HF_TOKEN is configured. Value is hidden."
  else
    fail "HF_TOKEN is missing or still a placeholder."
    next_step "Run Настроить Диктум.command and paste the read-only Hugging Face token."
  fi
  echo
}

check_models() {
  echo "ASR Models"
  echo "----------"
  echo "GigaSTT / GigaAM v3 is the local Russian ASR engine. It turns audio into text."
  echo "Files are created locally by setup: tools/bin/gigastt and .models/gigastt/."
  echo "Model inventory:"
  if find "$GIGASTT_MODEL_DIR" -maxdepth 3 \( -type f -o -type l \) -print -quit 2>/dev/null | grep -q .; then
    find "$GIGASTT_MODEL_DIR" -maxdepth 3 \( -type f -o -type l \) -print 2>/dev/null | sort | while IFS= read -r path; do
      echo " - ${path#$WORKSPACE_DIR/}"
    done
  else
    echo " - .models/gigastt/ is empty or missing"
  fi
  if [[ -x "$GIGASTT_BIN" ]]; then
    ok "GigaSTT binary found: tools/bin/gigastt"
  else
    fail "GigaSTT binary is missing."
    next_step "Run Настроить Диктум.command again and allow stage 4/5: GigaSTT/GigaAM v3."
    next_step "This downloads the local ASR binary from GitHub into tools/bin/."
  fi

  local required_models=(
    "v3_rnnt_decoder.onnx"
    "v3_rnnt_joint.onnx"
    "v3_vocab.txt"
    "punct/rupunct_small_int8.onnx"
    "punct/config.json"
    "punct/tokenizer.json"
  )
  local missing=0
  local model
  if [[ -f "$GIGASTT_MODEL_DIR/v3_rnnt_encoder.onnx" || -f "$GIGASTT_MODEL_DIR/v3_rnnt_encoder_int8.onnx" ]]; then
    ok "GigaSTT encoder model found: v3_rnnt_encoder.onnx or v3_rnnt_encoder_int8.onnx"
  else
    missing=$((missing + 1))
    fail "GigaSTT encoder model missing: v3_rnnt_encoder.onnx or v3_rnnt_encoder_int8.onnx"
  fi
  for model in "${required_models[@]}"; do
    if [[ -f "$GIGASTT_MODEL_DIR/$model" ]]; then
      ok "GigaSTT model file found: $model"
    else
      missing=$((missing + 1))
      fail "GigaSTT model file missing: $model"
    fi
  done
  if (( missing > 0 )); then
    next_step "Run Настроить Диктум.command again and allow GigaSTT/GigaAM model download."
    next_step "Models are stored locally in .models/gigastt/ and are reused on the next run."
  fi
  echo
}

check_workspace_dirs() {
  echo "Local Data Folders"
  echo "------------------"
  local inbox_dir
  inbox_dir="$WORKSPACE_DIR/$INBOX_NAME"
  if [[ "$INBOX_NAME" == /* ]]; then
    inbox_dir="$INBOX_NAME"
  fi

  if [[ -d "$inbox_dir" ]]; then
    ok "Inbox folder exists: $INBOX_NAME"
  elif [[ -z "${VOICE_RECOGNIZER_INBOX:-}" && -d "$WORKSPACE_DIR/inbox" ]]; then
    warn "Default Inbox folder is missing, but legacy inbox/ exists."
    next_step "Run setup to create Inbox/ or start with VOICE_RECOGNIZER_INBOX=inbox."
  else
    warn "Inbox folder does not exist yet."
    next_step "Run setup or create $INBOX_NAME before adding audio files."
  fi
  if [[ -d "$OUTPUTS_DIR" ]]; then
    ok "Outputs folder exists: outputs/"
  else
    warn "Outputs folder does not exist yet."
    next_step "It will be created by setup or the first transcription run."
  fi
  echo
}

check_ports() {
  echo "Server Ports"
  echo "------------"
  local ports=("${(@s: :)PORTS_TEXT}")
  local port
  for port in "${ports[@]}"; do
    if [[ -z "$port" ]]; then
      continue
    fi
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "Port $port is already in use."
      lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
      next_step "Use Остановить Диктум.command if this is an old Диктум server."
    else
      ok "Port $port is free."
    fi
  done
  echo
}

print_summary() {
  echo "Summary"
  echo "-------"
  echo "ok=$ok_count warnings=$warn_count failures=$fail_count"
  if [[ -n "$LOG_FILE" ]]; then
    echo "Doctor log: $LOG_FILE"
    echo "Latest doctor log: $LOG_DIR/doctor-latest.log"
  fi
  if (( fail_count == 0 )); then
    echo "Doctor did not find blocking problems."
  else
    echo "Doctor found blocking problems. Follow the next steps above, then run this check again."
  fi
  pause_before_close
  if (( fail_count == 0 )); then
    exit 0
  fi
  exit 1
}

init_logging
echo "Диктум doctor"
echo "Рабочая папка: $WORKSPACE_DIR"
echo "Приложение:    $APP_DIR"
echo

check_machine
check_homebrew
check_ffmpeg
check_python
check_python_packages
check_env
check_models
check_workspace_dirs
check_ports
print_summary
