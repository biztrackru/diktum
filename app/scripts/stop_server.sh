#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
PORTS_TEXT="${VOICE_RECOGNIZER_PORTS:-8765 8766}"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"

cd "$WORKSPACE_DIR" || exit 1

pause_before_close() {
  if [[ "$PAUSE_ON_EXIT" == "0" ]]; then
    return
  fi
  echo
  read -r "reply?Нажмите Enter, чтобы закрыть это окно..."
}

pids_on_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN -nP 2>/dev/null
}

show_port_owner() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

add_pid() {
  local pid="$1"
  if [[ -z "$pid" || "$pid" == "$$" ]]; then
    return
  fi
  if [[ -z "${seen_pids[$pid]-}" ]]; then
    seen_pids[$pid]=1
    pids+=("$pid")
  fi
}

typeset -A seen_pids
pids=()
ports=("${(@s: :)PORTS_TEXT}")
pid=""
port_pids=()
process_pids=()
still_running=()

echo "Диктум: остановка серверов"
echo "Рабочая папка: $WORKSPACE_DIR"
echo "Приложение:    $APP_DIR"
echo

local_port=""
for local_port in "${ports[@]}"; do
  if [[ -z "$local_port" ]]; then
    continue
  fi
  port_pids=(${(@f)$(pids_on_port "$local_port")})
  if (( ${#port_pids[@]} > 0 )); then
    echo "Порт $local_port занят:"
    show_port_owner "$local_port"
    echo
    for pid in "${port_pids[@]}"; do
      add_pid "$pid"
    done
  fi
done

if command -v pgrep >/dev/null 2>&1; then
  process_pids=(${(@f)$(pgrep -f '[v]oice-recognizer web|[v]oice_recognizer.cli.*web' 2>/dev/null)})
  for pid in "${process_pids[@]}"; do
    add_pid "$pid"
  done
fi

if (( ${#pids[@]} == 0 )); then
  echo "Запущенных серверов Диктум не найдено."
  pause_before_close
  exit 0
fi

echo "Будут остановлены PID:"
for pid in "${pids[@]}"; do
  ps -p "$pid" -o pid=,command= 2>/dev/null || echo "$pid"
done
echo

if ! read -r "reply?Остановить эти процессы? [Y/n] "; then
  reply=""
fi
case "$reply" in
  n|N|no|NO|нет|Нет|НЕТ)
    echo "Ничего не остановлено."
    pause_before_close
    exit 0
    ;;
esac

for pid in "${pids[@]}"; do
  kill "$pid" 2>/dev/null || true
done

attempt=""
for attempt in {1..20}; do
  sleep 0.25
  still_running=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      still_running+=("$pid")
    fi
  done
  if (( ${#still_running[@]} == 0 )); then
    echo "Серверы остановлены."
    pause_before_close
    exit 0
  fi
done

echo "Некоторые процессы не остановились мягко:"
for pid in "${still_running[@]}"; do
  ps -p "$pid" -o pid=,command= 2>/dev/null || echo "$pid"
done
echo
if ! read -r "force_reply?Принудительно завершить их? [y/N] "; then
  force_reply=""
fi
case "$force_reply" in
  y|Y|yes|YES|д|Д|да|Да|ДА)
    for pid in "${still_running[@]}"; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
    echo "Готово."
    ;;
  *)
    echo "Оставлено без принудительного завершения."
    ;;
esac

pause_before_close
