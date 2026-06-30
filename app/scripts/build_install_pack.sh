#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
DIST_DIR="${VOICE_RECOGNIZER_DIST_DIR:-$WORKSPACE_DIR/.dist}"
STAMP="$(date +%Y%m%d-%H%M%S)"
PACK_LABEL="${DICTUM_PACK_LABEL:-Trial}"
PACK_VERSION="${DICTUM_PACK_VERSION:-$STAMP}"
PACK_NAME="Диктум $PACK_LABEL $PACK_VERSION"
PACK_DIR="$DIST_DIR/$PACK_NAME"
ARCHIVE="$DIST_DIR/$PACK_NAME.zip"
GIT_COMMIT="$(git -C "$WORKSPACE_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"

cd "$WORKSPACE_DIR" || exit 1

copy_file() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
}

copy_dir() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "$target")"
  ditto "$source" "$target"
}

write_start_here() {
  cat > "$PACK_DIR/START_HERE.txt" <<'TXT'
Диктум Trial Pack
===========================

Что это
-------
Диктум - локальное приложение для Mac. Оно помогает превратить
аудиозапись встречи, интервью или обучения в текст с разделением по спикерам.

Записи, результаты, модели и токены хранятся только в этой папке на вашем Mac.

Быстрый старт
-------------
1. Распакуйте zip в обычную папку, например ~/Applications/Диктум Trial.
2. Откройте распакованную папку в Finder.
3. Если macOS блокирует запуск, дважды кликните
   "Разблокировать Диктум.command".
4. Дважды кликните "Настроить Диктум.command" и отвечайте на вопросы.
5. Дважды кликните "Проверить Диктум.command".
6. Если проверка не нашла блокирующих проблем, дважды кликните
   "Запустить Диктум.command".
7. Браузер должен открыться на http://127.0.0.1:8765/.
8. Загрузите короткий аудиофайл и запустите обработку.
9. После результата проверьте текст, назовите спикеров и откройте файлы результата.
10. Чтобы завершить работу, дважды кликните
    "Остановить Диктум.command".
11. После теста заполните "FEEDBACK_TEMPLATE.txt".

Если macOS блокирует запуск
---------------------------
1. Правый клик по "Разблокировать Диктум.command".
2. Нажмите Open/Открыть.
3. Если macOS попросит подтверждение в Privacy & Security, нажмите Open Anyway.
4. После этого обычные команды настройки, проверки и запуска должны открываться
   двойным кликом.

Что установит setup
-------------------
Setup может попросить разрешение установить или скачать:

- Homebrew, если его нет;
- ffmpeg для чтения аудиофайлов;
- Python runtime в локальную папку .venv/;
- локальные модели распознавания речи в .models/;
- GigaSTT binary в tools/bin/.

Для разделения записи по спикерам нужен Hugging Face token. Если разработчик
дал вам read-only token отдельно от архива, вставьте его в setup, когда он
попросит. Значение не печатается в окне и сохраняется только в локальный .env.

Где будут данные
----------------
- Аудио: Inbox/
- Результаты: outputs/
- Токен: .env
- Модели: .models/
- Python runtime: .venv/
- Логи настройки и проверки: logs/

Что делать при проблеме
-----------------------
1. Запустите "Проверить Диктум.command".
2. Откройте папку logs/.
3. Перешлите разработчику только:
   - logs/setup-latest.log
   - logs/doctor-latest.log

Не пересылайте .env, аудио из Inbox/ или результаты из outputs/.
TXT
}

write_version_file() {
  cat > "$PACK_DIR/VERSION.txt" <<TXT
Диктум $PACK_LABEL
======================

Build ID: $PACK_VERSION-$GIT_COMMIT

Runtime data is local to the unpacked folder and is not part of this build:
.env, .venv, .models, .cache, tools/bin, Inbox contents, outputs and logs.
TXT
}

