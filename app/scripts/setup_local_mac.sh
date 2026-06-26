#!/bin/zsh

set -u

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
VENV_DIR="$WORKSPACE_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$WORKSPACE_DIR/.env"
EXAMPLE_ENV="$APP_DIR/.env.example"
INBOX_DIR="$WORKSPACE_DIR/Inbox"
OUTPUT_DIR="$WORKSPACE_DIR/outputs/pipeline"
ASSUME_YES="${VOICE_RECOGNIZER_ASSUME_YES:-0}"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"
PYTHON_BIN=""

cd "$WORKSPACE_DIR" || exit 1

ok_count=0
warn_count=0
fail_count=0

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

ask_yes_no() {
  local prompt="$1"
  local default="${2:-n}"
  local suffix="[y/N]"
  local reply=""

  if [[ "$default" == "y" ]]; then
    suffix="[Y/n]"
  fi
  if [[ "$ASSUME_YES" == "1" ]]; then
    echo "$prompt $suffix"
    echo "Ответ: да (VOICE_RECOGNIZER_ASSUME_YES=1)"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    echo "$prompt $suffix"
    echo "Ответ: нет (нет интерактивного ввода)"
    return 1
  fi

  if ! read -r "reply?$prompt $suffix "; then
    reply=""
  fi
  if [[ -z "$reply" ]]; then
    [[ "$default" == "y" ]]
    return
  fi
  case "$reply" in
    y|Y|yes|YES|д|Д|да|Да|ДА)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
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

write_env_value() {
  local key="$1"
  local value="$2"
  local tmp="$ENV_FILE.tmp.$$"
  local found=0
  local line

  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  while IFS= read -r line; do
    if [[ "$line" == "$key="* ]]; then
      print -r -- "$key=$value" >> "$tmp"
      found=1
    else
      print -r -- "$line" >> "$tmp"
    fi
  done < "$ENV_FILE"
  if [[ "$found" == "0" ]]; then
    print -r -- "$key=$value" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
}

python_is_compatible() {
  local python_bin="$1"
  "$python_bin" - <<'PY'
import sys
version = sys.version_info[:2]
raise SystemExit(0 if (3, 10) <= version < (3, 13) else 1)
PY
}

find_python() {
  local candidate
  for candidate in "$VENV_PYTHON" python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate="$(command -v "$candidate")"
      if python_is_compatible "$candidate"; then
        echo "$candidate"
        return 0
      fi
    elif [[ -x "$candidate" ]]; then
      if python_is_compatible "$candidate"; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

ensure_homebrew() {
  activate_brew_path
  if command -v brew >/dev/null 2>&1; then
    ok "Homebrew найден: $(command -v brew)"
    return 0
  fi

  warn "Homebrew не найден. Он нужен, чтобы автоматически поставить ffmpeg и при необходимости Python 3.12."
  if ask_yes_no "Установить Homebrew сейчас? Это официальный менеджер пакетов для macOS." "n"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    activate_brew_path
    if command -v brew >/dev/null 2>&1; then
      ok "Homebrew установлен."
      return 0
    fi
  fi

  warn "Homebrew не установлен. Автоматическая установка ffmpeg/Python будет недоступна."
  return 1
}

ensure_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    ok "ffmpeg и ffprobe найдены."
    return 0
  fi

  warn "ffmpeg/ffprobe не найдены. Они нужны для чтения .m4a/.mp3/.wav и подготовки аудио к моделям."
  if command -v brew >/dev/null 2>&1; then
    if ask_yes_no "Установить ffmpeg через Homebrew?" "y"; then
      brew install ffmpeg
      if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
        ok "ffmpeg установлен."
        return 0
      fi
    fi
  fi

  fail "ffmpeg не готов. Без него обработка аудиофайлов не заработает."
  return 1
}

ensure_python() {
  local python_bin
  python_bin="$(find_python 2>/dev/null || true)"
  if [[ -n "$python_bin" ]]; then
    ok "Совместимый Python найден: $("$python_bin" -c 'import sys; print(sys.version.split()[0])')"
    PYTHON_BIN="$python_bin"
    return 0
  fi

  warn "Нужен Python 3.10-3.12. Подходящий Python не найден."
  if command -v brew >/dev/null 2>&1; then
    if ask_yes_no "Установить Python 3.12 через Homebrew?" "y"; then
      brew install python@3.12
      activate_brew_path
      python_bin="$(find_python 2>/dev/null || true)"
      if [[ -n "$python_bin" ]]; then
        ok "Python установлен."
        PYTHON_BIN="$python_bin"
        return 0
      fi
    fi
  fi

  fail "Python не готов. Установите Python 3.12 и запустите setup снова."
  return 1
}

ensure_venv_and_dependencies() {
  local python_bin="$1"
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo
    echo "Будет создано локальное Python-окружение:"
    echo "$VENV_DIR"
    if ask_yes_no "Создать .venv сейчас?" "y"; then
      if "$python_bin" -m venv "$VENV_DIR"; then
        ok ".venv создан."
      else
        fail "Не удалось создать .venv."
        return 1
      fi
    else
      fail ".venv не создан."
      return 1
    fi
  else
    ok ".venv уже существует."
  fi

  echo
  echo "Зависимости Python устанавливаются локально в .venv."
  echo "Это включает pyannote.audio для разделения по спикерам."
  if ask_yes_no "Установить/обновить зависимости Python сейчас?" "y"; then
    if "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel \
      && (cd "$APP_DIR" && "$VENV_PYTHON" -m pip install -e '.[diarization]'); then
      ok "Python-зависимости готовы."
    else
      fail "Не удалось установить Python-зависимости."
      return 1
    fi
  else
    warn "Зависимости Python не обновлялись."
  fi
}

