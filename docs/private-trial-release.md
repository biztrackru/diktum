# Private Trial Release

Дата: 2026-06-29.

## Решение

Текущий private trial надо собирать на стабильном baseline:

- ASR: `gigastt-gigaam-v3`;
- основной текст для пользователя: edited exports;
- разделение спикеров: текущий pyannote pipeline;
- альтернативные ASR/LLM/Handy/MacWhisper/Whisper/FluidAudio исследования не входят в trial build.

Причина: локальные кандидаты не выиграли private benchmark у текущего решения, а добавление их в UI увеличит сложность установки и поддержки без доказанного выигрыша.

## Что отправляем тестировщику

Один zip:

```text
.dist/Voice Recognizer Trial <timestamp>.zip
```

Отдельно от zip:

- read-only HF token, если тестировщик должен получить diarization без самостоятельной регистрации;
- короткое сообщение: распаковать, открыть `START_HERE.txt`, дальше идти по double-click launchers.

Не отправлять:

- `.env`;
- аудио из `Inbox/`;
- результаты из `outputs/`;
- `.models`, `.venv`, `.cache`, `tools/bin`;
- приватные `.docx`/черновики;
- полный dev workspace.

## Release acceptance перед отправкой

1. Рабочее дерево чистое по tracked-файлам или все изменения осознанно закоммичены.
2. Выполнены проверки:

```bash
app/scripts/smoke_local.sh
zsh -n app/scripts/*.sh
git diff --check
git diff --cached --check
```

3. Собран trial pack:

```bash
app/scripts/build_install_pack.sh
```

4. Проверено содержимое архива:

- есть `START_HERE.txt`;
- есть `VERSION.txt`;
- есть `FEEDBACK_TEMPLATE.txt`;
- есть launchers `Настроить`, `Проверить`, `Запустить`, `Остановить`, `Разблокировать`;
- есть `app/`, `docs/`, пустые `Inbox/`, `outputs/`;
- нет `.env`, `.venv`, `.models`, `.cache`, `logs`, `tools/bin`, приватных аудио и generated transcripts.

## Что просить у тестировщика

Попросить пройти минимальный сценарий:

1. Распаковать zip.
2. Открыть `START_HERE.txt`.
3. При необходимости запустить `Разблокировать Voice Recognizer.command`.
4. Запустить `Настроить Voice Recognizer.command`.
5. Запустить `Проверить Voice Recognizer.command`.
6. Запустить `Запустить Voice Recognizer.command`.
7. Загрузить короткий аудиофайл или тестовый фрагмент.
8. Дождаться результата, переименовать спикеров, открыть текстовые файлы.
9. Остановить сервер.
10. Заполнить `FEEDBACK_TEMPLATE.txt`.

## Feedback triage

Сначала чинить trial blockers:

1. Setup не запускается двойным кликом.
2. Setup/doctor просит непонятные Terminal-команды.
3. Gatekeeper/quarantine инструкция не помогает.
4. Токен или приватные данные попали в лог.
5. GigaSTT/model setup падает без понятного next step.
6. Web UI не открывается или не может загрузить файл.
7. Результат не открывается по ссылкам.
8. Stop не останавливает сервер.

Только после этого выбирать следующую продуктовую инвестицию:

- long-file resume/progress;
- batch reliability;
- speaker quality;
- text quality repair;
- engine registry / alternate ASR.
