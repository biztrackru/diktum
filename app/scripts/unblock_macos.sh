#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
PAUSE_ON_EXIT="${VOICE_RECOGNIZER_PAUSE_ON_EXIT:-1}"

pause_before_close() {
  if [[ "$PAUSE_ON_EXIT" == "0" ]]; then
    return
  fi
  echo
  read -r "reply?Нажмите Enter, чтобы закрыть это окно..."
}

echo "Диктум macOS unblock"
echo "Рабочая папка: $WORKSPACE_DIR"
echo
echo "macOS может помечать zip из Telegram/AirDrop/браузера как downloaded/quarantined."
echo "Из-за этого Finder показывает предупреждение про непроверенное ПО."
echo
echo "Этот helper снимает quarantine-метку только с файлов внутри этой папки:"
echo "$WORKSPACE_DIR"
echo
echo "Он не требует admin password, не отправляет данные в интернет и не меняет настройки macOS."
echo

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[WARN] Это не macOS. Нечего разблокировать."
  pause_before_close
  exit 0
fi

if ! command -v xattr >/dev/null 2>&1; then
  echo "[FAIL] Не найдена системная команда xattr."
  pause_before_close
  exit 1
fi

echo "Снимаю quarantine-метку..."
xattr -r -d com.apple.quarantine "$WORKSPACE_DIR" 2>/dev/null || true

remaining="$(xattr -lr "$WORKSPACE_DIR" 2>/dev/null | grep -c "com.apple.quarantine" || true)"
if [[ "$remaining" == "0" ]]; then
  echo "[OK] Quarantine-метка снята. Теперь можно запускать:"
  echo "     Настроить Диктум.command"
  echo "     Проверить Диктум.command"
  echo "     Запустить Диктум.command"
  pause_before_close
  exit 0
fi

echo "[WARN] На части файлов quarantine-метка осталась: $remaining"
echo
echo "Fallback через Terminal:"
echo "1. Откройте Terminal."
echo "2. Вставьте команду ниже и нажмите Enter:"
echo
echo "xattr -dr com.apple.quarantine \"$WORKSPACE_DIR\""
echo
echo "3. Потом снова запустите Настроить Диктум.command."
pause_before_close
exit 1
