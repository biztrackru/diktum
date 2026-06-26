# Task Board

Дата: 2026-06-26.

## Current Product Focus

Сделать нормальный локальный Mac-продукт до self-host и публичной публикации.

Definition of "normal local product":

- пользователь скачивает/получает папку или установщик;
- запускает понятный setup/launcher;
- setup проверяет Python/ffmpeg/модели/токены и сам объясняет, что делать;
- web UI открывается локально;
- можно загрузить аудио, запустить обработку, назвать спикеров и открыть результаты;
- проблемы показываются человеческим языком, не только traceback.

## Active Branches

- `main` - baseline.
- `codex/upload-files-queue` - upload UI and project coordination changes.

## Active Work

### Codex

Scope:

- `app/scripts/doctor_local_mac.sh`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/start_server.sh`
- `Проверить Voice Recognizer.command`
- minimal README/task-board updates for this doctor task

Goal:

- реализовать read-only doctor для локальной установки;
- ничего не устанавливать, не скачивать и не менять в пользовательских файлах;
- дать понятный отчет по Python, ffmpeg, моделям, `.env`, pyannote и портам.
- привести setup/start к единому дефолту `Inbox` с fallback на старый `inbox`.

### Claude Code

Status: DELIVERED (2026-06-26), ready for implementation handoff. UX/product track. Docs done; код (`web.py`) намеренно не тронут — реализация за implementation-агентом.

Deliverables: `docs/ux-audit.md` (F1–F16, вкл. персистентность/результаты + оценка S/M/L), `docs/ux/voice-recognizer-prototype.html` (эталон поведения; вид «Готовые» + бейдж «обработан → готово»), `docs/ux-acceptance-scenarios.md` (S1–S10 + матрица). Передача, приоритеты и Data contract — `.agents/handoff-ux-redesign.md`. Порядок реализации: 1) F1+F2, 2) F3+F4, 3) F15+F16 (библиотека результатов из `outputs/`), 4) F5–F8, полировка F9–F14.

Scope (write):

- `docs/ux-audit.md` (new)
- `docs/ux/voice-recognizer-prototype.html` (new)
- `docs/ux-acceptance-scenarios.md` (new)
- `.agents/handoff-ux-redesign.md` (new)
- this `### Claude Code` block in `.agents/task-board.md`

Goal:

- grounded UX-аудит фактического web UI (`app/src/voice_recognizer/web.py`) с severity / file:line / risk / fix;
- интерактивный self-contained прототип целевого интерфейса (vanilla HTML/CSS/JS под текущий стек, без сборки), пригодный для переноса в `web.py`;
- приёмочные UX-сценарии (Given/When/Then + ручные проверки), привязанные к `review-checklist.md` и `agent-redesign-proposal.md`.

Read-only (не редактирую): `app/src/voice_recognizer/web.py` — только источник для аудита; реализацию в коде отдаю implementation-агенту через handoff.

Не пересекается с активным scope Codex (`setup_local_mac.sh`, `*.command`, `implementation-plan.md`, `local-mac-product-plan.md`, `README.md`).

### Implementation

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 1 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation` block in `.agents/task-board.md`

Goal:

- F1: visible keyboard focus for `.btn`, `.segment`, `.file-row`, `.job-row`, `.link-chip`;
- F2: speaker-name inputs keep typed values, focus and caret during 2-second polling;
- keep diff small and do not touch pipeline or UX docs.

Checks:

- `.venv/bin/python -m compileall app/src`;
- Browser/IAB on `http://127.0.0.1:8782/`: page loads, console clean, F2 live job regression passes after 6.9s and two polling cycles, mobile 390px has no horizontal overflow;
- smoke job output was isolated to `outputs/ui-f2-smoke` and removed after verification.

### Implementation F3/F4

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 2 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F3/F4` block in `.agents/task-board.md`

Goal:

- F3: show coarse pipeline stage, elapsed time, start time and last meaningful log for queued/running jobs;
- F4: replace dead-end failed/offline messages with human-readable diagnostics and concrete next steps;
- keep the change local to the web UI; no pipeline or manifest changes.

Checks:

- `.venv/bin/python -m compileall app/src`;
- extracted rendered HTML script and ran `node --check /tmp/voice-recognizer-f3.js`;
- Browser/IAB on `http://127.0.0.1:8782/`: running job shows stage rail, elapsed/start and heartbeat; failed job shows diagnostic block with `role=alert`; desktop 1280px and mobile 390px have no horizontal overflow; console clean.

### Implementation F15/F16

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 3 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F15/F16` block in `.agents/task-board.md`

Goal:

- F15: add a disk-backed results library from `outputs/**/*.manifest.json`;
- F16: mark Inbox files that already have matching results and open those results from the UI;
- keep the change local to the web UI unless a manifest/pipeline blocker appears.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: 15 disk results found, 5 Inbox files marked processed;
- Chrome/Playwright on `http://127.0.0.1:8782/`: results library renders, Inbox processed badge opens a result, export link returns `200`, console clean, desktop/mobile no horizontal overflow.

