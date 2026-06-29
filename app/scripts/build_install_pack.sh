#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$APP_DIR/.." && pwd)"
DIST_DIR="${VOICE_RECOGNIZER_DIST_DIR:-$WORKSPACE_DIR/.dist}"
STAMP="$(date +%Y%m%d-%H%M%S)"
PACK_NAME="Voice Recognizer Trial $STAMP"
PACK_DIR="$DIST_DIR/$PACK_NAME"
ARCHIVE="$DIST_DIR/$PACK_NAME.zip"
GIT_BRANCH="$(git -C "$WORKSPACE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
GIT_COMMIT="$(git -C "$WORKSPACE_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="unknown"
if git -C "$WORKSPACE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$WORKSPACE_DIR" diff --quiet -- . && git -C "$WORKSPACE_DIR" diff --cached --quiet -- .; then
    GIT_DIRTY="clean"
  else
    GIT_DIRTY="dirty"
  fi
fi

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
Voice Recognizer Trial Pack
===========================

Что это
-------
Это пробный локальный пакет Voice Recognizer для macOS.
Он НЕ содержит ваши аудио, результаты, модели, .env, токены или Python .venv.

Первый запуск на другом Mac
---------------------------
1. Распакуйте zip в обычную папку, например ~/Applications/Voice Recognizer Trial.
2. Если macOS пишет "не удалось проверить на наличие вредоносного ПО",
   один раз запустите "Разблокировать Voice Recognizer.command".
3. Дважды кликните "Настроить Voice Recognizer.command".
4. Отвечайте на вопросы setup. Он идет этапами: Homebrew/ffmpeg/Python, затем Python runtime, затем HF token, затем GigaSTT/models.
5. Дважды кликните "Проверить Voice Recognizer.command".
6. Если doctor не нашёл блокирующих проблем, дважды кликните "Запустить Voice Recognizer.command".
7. Браузер должен открыться на http://127.0.0.1:8765/.
8. Загрузите короткий .m4a/.mp3/.wav через web UI и запустите тест-фрагмент на 30-120 секунд.
9. Для остановки дважды кликните "Остановить Voice Recognizer.command".
10. После теста заполните "FEEDBACK_TEMPLATE.txt". В нем уже есть поля,
    которые помогут быстро понять, что сломалось или что стоит улучшить.

Если macOS блокирует .command файлы
-----------------------------------
Это Gatekeeper/quarantine: macOS пометила распакованные файлы как скачанные
из внешнего источника. Сейчас пакет не подписан Apple Developer ID и не
notarized, поэтому macOS может предлагать "Move to Trash/Переместить в корзину".

Малый workaround:
1. Правый клик по "Разблокировать Voice Recognizer.command" -> Open/Открыть.
2. Если macOS отправляет в System Settings -> Privacy & Security, нажмите
   "Open Anyway/Все равно открыть" именно для этого helper.
3. Helper снимет quarantine-метку со всей папки Voice Recognizer Trial.
4. После этого обычные double-click launchers должны открываться нормально.

Если helper тоже неудобно открыть, Terminal fallback:
1. Откройте Terminal.
2. Вставьте команду, оставив пробел в конце:

   xattr -dr com.apple.quarantine 

3. Перетащите папку Voice Recognizer Trial из Finder прямо в окно Terminal.
4. Нажмите Enter.
5. Вернитесь в Finder и запустите "Настроить Voice Recognizer.command".

Правильное будущее решение: Apple Developer ID signing + notarization. Это
уберет такие предупреждения нормально, но требует отдельного release-процесса.

Про HF token
------------
HF token нужен только для pyannote, то есть для разделения записи по спикерам.
Web UI и часть setup можно поставить без него, но speaker diarization будет не готова.

Где взять:
1. Откройте https://huggingface.co/pyannote/speaker-diarization-community-1
2. Войдите или зарегистрируйтесь в Hugging Face.
3. Примите условия доступа к модели pyannote.
4. Создайте read-only token: https://huggingface.co/settings/tokens

Для семейного теста лучше создать отдельный read-only token, например
voice-recognizer-family-test, передать его отдельно от zip и при необходимости
потом отозвать. Не кладите реальный token в архив: setup попросит вставить его
скрытым вводом и сохранит только в локальный .env на этом Mac.

