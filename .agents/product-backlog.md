# Product Backlog

Дата актуализации: 2026-06-29.

Этот файл - источник правды для следующих задач Codex, Claude Code и review-агентов. `.agents/task-board.md` остается журналом выполненных delivery-блоков и местом для активного claim, но приоритеты брать отсюда.

## Product North Star

Ориентир текущего этапа: обычный пользователь Mac получает папку/пакет Voice Recognizer, запускает setup и затем обрабатывает длинные диктофонные записи локально без помощи разработчика и без Terminal.

Self-host, публичный GitHub, внешний лендинг и SwiftUI/native wrapper отложены до завершения локального продукта.

## Что уже реально сделано

- Локальный Python/web pipeline с GigaSTT/GigaAM v3 RNNT и pyannote diarization.
- ASR chunking для файлов длиннее лимита GigaSTT; дефолт 600 секунд для сохранения пунктуации.
- Web UI: Inbox, upload, queue/results views, batch subset selection, result tabs, exports, speaker samples/names, disk results from `outputs/`.
- Start/stop/setup/doctor `.command` и shell helpers существуют.
- Очередь умеет отменять queued/running jobs, удалять завершенные jobs из UI и сохранять job history в `.cache/jobs/web_jobs.json` между перезапусками.
- ASR/speaker quality diagnostics пишутся в manifest и показываются в UI.
- `refresh-quality` backfill обновляет старые manifest без повторного ASR/diarization.
- Claude UX F1-F16 в основном реализованы в текущем web UI.
- Интеграция Claude UI-прототипа проверена отдельным UX/product pass; подзадачи записаны в `.agents/claude-prototype-integration-subtasks.md`.
- Spouse-Mac acceptance пройден: установка на внешнем Mac завершилась без ошибок, тестовый файл распознан, имена спикеров применились, артефакты прошли ручную проверку качества.
- Local smoke suite добавлен: одна команда проверяет shell syntax, Python compile, CLI help, synthetic quality fixtures, manifest/result payload и web JS syntax без приватных аудио и тяжелых моделей.

## Главные недоделки из диалогов

- Нет installable/update-safe layout, где код приложения отделен от пользовательских данных и runtime cache.
- Нет release channel/update mechanism: актуальную версию нельзя проверить/скачать из самого продукта.
- Очередь получила disk-backed history; полноценный resume по этапам/chunks остается в `P0-003`.
- Long-file story закрыта для ASR chunking, но не закрыта как полноценный resume/progress pipeline по этапам и chunks.
- Batch UX есть, но нуждается в надежной job persistence, resume и итоговом отчете по пачке.
- Есть мелкие UX-замечания из spouse-Mac теста: поле `Имена спикеров` в настройках запуска преждевременно, верхний workflow stepper выглядит как шум.
- Выбор движков в UI пока по сути один рабочий backend: GigaSTT/GigaAM v3. Whisper/Handy/Wisper/LM Studio не интегрированы как реальные engine profiles; local Whisper inventory уже описывает MacWhisper/WhisperKit и Handy `ggml` как отдельных кандидатов.
- Итоговый текст иногда теряет смысл из-за ASR-ошибок, плохой пунктуации/регистра, склеек слов и разрывов одной фразы между спикерами; диагностика есть, но semantic repair и сравнение raw/edited результата не реализованы.
- Диаризация получила диагностику, но не получила системный quality-improvement loop: сравнение конфигураций, улучшение speaker-islands, overlap/uncertain regions и приемочный benchmark.
- Speaker labeling работает в рамках результата, но speaker memory / повторное узнавание людей по голосу отложено.

## Claude Prototype Integration Subtasks

Детальный статус и narrowed scopes: `.agents/claude-prototype-integration-subtasks.md`.

Эти подзадачи не меняют текущий P0 порядок, а дробят недоделанные UI-кусочки внутри существующих P0/P1:

- `UX-P0-001 Inline Launch And API Error Recovery` -> `P0-001`, `P0-007`.
- `UX-P0-002 Compact Journal And Polling Efficiency` -> `P0-003`, `P0-007`.
- `UX-P0-003 Structured Long-File Progress In UI` -> `P0-003`.
- `UX-P0-004 Batch Session Summary` -> `P0-004`.
- `UX-P0-005 Engine Profile UX Completion` -> `P0-005`.
- `UX-P0-006 Speaker Workspace Details` -> `P0-006`.
- `UX-P1-001 Text Preview Search And Result Maintenance` -> `P1-009`.
- `UX-P0-007 Prototype Acceptance Smoke` -> `P0-007`.
- `UX-P0-008 Launch UI Cleanup` -> `P0-001`, `P0-007`.

## Task Status Model

