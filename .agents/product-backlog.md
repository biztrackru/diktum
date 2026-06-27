# Product Backlog

Дата актуализации: 2026-06-27.

Этот файл - источник правды для следующих задач Codex, Claude Code и review-агентов. `.agents/task-board.md` остается журналом выполненных delivery-блоков и местом для активного claim, но приоритеты брать отсюда.

## Product North Star

Ориентир текущего этапа: обычный пользователь Mac получает папку/пакет Voice Recognizer, запускает setup и затем обрабатывает длинные диктофонные записи локально без помощи разработчика и без Terminal.

Self-host, публичный GitHub, внешний лендинг и SwiftUI/native wrapper отложены до завершения локального продукта.

## Что уже реально сделано

- Локальный Python/web pipeline с GigaSTT/GigaAM v3 RNNT и pyannote diarization.
- ASR chunking для файлов длиннее лимита GigaSTT; дефолт 600 секунд для сохранения пунктуации.
- Web UI: Inbox, upload, queue/results views, batch subset selection, result tabs, exports, speaker samples/names, disk results from `outputs/`.
- Start/stop/setup/doctor `.command` и shell helpers существуют.
- Очередь умеет отменять queued/running jobs и удалять завершенные jobs из UI.
- ASR/speaker quality diagnostics пишутся в manifest и показываются в UI.
- `refresh-quality` backfill обновляет старые manifest без повторного ASR/diarization.
- Claude UX F1-F16 в основном реализованы в текущем web UI.

## Главные недоделки из диалогов

- Setup/doctor есть, но нет финального acceptance на чистом пользовательском Mac и нет installable layout, где пользователь не видит структуру dev-проекта.
- Очередь in-memory: после перезапуска сервера состояние jobs теряется, а долгие/упавшие процессы восстанавливаются только частично.
- Long-file story закрыта для ASR chunking, но не закрыта как полноценный resume/progress pipeline по этапам и chunks.
- Batch UX есть, но нуждается в надежной job persistence, resume и итоговом отчете по пачке.
- Выбор движков в UI пока по сути один рабочий backend: GigaSTT/GigaAM v3. Whisper/Handy/Wisper/LM Studio не интегрированы как реальные engine profiles.
- Диаризация получила диагностику, но не получила системный quality-improvement loop: сравнение конфигураций, улучшение speaker-islands, overlap/uncertain regions и приемочный benchmark.
- Speaker labeling работает в рамках результата, но speaker memory / повторное узнавание людей по голосу отложено.
- Нет компактного автоматизированного smoke/e2e набора на коротких безопасных fixtures, который можно гонять перед каждым релизным шагом.

## Task Status Model

- `READY` - можно брать в работу сейчас.
- `CLAIMED` - агент взял задачу; claim обязан быть отражен в `.agents/task-board.md`.
- `BLOCKED` - нужен пользовательский ввод, внешний доступ или решение по продукту.
- `DELIVERED` - код/документация сделаны, проверки записаны в `.agents/task-board.md`.
- `DEFERRED` - осознанно отложено.

## Ready Queue

### P0-001 Mac Install Acceptance

Status: READY.

Goal: доказать и довести путь установки до состояния "супруга на Apple Silicon Mac запускает без разработчика".

Scope:

- `app/scripts/doctor_local_mac.sh`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/start_server.sh`
- `app/scripts/stop_server.sh`
- `*.command`
- `README.md`
- `docs/local-mac-product-plan.md`

Acceptance:

- `zsh -n app/scripts/*.sh` проходит.
- `Проверить Voice Recognizer.command` дает понятный отчет без печати токенов.
- `Настроить Voice Recognizer.command` объясняет Homebrew/ffmpeg/Python/model/HF steps и не требует ручного Terminal happy path.
- `Запустить` корректно обрабатывает свободный и занятый порт.
- `Остановить` находит и останавливает серверы.
- Есть пошаговый сценарий clean/semi-clean Mac acceptance в docs.

### P0-002 Durable Job Queue

Status: READY.

Goal: заменить in-memory-only queue на локально устойчивую очередь, чтобы перезапуск web UI не делал долгие задачи невидимыми.

Scope:

- `app/src/voice_recognizer/web.py`
- новая локальная storage helper/module, если нужен
- tests/smokes в `.agents/` или docs

Acceptance:

- Jobs сохраняются на диск в local-only runtime path.
- После перезапуска сервера UI показывает queued/running/done/failed/canceled историю.
- Orphan running jobs после restart помечаются понятным статусом, без ложного `running`.
- Cancel/delete controls продолжают работать.
- Generated outputs не попадают в git.

### P0-003 Long-File Resume And Progress

Status: READY.

Goal: превратить "ASR chunking работает" в полноценную модель resume/progress для длинных записей.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/web.py`
- docs/checks

Acceptance:

- Manifest отражает этапы: audio prepare, ASR chunks, diarization, merge, exports.
- Повторный запуск не пересчитывает готовые chunks/artifacts при совпадении options.
- UI показывает конкретный текущий chunk/stage, а не только coarse stage.
- Длинный файл >2 часов проходит без `Audio file too long`.
- Диаризация имеет понятный fallback/resume story или явно документированный лимит.

### P0-004 Batch Reliability

Status: READY.

Goal: сделать пакетную обработку безопасной для сценария "3 дня по 6 часов".

Scope:

- `app/src/voice_recognizer/web.py`
- queue/persistence из P0-002 или совместимый storage
- docs/user-scenarios.md

Acceptance:

- Пользователь выбирает subset файлов и ставит их в последовательную очередь.
- Видит прогресс по каждому файлу и общий итог.
- Может отменить один queued/running item без потери готовых результатов.
- После refresh/restart UI не теряет batch state.

### P0-005 Engine Registry And Model Profiles

Status: READY.

Goal: превратить поле "ASR-движок" из почти статического выбора в общий registry CLI/Web с реальными профилями.

Scope:

- `app/src/voice_recognizer/engines.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- `docs/local-models.md`
- `docs/external-projects.md`

Acceptance:

- CLI и Web читают один список engine profiles.
- Каждый engine имеет status: ready/missing/disabled/deferred и next step.
- GigaSTT/GigaAM v3 остается default.
- Whisper local profile выбран как следующий candidate или явно отложен с причиной.
- Handy/Wisper/LM Studio assets описаны как reusable/not reusable без догадок.

### P0-006 Speaker Quality Improvement Loop

Status: READY.

Goal: перейти от диагностики "разметка подозрительная" к улучшению качества диаризации.

Scope:

- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/gigastt.py`
- `docs/quality-benchmark-references.md`
- `docs/asr-benchmark/`
- optional CLI benchmark command

Acceptance:

- Есть benchmark на проблемных файлах/фрагментах: `Носников`, `Модуль 3, день 2`, короткая 2-speaker запись.
- Сравниваются варианты smoothing/aggressiveness и speaker constraints.
- В exports или diagnostic markdown помечаются short islands/uncertain speaker turns.
- Настройки не ухудшают очевидные короткие настоящие реплики без отдельного флага.

### P0-007 Local Smoke Suite

Status: READY.

Goal: получить быстрый набор проверок перед каждым крупным шагом без приватных аудио и без тяжелых моделей.

Scope:

- `app/src/voice_recognizer/`
- `app/scripts/`
- `.agents/`
- docs

Acceptance:

- Одна команда проверяет shell syntax, Python compile, key CLI help, web render JS syntax.
- Есть synthetic fixtures для manifest/result/speaker-quality без приватного аудио.
- Smoke suite не требует network и не пишет в git-tracked paths.

## Later Queue

### P1-008 Installable Folder Layout

Status: READY after P0-001.

Goal: отделить поставляемый продукт от dev workspace: `VoiceRecognizerLocal/app` + `user-data`.

Acceptance: launchers, paths, cache, Inbox, outputs and models work from product folder layout.

### P1-009 Result Maintenance UX

Status: READY after P0-002.

Goal: UI actions for refresh-quality, rerender exports, archive/delete result records without deleting source audio accidentally.

### P1-010 Speaker Memory Experiment

Status: DEFERRED until speaker workflow is stable.

Goal: allow user to name known voices and reuse labels across recordings.

### P1-011 Optional Whisper Backend

Status: DEFERRED until P0-005 registry is ready.

Goal: add a local Whisper profile only if it improves quality/cost for Russian or gives useful fallback.

## Deferred

- Self-host/Docker/cloud profile.
- Public GitHub packaging and landing.
- SwiftUI/macOS-native wrapper.
- Multi-user/auth/server access control.