Про GigaSTT / GigaAM v3
----------------------
GigaSTT / GigaAM v3 - это основной локальный распознаватель речи для русского
языка. Он превращает аудио в текст. Без него web UI может открыться, но
обработка записей не запустится.

Binary и модели намеренно не входят в zip: они тяжелые и должны быть
подготовлены на том Mac, где будет запускаться приложение. На этапе 4/5 setup
скачает:
- tools/bin/gigastt
- .models/gigastt/
- .models/gigastt/punct/

Нужен интернет. Загрузка может занять несколько минут и сотни мегабайт.
Если скачивание оборвалось, запустите "Настроить Voice Recognizer.command"
снова: уже готовые файлы будут переиспользованы.

Если после setup UI все еще пишет "GigaSTT не настроен"
--------------------------------------------------------
1. Дважды кликните "Проверить Voice Recognizer.command".
2. Откройте папку logs/.
3. Перешлите разработчику только эти файлы:
   - logs/setup-latest.log
   - logs/doctor-latest.log

Не пересылайте .env, аудио из Inbox/ или результаты из outputs/.
Логи содержат инвентарь GigaSTT/GigaAM файлов и missing-компоненты, но не
должны печатать HF token.

Если первый тестовый файл долго "выполняется"
---------------------------------------------
После чистой установки первый запуск pyannote может несколько минут готовить
локальный cache модели разделения спикеров. В техническом журнале задачи
должны появляться строки "Diarization / pyannote: ...". Это нормальный признак
живого процесса. Если таких строк нет 10+ минут, перешлите технический лог
задачи разработчику.

Где будут личные данные
-----------------------
- Аудио: Inbox/
- Результаты: outputs/
- Токен: .env
- Python runtime: .venv/
- Модели: .models/
- GigaSTT binary: tools/bin/
- Логи установки/проверки: logs/

Эти папки создаются локально на этом Mac и не входят в исходный zip.

Если macOS ругается на файл .command
------------------------------------
Сначала попробуйте "Разблокировать Voice Recognizer.command". Если macOS
блокирует даже его, используйте Terminal fallback из раздела выше.

Если Homebrew не докачивает ffmpeg
----------------------------------
Если видите "Failed to download resource", "curl: (28)", "curl: (35)" или ссылки
на ghcr.io, остановите setup через Ctrl+C и попробуйте другую сеть/позже.
Setup можно запускать повторно: уже готовые шаги будут переиспользованы.
Не переходите к Python dependencies, HF token и моделям, пока ffmpeg не установлен.

Подробный чеклист: docs/spouse-mac-install-trial.md
TXT
}

write_version_file() {
  cat > "$PACK_DIR/VERSION.txt" <<TXT
Voice Recognizer Trial
======================

Build timestamp: $STAMP
Git branch: $GIT_BRANCH
Git commit: $GIT_COMMIT
Git working tree at build time: $GIT_DIRTY

Runtime data is local to the unpacked folder and is not part of this build:
.env, .venv, .models, .cache, tools/bin, Inbox contents, outputs and logs.

Baseline for this private trial:
- ASR: GigaSTT / GigaAM v3 RNNT
- Speaker separation: pyannote Community-1
- User-facing transcript: edited exports when available
- Alternate ASR engines: not included in this trial build
TXT
}

write_release_notes() {
  cat > "$PACK_DIR/TRIAL_RELEASE_NOTES.txt" <<'TXT'
Voice Recognizer Private Trial Notes
====================================

Цель этой сборки
----------------
Проверить не лабораторное качество модели, а реальный путь пользователя:
распаковал zip, запустил setup, открыл локальный web UI, обработал запись,
переименовал спикеров, открыл итоговые файлы.

Что сейчас должно работать
--------------------------
- локальная установка через double-click setup;
- проверка окружения через doctor;
- запуск/остановка локального web-сервера;
- загрузка аудио через web UI;
- очередь задач и отмена случайных запусков;
- длинные файлы через ASR chunking;
- разделение по спикерам;
- переименование спикеров после результата;
- Markdown/TXT exports, включая edited-текст.

Известные ограничения
---------------------
- пакет пока не подписан Apple Developer ID и не notarized, поэтому macOS
  может потребовать "Разблокировать Voice Recognizer.command";
- первый setup скачивает зависимости и модели, нужен интернет;
- HF token нужен для разделения по спикерам;
- полное восстановление long-file job после падения сервера еще не финальное;
- качество спикеров и текста может требовать ручной проверки на сложных записях;
- альтернативные ASR-движки Handy/MacWhisper/Whisper не включены: они не
  выиграли текущий benchmark у baseline.
TXT
}