write_feedback_template() {
  cat > "$PACK_DIR/FEEDBACK_TEMPLATE.txt" <<'TXT'
Диктум Feedback
=========================

Пожалуйста, заполните после теста. Не прикладывайте .env, аудио, outputs или
модели, если об этом отдельно не попросили.

1. Mac model/chip:
2. RAM:
3. macOS version:
4. Был ли Homebrew установлен до теста:
5. Был ли Python установлен до теста:
6. Был ли Hugging Face token готов до теста:

Установка
---------
1. Получилось распаковать zip:
2. Нужно было запускать "Разблокировать Диктум.command":
3. "Настроить Диктум.command" дошел до конца:
4. Что было непонятно в setup:
5. "Проверить Диктум.command" показал failures=0:
6. Если были ошибки, какие строки из logs/setup-latest.log или logs/doctor-latest.log можно прислать без токенов:

Запуск и интерфейс
------------------
1. "Запустить Диктум.command" открыл браузер:
2. Адрес был http://127.0.0.1:8765/:
3. Файл загрузился через интерфейс:
4. Очередь/статус задачи были понятны:
5. Получилось остановить сервер:

Результат
---------
1. Тип записи: интервью / обучение / встреча / другое:
2. Длительность тестового файла:
3. Сколько примерно спикеров:
4. Разделение по спикерам помогло:
5. Имена спикеров удалось применить:
6. Итоговый текст пригоден для работы:
7. Какие ошибки в тексте повторялись:
8. Какие файлы результата удалось открыть:

Оценка
------
1. Что помешало больше всего:
2. Что было неожиданно удобно:
3. Что обязательно исправить до следующей сборки:
4. Можно ли дать эту сборку еще одному человеку:
5. Дополнительные заметки:
TXT
}

prune_runtime_files() {
  find "$PACK_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
  find "$PACK_DIR" -name "*.pyc" -type f -delete
  find "$PACK_DIR" -name ".DS_Store" -type f -delete
}

mkdir -p "$PACK_DIR"

copy_file "Проверить Диктум.command" "$PACK_DIR/Проверить Диктум.command"
copy_file "Разблокировать Диктум.command" "$PACK_DIR/Разблокировать Диктум.command"
copy_file "Настроить Диктум.command" "$PACK_DIR/Настроить Диктум.command"
copy_file "Запустить Диктум.command" "$PACK_DIR/Запустить Диктум.command"
copy_file "Остановить Диктум.command" "$PACK_DIR/Остановить Диктум.command"

copy_file "app/pyproject.toml" "$PACK_DIR/app/pyproject.toml"
copy_file "app/.env.example" "$PACK_DIR/app/.env.example"
copy_dir "app/src" "$PACK_DIR/app/src"
copy_file "app/scripts/doctor_local_mac.sh" "$PACK_DIR/app/scripts/doctor_local_mac.sh"
copy_file "app/scripts/setup_gigastt.sh" "$PACK_DIR/app/scripts/setup_gigastt.sh"
copy_file "app/scripts/setup_local_mac.sh" "$PACK_DIR/app/scripts/setup_local_mac.sh"
copy_file "app/scripts/start_server.sh" "$PACK_DIR/app/scripts/start_server.sh"
copy_file "app/scripts/stop_server.sh" "$PACK_DIR/app/scripts/stop_server.sh"
copy_file "app/scripts/unblock_macos.sh" "$PACK_DIR/app/scripts/unblock_macos.sh"
mkdir -p "$PACK_DIR/app/config"
copy_file "app/config/speaker-counts.example.json" "$PACK_DIR/app/config/speaker-counts.json"
copy_file "app/config/hotwords.example.txt" "$PACK_DIR/app/config/hotwords.example.txt"

mkdir -p "$PACK_DIR/Inbox" "$PACK_DIR/outputs"
write_start_here
write_version_file
write_feedback_template

prune_runtime_files

chmod +x "$PACK_DIR"/*.command
chmod +x "$PACK_DIR/app/scripts/"*.sh

(
  cd "$DIST_DIR"
  COPYFILE_DISABLE=1 ditto -c -k --norsrc --noextattr --keepParent "$PACK_NAME" "$ARCHIVE"
)

echo "Install trial pack is ready:"
echo "$PACK_DIR"
echo
echo "Archive:"
echo "$ARCHIVE"
echo
echo "Only user-facing trial files were copied. Private runtime data was not copied."
echo "The target Mac will create its own .env, .venv, .models, tools/bin, Inbox and outputs."
