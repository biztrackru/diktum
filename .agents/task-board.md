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