write_feedback_template() {
  cat > "$PACK_DIR/FEEDBACK_TEMPLATE.txt" <<'TXT'
Voice Recognizer Feedback
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
2. Нужно было запускать "Разблокировать Voice Recognizer.command":
3. "Настроить Voice Recognizer.command" дошел до конца:
4. Что было непонятно в setup:
5. "Проверить Voice Recognizer.command" показал failures=0:
6. Если были ошибки, какие строки из logs/setup-latest.log или logs/doctor-latest.log можно прислать без токенов:

Запуск и интерфейс
------------------
1. "Запустить Voice Recognizer.command" открыл браузер:
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

write_pack_manifest() {
  cat > "$PACK_DIR/PACK_CONTENTS.txt" <<TXT
Voice Recognizer trial pack
Built: $(date)
Source: $WORKSPACE_DIR

Included:
- root *.command launchers
- macOS quarantine unblock helper
- START_HERE.txt
- VERSION.txt
- TRIAL_RELEASE_NOTES.txt
- FEEDBACK_TEMPLATE.txt
- app/src
- app/scripts
- app/config
- app/pyproject.toml
- app/.env.example
- README.md
- LICENSE and SECURITY.md
- selected docs
- empty Inbox/
- empty outputs/

Intentionally excluded:
- .env and .env.*
- .venv/
- .models/
- .cache/
- .dist/
- logs/
- tools/bin/
- Inbox/* audio files
- outputs/* generated transcripts
- private docx/drafts
TXT
}

prune_runtime_files() {
  find "$PACK_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
  find "$PACK_DIR" -name "*.pyc" -type f -delete
  find "$PACK_DIR" -name ".DS_Store" -type f -delete
}

mkdir -p "$PACK_DIR"

copy_file "Проверить Voice Recognizer.command" "$PACK_DIR/Проверить Voice Recognizer.command"
copy_file "Разблокировать Voice Recognizer.command" "$PACK_DIR/Разблокировать Voice Recognizer.command"
copy_file "Настроить Voice Recognizer.command" "$PACK_DIR/Настроить Voice Recognizer.command"
copy_file "Запустить Voice Recognizer.command" "$PACK_DIR/Запустить Voice Recognizer.command"
copy_file "Остановить Voice Recognizer.command" "$PACK_DIR/Остановить Voice Recognizer.command"
copy_file "README.md" "$PACK_DIR/README.md"
copy_file "LICENSE" "$PACK_DIR/LICENSE"
copy_file "SECURITY.md" "$PACK_DIR/SECURITY.md"

copy_file "app/pyproject.toml" "$PACK_DIR/app/pyproject.toml"
copy_file "app/.env.example" "$PACK_DIR/app/.env.example"
copy_dir "app/src" "$PACK_DIR/app/src"
copy_dir "app/scripts" "$PACK_DIR/app/scripts"
copy_dir "app/config" "$PACK_DIR/app/config"

copy_file "docs/local-mac-product-plan.md" "$PACK_DIR/docs/local-mac-product-plan.md"
copy_file "docs/setup-secrets.md" "$PACK_DIR/docs/setup-secrets.md"
copy_file "docs/private-trial-release.md" "$PACK_DIR/docs/private-trial-release.md"
if [[ -f "docs/spouse-mac-install-trial.md" ]]; then
  copy_file "docs/spouse-mac-install-trial.md" "$PACK_DIR/docs/spouse-mac-install-trial.md"
fi

mkdir -p "$PACK_DIR/Inbox" "$PACK_DIR/outputs"
write_start_here
write_version_file
write_release_notes
write_feedback_template
write_pack_manifest

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
echo "Private runtime data was not copied. The target Mac will create its own .env, .venv, .models, tools/bin, Inbox and outputs."
