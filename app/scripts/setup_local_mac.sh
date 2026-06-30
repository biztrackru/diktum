#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
VENV_DIR="$WORKSPACE_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$WORKSPACE_DIR/.env"
EXAMPLE_ENV="$APP_DIR/.env.example"
INBOX_DIR="$WORKSPACE_DIR/Inbox"
OUTPUT_DIR="$WORKSPACE_DIR/outputs/pipeline"
LOG_DIR="$WORKSPACE_DIR/logs"
LOG_FILE=""
MPLCONFIG_DIR="$WORKSPACE_DIR/.cache/matplotlib"
ASSUME_YES="${VOICE_RECOGNIZER_ASSUME_YES:-0}"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"
PYTHON_BIN=""

cd "$WORKSPACE_DIR" || exit 1

ok_count=0
warn_count=0
fail_count=0

init_logging() {
  local stamp
  mkdir -p "$LOG_DIR"
  stamp="$(date +%Y%m%d-%H%M%S)"
  LOG_FILE="$LOG_DIR/setup-$stamp.log"
  ln -sf "$(basename "$LOG_FILE")" "$LOG_DIR/setup-latest.log"
  exec > >(tee -a "$LOG_FILE") 2>&1
  echo "Setup log: $LOG_FILE"
  echo "Latest setup log: $LOG_DIR/setup-latest.log"
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

phase() {
  echo
  echo "== $1 =="
}

homebrew_network_hint() {
  echo "      -> Это похоже на сетевую ошибку Homebrew при скачивании bottle'ов с ghcr.io."
  echo "      -> Ничего приватного в этот момент не отправляется: Homebrew скачивает ffmpeg и его зависимости."
  echo "      -> Лучше остановиться, попробовать другую сеть/позже и снова запустить Настроить Диктум.command."
  echo "      -> Уже скачанные части Homebrew обычно переиспользует при повторном запуске."
}

stop_after_failed_phase() {
  local phase_name="$1"
  warn "Останавливаюсь после этапа: $phase_name."
  echo "Следующие тяжелые шаги пока не запускаю: Python dependencies, HF token check, GigaSTT binary/models."
  echo "Сначала исправьте ошибки выше и запустите setup снова."
  print_next_steps
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
    echo "Homebrew скачает ffmpeg и набор зависимостей. На чистом Mac это самый длинный первый шаг."
    if ask_yes_no "Установить ffmpeg через Homebrew?" "y"; then
      if ! brew install ffmpeg; then
        fail "Homebrew не смог установить ffmpeg."
        homebrew_network_hint
        return 1
      fi
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

prepare_runtime_caches() {
  mkdir -p "$MPLCONFIG_DIR"
  ok "Локальные cache-папки подготовлены."
  if [[ ! -x "$VENV_PYTHON" ]]; then
    warn "Matplotlib cache не прогрет: .venv Python не найден."
    return 0
  fi
  echo "Готовлю Matplotlib font cache заранее, чтобы первый запуск файла не выглядел зависшим."
  if MPLCONFIGDIR="$MPLCONFIG_DIR" "$VENV_PYTHON" - <<'PY' >/dev/null 2>&1
from matplotlib import font_manager
font_manager.findfont("DejaVu Sans")
PY
  then
    ok "Matplotlib font cache готов."
  else
    warn "Не удалось заранее прогреть Matplotlib cache. Это не блокирует setup; первый запуск pyannote может занять немного дольше."
  fi
}

print_hf_token_help() {
  echo
  echo "Зачем нужен Hugging Face token"
  echo "--------------------------------"
  echo "HF token нужен только для pyannote: это модуль, который разделяет запись"
  echo "по спикерам. Распознавание речи и web UI можно поставить без него, но"
  echo "разделение по людям будет не готово до настройки token."
  echo
  echo "Где взять token:"
  echo "1. Откройте https://huggingface.co/pyannote/speaker-diarization-community-1"
  echo "2. Войдите или зарегистрируйтесь в Hugging Face."
  echo "3. Примите условия доступа к модели pyannote под этим аккаунтом."
  echo "4. Создайте read-only token: https://huggingface.co/settings/tokens"
  echo
  echo "Для внешнего теста лучше создать отдельный read-only token, например"
  echo "dictum-family-test. Его можно передать отдельно от zip и"
  echo "потом отозвать в Hugging Face settings."
  echo
  echo "Не кладите реальный token в zip, README, чат или скриншоты. Setup сохранит"
  echo "его только в локальный .env на этом Mac и не напечатает значение в лог."
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
  print_hf_token_help
  if ask_yes_no "Вставить read-only HF token сейчас? Ввод будет скрыт." "y"; then
    local hf_token=""
    read -rs "hf_token?HF token (hidden input): "
    echo
    if [[ -n "$hf_token" ]]; then
      write_env_value "HF_TOKEN" "$hf_token"
      ok "HF_TOKEN сохранен в .env без вывода в лог."
    else
      warn "Пустой token не сохранен."
    fi
  else
    warn "HF token пропущен. Setup можно продолжить, но разделение по спикерам будет не готово."
  fi
}

print_gigastt_help() {
  echo
  echo "Зачем нужен GigaSTT / GigaAM v3"
  echo "--------------------------------"
  echo "Это основной локальный ASR-движок Диктум для русского языка:"
  echo "он превращает аудио в текст на этом Mac. Без него web UI откроется,"
  echo "но обработка записей не запустится."
  echo
  echo "Setup подготовит локальные файлы:"
  echo "- tools/bin/gigastt        - исполняемый файл распознавания"
  echo "- .models/gigastt/         - модели GigaAM v3"
  echo "- .models/gigastt/punct/   - модель пунктуации/регистра RUPunct"
  echo "- .cache/downloads/        - временный кеш загрузок"
  echo
  echo "Нужен интернет: скачивается GigaSTT release с GitHub, модели GigaAM v3"
  echo "и небольшая RUPunct-модель с Hugging Face. Это может занять несколько"
  echo "минут и сотни мегабайт. Если сеть оборвется,"
  echo "просто запустите setup снова: уже готовые файлы будут переиспользованы."
}

print_gigastt_inventory() {
  local bin="$WORKSPACE_DIR/tools/bin/gigastt"
  local model_dir="$WORKSPACE_DIR/.models/gigastt"
  echo
  echo "Инвентарь GigaSTT/GigaAM v3"
  echo "---------------------------"
  if [[ -x "$bin" ]]; then
    echo "[OK] tools/bin/gigastt"
  else
    echo "[MISSING] tools/bin/gigastt"
  fi
  if find "$model_dir" -maxdepth 3 \( -type f -o -type l \) -print -quit 2>/dev/null | grep -q .; then
    find "$model_dir" -maxdepth 3 \( -type f -o -type l \) -print 2>/dev/null | sort | while IFS= read -r path; do
      echo " - ${path#$WORKSPACE_DIR/}"
    done
  else
    echo " - .models/gigastt/ пустая или еще не создана"
  fi
}

verify_gigastt_runtime() {
  local bin="$WORKSPACE_DIR/tools/bin/gigastt"
  local model_dir="$WORKSPACE_DIR/.models/gigastt"
  local required=(
    "v3_rnnt_decoder.onnx"
    "v3_rnnt_joint.onnx"
    "v3_vocab.txt"
    "punct/rupunct_small_int8.onnx"
    "punct/config.json"
    "punct/tokenizer.json"
  )
  local file
  local missing=0

  if [[ ! -x "$bin" ]]; then
    echo "[MISSING] tools/bin/gigastt"
    missing=1
  fi
  if [[ ! -f "$model_dir/v3_rnnt_encoder.onnx" && ! -f "$model_dir/v3_rnnt_encoder_int8.onnx" ]]; then
    echo "[MISSING] .models/gigastt/v3_rnnt_encoder.onnx или v3_rnnt_encoder_int8.onnx"
    missing=1
  fi
  for file in "${required[@]}"; do
    if [[ ! -f "$model_dir/$file" ]]; then
      echo "[MISSING] .models/gigastt/$file"
      missing=1
    fi
  done

  [[ "$missing" == "0" ]]
}

ensure_gigastt() {
  if verify_gigastt_runtime >/dev/null; then
    ok "GigaSTT binary и GigaAM v3 модели найдены."
    print_gigastt_inventory
    return 0
  fi

  warn "GigaSTT/GigaAM v3 еще не готовы. Это основной ASR-движок для русского языка."
  print_gigastt_help
  print_gigastt_inventory
  if ask_yes_no "Скачать/подготовить GigaSTT и модели сейчас?" "y"; then
    if [[ ! -x "/bin/bash" ]]; then
      fail "Не найден /bin/bash, который нужен для запуска setup_gigastt.sh."
      echo "      -> Это необычно для macOS. Пришлите файл лога: ${LOG_FILE:-$LOG_DIR/setup-latest.log}"
      return 1
    fi
    if ! /bin/bash "$APP_DIR/scripts/setup_gigastt.sh"; then
      fail "Не удалось скачать или подготовить GigaSTT/GigaAM v3."
      echo "      -> Проверьте missing-строки выше: это может быть GigaSTT, GigaAM или punct-модель."
      echo "      -> Проверьте сеть/VPN/proxy и запустите setup еще раз."
      echo "      -> Уже скачанные части обычно переиспользуются."
      return 1
    fi
    print_gigastt_inventory
    if verify_gigastt_runtime; then
      ok "GigaSTT/GigaAM v3 готовы."
      return 0
    fi
  fi

  print_gigastt_inventory
  fail "GigaSTT/GigaAM v3 не подготовлены. Распознавание не запустится до настройки моделей."
  echo "      -> Запустите Настроить Диктум.command еще раз и подтвердите этап GigaSTT/GigaAM v3."
  echo "      -> Пришлите файл лога: ${LOG_FILE:-$LOG_DIR/setup-latest.log}"
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
  echo "Диктум setup"
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
  if [[ -n "$LOG_FILE" ]]; then
    echo "Лог setup: $LOG_FILE"
    echo "Последний лог: $LOG_DIR/setup-latest.log"
  fi
  echo
  if (( fail_count == 0 )); then
    echo "Базовая подготовка завершена."
    if ask_yes_no "Запустить Диктум сейчас?" "y"; then
      "$APP_DIR/scripts/start_server.sh"
      exit $?
    fi
  else
    echo "Есть проблемы, которые нужно исправить. После исправления запустите setup еще раз."
    echo "Setup можно безопасно запускать повторно: готовые шаги будут переиспользованы."
  fi
  pause_before_close
  if (( fail_count > 0 )); then
    exit 1
  fi
}

init_logging
print_header
print_machine_info
phase "Этап 1/5: базовые инструменты"
base_ready=1
ensure_homebrew || base_ready=0
ensure_ffmpeg || base_ready=0
ensure_python || base_ready=0
mkdir -p "$INBOX_DIR" "$OUTPUT_DIR"
ok "Папки Inbox и outputs подготовлены."
if [[ "$base_ready" != "1" ]]; then
  stop_after_failed_phase "базовые инструменты"
fi

phase "Этап 2/5: Python runtime"
runtime_ready=1
if [[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]]; then
  ensure_venv_and_dependencies "$PYTHON_BIN" || runtime_ready=0
else
  runtime_ready=0
fi
if [[ "$runtime_ready" != "1" ]]; then
  stop_after_failed_phase "Python runtime"
fi
prepare_runtime_caches

phase "Этап 3/5: локальный HF token"
ensure_env_file || true

phase "Этап 4/5: GigaSTT/GigaAM v3"
ensure_gigastt || true

phase "Этап 5/5: проверки"
check_pyannote_access || true
smoke_test || true
print_next_steps