### Implementation F5/F8

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 4 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F5/F8` block in `.agents/task-board.md`

Goal:

- F5: localize user-facing job/status labels;
- F6: add a test-fragment run mode with mm:ss parsing and presets;
- F7: show practical Inbox metadata such as duration, format and modified time;
- F8: group export files by user intent.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: Inbox files include duration/format/modified metadata;
- Chrome/Playwright on `http://127.0.0.1:8782/`: test-fragment mode and presets work, status labels are localized, export groups render, `mm:ss` parser works, console clean, desktop/mobile no horizontal overflow.

### Implementation F9/F14

Status: DELIVERED (2026-06-26), Codex. UX polish portion from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F9/F14` block in `.agents/task-board.md`

Goal:

- F9: reduce polling churn where it affects reading/focus, especially log scroll;
- F10: add polite status announcements and alert semantics for failures;
- F12: make workflow step labels reflect the current active stage instead of staying decorative;
- F13/F14: keep muted text readable and add restrained transitions with reduced-motion support.

Checks:

- `.venv/bin/python -m compileall app/src`;
- Chrome/Playwright on `http://127.0.0.1:8782/`: workflow moves from settings to export, status regions expose `aria-live=polite`, log no longer auto-scrolls when reading from top, console clean, desktop/mobile no horizontal overflow.

### Implementation F11

Status: DELIVERED (2026-06-26), Codex. UX implementation for controlled batch selection.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F11` block in `.agents/task-board.md`

Goal:

- F11: in batch mode, let the user include/exclude Inbox files before queueing;
- keep single-file and test-fragment selection unchanged;
- avoid uncontrolled heavy batch starts.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: batch mode exposes 5 checkboxes, `Все` selects all, `Ни одного` disables run, row click toggles one file and updates `4 из 5 выбрано`, console clean;
- mobile viewport 390px: no horizontal overflow.

### Implementation Disk Speaker Names

Status: DELIVERED (2026-06-26), Codex. Extend speaker labeling to disk-backed results.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Disk Speaker Names` block in `.agents/task-board.md`

Goal:

- allow applying speaker names to results opened from `outputs/**/*.manifest.json`;
- reuse existing ASR/diarization artifacts via CLI `--skip-existing`;
- refresh the result library and Inbox badges after applying names.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke: `_apply_result_speaker_names` updates a short disk result and logs `Using ASR JSON` + `Using diarization JSON`;
- in-app Browser on `http://127.0.0.1:8782/`: disk result opens, speaker name input applies via `POST /api/results/<id>/speaker-names`, label updates, console clean.

### Implementation Clip Validation

Status: DELIVERED (2026-06-26), Codex. Finish test-fragment validation UX.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Clip Validation` block in `.agents/task-board.md`

Goal:

- show readable test-fragment range after `mm:ss` parsing;
- validate selected clip against known Inbox duration;
- block run with a local message when the clip is outside the file.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: `2:00` shows `0:00-2:00`, `99:00` shows local out-of-file warning and disables run, `1:30` re-enables run, console clean;
- mobile viewport 390px: no horizontal overflow.

## Next Implementation Tasks

UX implementation (ready, from Claude UX track): полный бриф и copy-paste промпт — `.agents/next-task-ux-implementation.md`. Порядок порций: 1) F1+F2, 2) F3+F4, 3) F15+F16 (библиотека результатов из `outputs/`), 4) F5–F8, полировка F9–F14. Scope порций 1–2 — только `app/src/voice_recognizer/web.py`. Эталон — `docs/ux/voice-recognizer-prototype.html`, приёмка — `docs/ux-acceptance-scenarios.md`.

0. WhisperLiveKit research gate:
   - read `docs/external-projects.md` section `QuentinFuxa/WhisperLiveKit`;
   - decide whether to borrow model manager, doctor, benchmark, optional backend profile ideas;
   - do not add live WebSocket, Docker, translation, chrome extension, or multi-user features to the local Mac product yet;
   - write findings to `.agents/whisperlivekit-research.md` before implementing setup/engine registry changes.

1. Local setup doctor:
   - detect Python version;
   - detect ffmpeg/ffprobe;
   - detect `.venv`;
   - detect GigaSTT binary and model files;
   - detect HF token presence without printing it;
   - show clear next actions.
   - status: read-only doctor script exists and passes local smoke check.

2. Local setup launcher:
   - double-clickable setup `.command`;
   - creates `.venv`;
   - installs dependencies;
   - runs model setup or explains manual model download;
   - ends with "Start Voice Recognizer".
   - status: first launcher exists as `Настроить Voice Recognizer.command`.

3. UI upload completion:
   - keep uploaded file selected;
   - add duration metadata once probing is fast enough;
   - support checked subset batch mode.

4. Long task UX:
   - stage labels;
   - elapsed time;
   - last successful artifact;
   - retry/resume language.

5. Speaker workflow:
   - robust sample playback;
   - stable name inputs during polling;
   - per-file speaker count and speaker names.

## Coordination Rules

- Claim one task and one write scope before editing.
- Do not edit files listed under another active owner.
- Commit small, thematic changes.
- Review before merging to `main`.
- If a task requires touching shared files like `README.md`, mention it in the handoff.
