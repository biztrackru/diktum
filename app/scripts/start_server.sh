#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
HOST="${VOICE_RECOGNIZER_HOST:-127.0.0.1}"
PORT="${VOICE_RECOGNIZER_PORT:-8765}"
OPEN_BROWSER="${VOICE_RECOGNIZER_OPEN_BROWSER:-1}"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"
PYTHON="$WORKSPACE_DIR/.venv/bin/python"
INBOX_DIR="${VOICE_RECOGNIZER_INBOX:-Inbox}"
OUTPUT_DIR="${VOICE_RECOGNIZER_OUTPUT_DIR:-outputs/pipeline}"
URL="http://$HOST:$PORT/"

cd "$WORKSPACE_DIR" || exit 1

if [[ -z "${VOICE_RECOGNIZER_INBOX:-}" && ! -d "$INBOX_DIR" && -d "inbox" ]]; then
  INBOX_DIR="inbox"
fi

pause_before_close() {
  if [[ "$PAUSE_ON_EXIT" == "0" ]]; then
    return
  fi
  echo
  read -r "reply?Нажмите Enter, чтобы закрыть это окно..."
}

pids_on_port() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN -nP 2>/dev/null
}

show_port_owner() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

open_browser() {
  if [[ "$OPEN_BROWSER" == "0" ]]; then
    return
  fi
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  fi
}

stop_port_owner() {
  local pids
  pids=(${(@f)$(pids_on_port)})
  if (( ${#pids[@]} == 0 )); then
    return 0
  fi

  echo "Останавливаю старый сервер на порту $PORT..."
  local pid
  for pid in "${pids[@]}"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  local attempt
  for attempt in {1..20}; do
    sleep 0.25
    if [[ -z "$(pids_on_port)" ]]; then
      echo "Порт $PORT освобожден."
      return 0
    fi
  done

  echo "Не получилось мягко остановить процесс:"
  show_port_owner
  echo
  if ! read -r "force_reply?Принудительно завершить этот процесс? [y/N] "; then
    force_reply=""
  fi
  case "$force_reply" in
    y|Y|yes|YES|д|Д|да|Да|ДА)
      pids=(${(@f)$(pids_on_port)})
      for pid in "${pids[@]}"; do
        if [[ -n "$pid" ]]; then
          kill -9 "$pid" 2>/dev/null || true
        fi
      done
      sleep 0.5
      ;;
  esac

  if [[ -n "$(pids_on_port)" ]]; then
    echo "Порт $PORT все еще занят. Запуск отменен."
    show_port_owner
    pause_before_close
    exit 1
  fi
}

if [[ ! -x "$PYTHON" ]]; then
  echo "Не найден исполняемый файл:"
  echo "$PYTHON"
  echo
  echo "Проверьте, что виртуальное окружение создано. Следующий шаг:"
  echo "  cd \"$WORKSPACE_DIR\""
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -e 'app[diarization]'"
  pause_before_close
  exit 1
fi

export PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "Диктум"
echo "Рабочая папка: $WORKSPACE_DIR"
echo "Приложение:    $APP_DIR"
echo "Адрес:  $URL"
echo

if [[ -n "$(pids_on_port)" ]]; then
  echo "Порт $PORT уже занят. Вероятно, старая версия сервера еще работает:"
  show_port_owner
  echo
  echo "Что сделать?"
  echo "1) Остановить старый процесс и запустить свежий сервер"
  echo "2) Оставить старый процесс работать и открыть его в браузере"
  echo "3) Выйти без изменений"
  echo
  while true; do
    if ! read -r "choice?Выберите 1, 2 или 3: "; then
      echo "Не удалось прочитать ответ. Ничего не меняю."
      pause_before_close
      exit 1
    fi
    case "$choice" in
      1)
        stop_port_owner
        break
        ;;
      2)
        echo "Оставляю текущий сервер работать."
        open_browser
        pause_before_close
        exit 0
        ;;
      3)
        echo "Ничего не меняю."
        pause_before_close
        exit 0
        ;;
      *)
        echo "Введите 1, 2 или 3."
        ;;
    esac
  done
fi

echo "Запускаю свежий сервер..."
echo "Чтобы остановить его вручную, нажмите Ctrl+C в этом окне."
echo

if [[ "$OPEN_BROWSER" != "0" ]]; then
  (sleep 1; open_browser) &
fi
"$PYTHON" -m voice_recognizer.cli web \
  --host "$HOST" \
  --port "$PORT" \
  --inbox "$INBOX_DIR" \
  --output-dir "$OUTPUT_DIR"
exit_code=$?

echo
echo "Сервер завершил работу с кодом $exit_code."
pause_before_close
exit "$exit_code"