ensure_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$EXAMPLE_ENV" ]]; then
      cp "$EXAMPLE_ENV" "$ENV_FILE"
      chmod 600 "$ENV_FILE" 2>/dev/null || true
      ok "Создан локальный .env из app/.env.example."
    else
      touch "$ENV_FILE"
      chmod 600 "$ENV_FILE" 2>/dev/null || true
      warn "Создан пустой .env."
    fi
  else
    ok "Локальный .env найден."
  fi

  local token_value
  token_value="$(read_env_value HF_TOKEN 2>/dev/null || true)"
  if [[ -n "$token_value" && "$token_value" != "hf_your_token_here" ]]; then
    ok "HF_TOKEN найден в .env. Значение не выводится."
    return 0
  fi

  warn "HF_TOKEN не настроен. Он нужен pyannote для разделения по спикерам."
  if ask_yes_no "Вставить HF token сейчас? Ввод будет скрыт, токен сохранится только в локальный .env." "y"; then
    local hf_token=""
    read -rs "hf_token?HF token: "
    echo
    if [[ -n "$hf_token" ]]; then
      write_env_value "HF_TOKEN" "$hf_token"
      ok "HF_TOKEN сохранен в .env без вывода в лог."
    else
      warn "Пустой token не сохранен."
    fi
  fi
}

ensure_gigastt() {
  local bin="$WORKSPACE_DIR/tools/bin/gigastt"
  local model="$WORKSPACE_DIR/.models/gigastt/v3_rnnt_encoder.onnx"
  if [[ -x "$bin" && -f "$model" ]]; then
    ok "GigaSTT binary и GigaAM v3 модели найдены."
    return 0
  fi

  warn "GigaSTT/GigaAM v3 еще не готовы. Это основной ASR-движок для русского языка."
  echo "Модели будут храниться локально в .models/gigastt, binary - в tools/bin."
  if ask_yes_no "Скачать/подготовить GigaSTT и модели сейчас?" "y"; then
    "$APP_DIR/scripts/setup_gigastt.sh"
    if [[ -x "$bin" && -f "$model" ]]; then
      ok "GigaSTT/GigaAM v3 готовы."
      return 0
    fi
  fi

  warn "GigaSTT/GigaAM v3 не подготовлены. Распознавание не запустится до настройки моделей."
  return 1
}

check_pyannote_access() {
  local token_value
  token_value="$(read_env_value HF_TOKEN 2>/dev/null || true)"
  if [[ -z "$token_value" || "$token_value" == "hf_your_token_here" ]]; then
    warn "Проверка pyannote пропущена: HF_TOKEN не настроен."
    return 1
  fi

  if [[ ! -x "$VENV_PYTHON" ]]; then
    warn "Проверка pyannote пропущена: .venv не готов."
    return 1
  fi

  if ask_yes_no "Проверить доступ HF token к pyannote сейчас? Токен не будет напечатан." "y"; then
    if HF_TOKEN="$token_value" PYTHONPATH="$APP_DIR/src" "$VENV_PYTHON" -m voice_recognizer.cli check-pyannote-access; then
      ok "Доступ к pyannote проверен."
    else
      fail "Не удалось проверить доступ к pyannote."
      return 1
    fi
  else
    warn "Проверка pyannote пропущена."
  fi
}

smoke_test() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    fail "Smoke-test невозможен: .venv не найден."
    return 1
  fi
  if PYTHONPATH="$APP_DIR/src" "$VENV_PYTHON" -m voice_recognizer.cli --help >/dev/null; then
    ok "CLI импортируется из app/src."
  else
    fail "CLI не импортируется из app/src."
    return 1
  fi
}

print_header() {
  echo "Voice Recognizer setup"
  echo "Рабочая папка: $WORKSPACE_DIR"
  echo "Приложение:    $APP_DIR"
  echo
  echo "Цель: подготовить локальную приватную установку на Mac."
  echo "Все аудио, модели, токены и результаты остаются в этой папке."
  echo
}

print_machine_info() {
  local arch
  arch="$(uname -m)"
  echo "Mac architecture: $arch"
  if [[ "$arch" == "arm64" ]]; then
    ok "Apple Silicon обнаружен. Целевой MacBook M5/32GB подходит."
  else
    warn "Это не Apple Silicon. Проект может работать, но setup оптимизирован под arm64 Mac."
  fi
}

print_next_steps() {
  echo
  echo "Итог setup: ok=$ok_count, warnings=$warn_count, failures=$fail_count"
  echo
  if (( fail_count == 0 )); then
    echo "Базовая подготовка завершена."
    if ask_yes_no "Запустить Voice Recognizer сейчас?" "y"; then
      "$APP_DIR/scripts/start_server.sh"
      exit $?
    fi
  else
    echo "Есть проблемы, которые нужно исправить. После исправления запустите setup еще раз."
  fi
  pause_before_close
}

print_header
print_machine_info
ensure_homebrew || true
ensure_ffmpeg || true
ensure_python || true
if [[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]]; then
  ensure_venv_and_dependencies "$PYTHON_BIN" || true
fi
mkdir -p "$INBOX_DIR" "$OUTPUT_DIR"
ok "Папки Inbox и outputs подготовлены."
ensure_env_file || true
ensure_gigastt || true
check_pyannote_access || true
smoke_test || true
print_next_steps