- `READY` - можно брать в работу сейчас.
- `CLAIMED` - агент взял задачу; claim обязан быть отражен в `.agents/task-board.md`.
- `BLOCKED` - нужен пользовательский ввод, внешний доступ или решение по продукту.
- `DELIVERED` - код/документация сделаны, проверки записаны в `.agents/task-board.md`.
- `DEFERRED` - осознанно отложено.

## Ready Queue

### SEC-P0-001 Security Hardening Review Fixes

Status: DELIVERED (2026-06-28).

Parent backlog: `P0-001 Mac Install Acceptance`, `P0-007 Local Smoke Suite`.

Goal: проверить hardening-ветку Клода и закрыть найденные review-регрессии до merge.

Scope:

- `app/src/voice_recognizer/web.py`
- `app/src/voice_recognizer/multipart.py`
- `tests/`
- `docs/security-hardening-review.md`
- `.agents/task-board.md`

Acceptance:

- Multipart upload не оставляет частичные файлы после malformed/oversized request.
- `/outputs/` full and range responses stream file bytes without reading a whole large range into memory.
- JSON endpoints reject non-JSON request bodies consistently.
- Security tests pass.

### UX-P0-008 Launch UI Cleanup

Status: DELIVERED (2026-06-28).

Parent backlog: `P0-001 Mac Install Acceptance`, `P0-007 Local Smoke Suite`.

Goal: убрать UX-шум из первого экрана после успешного spouse-Mac acceptance.

Scope:

- `app/src/voice_recognizer/web.py`
- `.agents/claude-prototype-integration-subtasks.md`
- `.agents/task-board.md`

Acceptance:

- Поле `Имена спикеров` удалено из настроек запуска; именование остается после обработки во вкладке/области спикеров.
- Верхняя строка workflow `1 Inbox / 2 Настройки / ...` удалена или скрыта как лишний шум.
- Запуск задач продолжает работать без `speaker_names` в стартовой форме.
- Python compile и базовая проверка web module проходят.

### P0-001 Mac Install Acceptance

Status: DELIVERED for private trial. Keep only regressions/packaging polish here.

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

- Delivered: spouse-Mac setup прошел без ошибок.
- Delivered: тестовый файл распознан.
- Delivered: имена спикеров применились после результата.
- Delivered: артефакты прошли ручную проверку качества.
- Remaining polish/regressions track as separate tasks, not as blockers for private trial.

### P0-007 Local Smoke Suite

Status: DELIVERED (2026-06-29).

Goal: получить быстрый набор проверок перед каждым крупным шагом без приватных аудио и без тяжелых моделей.

Scope:

- `app/src/voice_recognizer/`
- `app/scripts/`
- `.agents/`
- docs

Acceptance:

- Delivered: `app/scripts/smoke_local.sh` проверяет shell syntax, Python compile, key CLI help, web render JS syntax.
- Delivered: `tests/test_local_smoke.py` содержит synthetic fixtures для ASR quality, speaker quality и manifest/result payload без приватного аудио.
- Delivered: smoke suite не запускает GigaSTT/pyannote, не требует network и пишет временные файлы только в temp.

### P0-010 Transcript Quality Repair And Postprocessing

Status: READY. Diagnostic and deterministic edited-export slices delivered on 2026-06-29; local LLM/targeted re-ASR remain open. Highest current quality priority; coordinate with `P0-005` and `P0-006`.

Goal: получить качественный итоговый текст, в котором raw ASR остается доступным, а отдельный edited/repair слой исправляет пунктуацию, регистр, очевидные ASR-искажения, разрывы фраз между соседними сегментами и подозрительные места без выдумывания нового содержания.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- `app/src/voice_recognizer/engines.py`
- new optional transcript repair helper/module
- `docs/transcript-quality-repair.md`
- synthetic fixtures and local-only private evaluation notes

Acceptance:

