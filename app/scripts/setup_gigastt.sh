#!/bin/bash
# Compatible with macOS /bin/bash 3.2. Versions and SHA-256 live in resources.json.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
PYTHON="${VOICE_RECOGNIZER_PYTHON:-$WORKSPACE_DIR/.venv/bin/python}"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo "Эта сборка ресурсов предназначена для macOS Apple Silicon (arm64)." >&2
  exit 1
fi
if [ ! -x "$PYTHON" ]; then
  echo "Сначала запустите Настроить Диктум.command для подготовки Python 3.12." >&2
  exit 1
fi
export PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
echo "Диктум: установка GigaSTT 2.22.0, GigaAM v3, CTC и Silero v4/v6."
echo "Ресурсы скачиваются по HTTPS и проверяются по SHA-256."
echo "Прежние заменяемые файлы сохраняются в .cache/resource-backups/."
arguments=(install gigastt rnnt ctc vad --root "$WORKSPACE_DIR")
if [ "${VOICE_RECOGNIZER_SETUP_OFFLINE:-0}" = 1 ]; then
  arguments+=(--offline)
fi
"$PYTHON" -m voice_recognizer.assets "${arguments[@]}"
"$WORKSPACE_DIR/tools/bin/gigastt" --version
echo "Локальные ресурсы готовы. Обновление не меняет аудио, результаты и профили голосов."