- Delivered first slice: raw transcript, manifest and raw engine JSON are not overwritten; `repair-quality` writes separate `*.repair.json`.
- Delivered first slice: pipeline detects suspicious spans from ASR/speaker diagnostics, broken casing, all-caps artifacts, very short fragments, punctuation anomalies and speaker-island boundaries.
- Delivered first edited slice: repaired text is exported separately as `*.edited.md`, `*.edited.txt`, `*.repair.json`; new `process` runs write edited exports too.
- Repair uses surrounding context and preserves timestamps/speaker attribution; uncertain edits are marked rather than silently accepted.
- Local LLM/text repair is optional and local-first, for example LM Studio OpenAI-compatible endpoint; no external text/audio call happens by default.
- Delivered first slice: UI result file links include sibling `*.repair.json`, `*.edited.md` and `*.edited.txt` when they exist.
- Delivered first UI slice: Text preview and primary Markdown link prefer edited exports; raw/clean files remain available in the Files tab.
- Delivered benchmark slice: `benchmark-quality` can compare selected problematic snippets against private reference text under ignored `.local-quality/` without committing transcripts, audio or outputs.
- Delivered candidate benchmark slice: `benchmark-quality --candidate name=path` can score local `.txt`, `.md`, `.docx`, `.srt` and `.vtt` outputs from Speech2Text/FluidAudio/FunASR/WhisperX/Whisper before any ensemble merge is attempted.
- Delivered research slice: MacWhisper/WhisperKit and Handy/whisper.cpp are documented as separate local Whisper candidates for the same benchmark loop.
- Delivered first Whisper experiment: Homebrew `whisper.cpp 1.9.1` with Handy `ggml-large-v3-q5_0.bin` ran on the first `Носников` reference window; CPU/BLAS build was slow and scored below current edited GigaSTT.
- Delivered Handy inspection slice: Handy's high-quality dictation path appears to be `gigaam-v3-e2e-ctc` ONNX with Silero VAD and CTC decoding, not the current GigaSTT split RNNT pipeline and not enabled LLM post-processing.
- Delivered Handy runtime spike: Handy `gigaam-v3-e2e-ctc` ONNX runs through clean `onnxruntime` preprocessing/CTC decode and produces punctuated text, but first fixed/pyannote-chunk candidates did not yet beat current edited GigaSTT on the private `Носников` reference.
- Documentation explains when to rerun ASR with shorter chunks/alternate engine versus when to use text repair.

### P0-008 Installable Layout And Update-Safe Data Split

Status: READY after `P0-010` or when packaging work is explicitly selected.

Goal: отделить обновляемый код от локальных пользовательских данных, чтобы будущий updater мог заменять приложение без риска для `.env`, `.venv`, `.models`, `Inbox`, `outputs`, `logs`.

Scope:

- `app/scripts/build_install_pack.sh`
- root `*.command`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/start_server.sh`
- `app/scripts/stop_server.sh`
- docs/install/update notes

Acceptance:

- Trial pack layout явно разделяет `app/` и user/runtime data.
- Поверхностное обновление заменяет только код/скрипты/docs, не трогая пользовательские данные.
- Старые trial folders имеют понятный migration/compat story.
- Setup/start/doctor работают из нового layout.

### P0-009 Release Channel And Manual Updater

Status: READY after `P0-008`.

Goal: дать пользователю способ проверить и скачать актуальную версию из продукта при наличии интернета.

Scope:

- release manifest format, например `version.json`
- updater script/command
- optional Web UI button/status
- docs/release-process

Acceptance:

- Приложение умеет проверить доступную версию и показать changelog.
- Скачанный zip проверяется по SHA-256 перед применением.
- Updater отказывается работать при running job.
- Обновление сохраняет `.env`, `.venv`, `.models`, `Inbox`, `outputs`, `logs`.
- Есть rollback/backup текущего `app/` на случай неудачи.
- Хостинг MVP может быть GitHub Releases/private HTTPS bucket; public notarized releases остаются отдельной будущей задачей.

### P0-002 Durable Job Queue

Status: DELIVERED (2026-06-29). JSON-backed local job store delivered; chunk-level resume remains `P0-003`.

Goal: заменить in-memory-only queue на локально устойчивую очередь, чтобы перезапуск web UI не делал долгие задачи невидимыми.

Scope:

- `app/src/voice_recognizer/web.py`
- новая локальная storage helper/module, если нужен
- tests/smokes в `.agents/` или docs

Acceptance:

- Delivered: jobs сохраняются на диск в local-only runtime path `.cache/jobs/web_jobs.json`.
- Delivered: после перезапуска сервера UI/API получают queued/done/failed/canceled историю из job store.
- Delivered: orphan `running`/`canceling` jobs после restart помечаются понятным статусом, без ложного `running`.
- Delivered: cancel/delete controls продолжают работать и обновляют job store.
- Delivered: generated outputs/job store остаются local-only и не попадают в git.

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
- Delivered research slice: Handy `ggml-large-v3-q5_0.bin` maps to future `whispercpp-handy`; MacWhisper `openai_whisper-large-v3-v20240930` maps to future `macwhisper-whisperkit`; `faster-whisper` requires separate CTranslate2 model download/convert.
- Delivered first runtime slice: `whisper-cli` is installed, but `whispercpp-handy` should not be default because the current Homebrew build has no GPU/Metal and did not improve the `Носников` quality benchmark.
- Delivered Handy inspection slice: Handy `giga-am-v3-int8/model.int8.onnx` maps to a future `handy-gigaam-v3-e2e-ctc` candidate; it needs a clean ONNX/e2e runtime and should not depend on private Handy app code.
- Delivered Handy runtime spike: `handy-gigaam-v3-e2e-ctc` can run without Handy runtime code via `onnxruntime`; next implementation is a real experimental engine profile with segment-level output, VAD/chunk stitching and benchmark gating.

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

## Later Queue

### P1-008 Installable Folder Layout

Status: PROMOTED to `P0-008 Installable Layout And Update-Safe Data Split`.

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
