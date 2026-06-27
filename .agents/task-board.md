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

### Claude Code — задача 2: бенчмарк качества vs референс

Status: DELIVERED (2026-06-27). Analysis-only, код не тронут.

Что: сравнение нашей ASR+диаризации против референсного сервиса (`references/*.docx`) на 4 одинаковых файлах (Модуль 3 ×3, Носников), наши прогоны — `outputs/pipeline/`.

Итог (кратко): ASR по полноте/скорости на уровне референса или выше (слов столько же или больше, покрытие 100%, RTF≈0.03); главный разрыв ASR — нет пунктуации/заглавных/«ё» и теряются термины/имена. Диаризация: на истинно 2-спикерных файлах совпадает (2=2); на многоголосых наши числа занижены, **но это в основном артефакт настроек** (Носников запущен с `num_speakers=2`, день2 упёрся в `max_speakers=8` при референсных 5 и 21). Сырых turn'ов pyannote достаточно (1712/2295) — проблема в кластеризации/лимитах, не в сегментации.

Deliverable: `docs/quality-benchmark-references.md`. Рекомендации завязаны на этапы 4/5 `implementation-plan.md` и на дефолты диаризации в `web.py`.

Read-only: `references/`, `outputs/pipeline/`, `app/src/...` — только источники. Не пересекается со scope Codex.

### Claude Code — задача 3: ASR-модели и пунктуация/регистр

Status: DELIVERED (2026-06-27). Analysis + ресёрч, код не тронут.

Находка (важно для implementation): мы уже возим модель пунктуации RUPunct (`.models/gigastt/punct/rupunct_small_int8.onnx`) и передаём `--punct-model-dir`, но в выводе пунктуации/регистра/«ё» нет вообще (эмпирически: punct≈0/100w, caps≈0%, ё=0 против ~31 / 62–99% / 19–30 у референса). Все читаемые тексты собираются из сырых пословных токенов (`gigastt.py:263`), пунктуированный путь не используется.

Варианты фикса: (B) заставить бинарь применять punct — проверить `gigastt transcribe --help` на Mac; (A) применить вшитый RUPunct пост-шагом в Python; (C) GigaAM v3 **e2e** (нативная пунктуация); (D) Whisper large-v3. Тесты других моделей и auto-диаризацию из песочницы запустить нельзя (Linux vs macOS-бинарь, сеть pip/HF закрыта) — протокол и скрипты для Mac в отчёте.

Deliverables: `docs/asr-model-research.md`, `docs/asr-benchmark/score.py` (dependency-free скорер читабельности — гонять при смене модели). Привязка: этап 4/5.

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

### Implementation Result Preview Tabs

Status: DELIVERED (2026-06-26), Codex. Add result tabs and transcript preview.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Result Preview Tabs` block in `.agents/task-board.md`

Goal:

- split result panel into Overview/Text/Speakers/Files tabs;
- load transcript preview from existing export files without changing pipeline;
- keep speaker naming and export links working inside the new structure.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: disk result opens with Text tab by default, transcript preview loads from export file, Speakers tab contains audio/name/apply controls, Files tab keeps grouped exports, Overview tab shows metadata, console clean;
- mobile viewport 390px: result tabs render after opening a result, no horizontal overflow.

### Implementation Privacy Signal

Status: DELIVERED (2026-06-26), Codex. Make local/private mode explicit in the UI.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Privacy Signal` block in `.agents/task-board.md`

Goal:

- show that the app is running locally on `127.0.0.1`;
- state that audio and transcripts stay on this Mac unless the user explicitly chooses another engine/profile later;
- keep the top bar compact on mobile.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: top bar shows `Локально · 127.0.0.1:8782` and `Аудио и тексты остаются на этом Mac`;
- mobile viewport 390px: no horizontal overflow.

### Implementation Source Freshness

Status: DELIVERED (2026-06-27), Codex. Warn when disk-backed results no longer match the source audio.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Source Freshness` block in `.agents/task-board.md`

Goal:

- detect whether a result source file is fresh, changed after processing, missing, or not safely checkable;
- surface changed/missing source state in Inbox badges, the results list, and result overview;
- avoid breaking result listing when a manifest source is absent or outside the project.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: 15 disk results expose `source_status=fresh`, Inbox summaries inherit source freshness;
- temporary manifest smoke: source mtime newer than manifest returns `source_status=changed`;
- in-app Browser on `http://127.0.0.1:8782/`: page loads, console clean, 15 results render, result overview shows `Исходник — исходник свежий`;
- mobile viewport 390px: no horizontal overflow, Inbox freshness tooltips remain readable.

### Implementation Rerun Stale Result

Status: DELIVERED (2026-06-27), Codex. Let users refresh a stale disk-backed result from the UI.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Rerun Stale Result` block in `.agents/task-board.md`

Goal:

- add a safe rerun endpoint for `outputs/**/*.manifest.json` results;
- reuse the result source, clip window, ASR engine, output directory and existing speaker names where available;
- show an update action for changed-source results without starting expensive work accidentally.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke with `PYTHONPATH=app/src`: `_create_result_rerun_job` preserves source/output/clip, adds `--overwrite`, and keeps existing speaker names;
- in-app Browser on `http://127.0.0.1:8782/` with a temporary ignored stale manifest: page loads, console clean, stale result shows `обновить`, opening it shows active `Обновить результат`;
- mobile viewport 390px: no horizontal overflow and rerun action remains visible;
- temporary smoke source/result files removed and test server stopped.

### Implementation Engine Readiness Signal

Status: DELIVERED (2026-06-27), Codex. Show whether the local GigaSTT/GigaAM engine is actually ready.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Engine Readiness Signal` block in `.agents/task-board.md`

Goal:

- check local GigaSTT binary and GigaAM model files without network calls;
- show a compact ready/missing status next to ASR engine selection;
- keep unavailable Handy engines disabled until their runtime backends are integrated.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke with `PYTHONPATH=app/src`: `_asr_runtime_status` returns `GigaSTT готов` on this Mac;
- in-app Browser on `http://127.0.0.1:8782/`: ASR settings show `GigaSTT готов` / `GigaAM v3 найден локально`, console clean;
- mobile viewport 390px: no horizontal overflow.

### Implementation Manifest Metadata Contract

Status: DELIVERED (2026-06-27), Codex. Enrich new manifests with explicit run metadata.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation Manifest Metadata Contract` block in `.agents/task-board.md`

Goal:

- write explicit clip, device, timing and source file metadata to new manifests;
- keep old manifests readable via filename/stat fallbacks;
- use explicit manifest fields for disk-result preview, speaker renaming and rerun where available.

Checks:

- `.venv/bin/python -m compileall app/src`;
- manifest v2 smoke: `_write_manifest` stores `clip_start`, `clip_duration`, `device`, source size/mtime, created/completed timestamps and speaker constraints;
- web payload smoke: `_result_payload` reads explicit manifest fields and `_create_result_rerun_job` preserves clip/device/speaker constraints;
- source freshness smoke: unchanged v2 source is `fresh`, size-changed source becomes `changed`;
- legacy manifest smoke: old filename-based clip fallback still returns `5.0 / 10.0`.

### Implementation Result Overview Metadata

Status: DELIVERED (2026-06-27), Codex. Surface manifest run metadata in the result overview.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Result Overview Metadata` block in `.agents/task-board.md`

Goal:

- show processing date, clip window and recognized audio duration in the overview tab;
- use existing formatting helpers and keep old manifests readable;
- verify desktop/mobile rendering with the in-app browser.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: opened a result, switched to `Обзор`, saw `Обработано`, `Окно`, `Распознано`, console clean;
- mobile viewport 390px: same overview fields render, no horizontal overflow;
- test server stopped.

### Implementation Left/Middle Prototype Alignment

Status: DELIVERED (2026-06-27), Codex. Bring the Inbox and center workbench closer to Claude's UX prototype.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Left/Middle Prototype Alignment` block in `.agents/task-board.md`

Goal:

- make Inbox processed badges explicit click-through actions such as `обработан · готово →`;
- combine queue and disk results into one center `Работа` panel with `Очередь / Готовые` switching;
- keep result opening, queue state and existing APIs unchanged.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: queue view shows only jobs/queue badges, ready-results view shows 15 results/result badge, opening a ready result keeps `Готовые` active and renders the right column, console clean;
- mobile viewport 390px: Inbox badges, center switch and ready-results list render with no horizontal overflow;
- fixed hidden-state CSS so list/badge `hidden` is not overridden by component `display` rules.

### Implementation Quality Benchmark Follow-up

Status: DELIVERED (2026-06-27), Codex. Apply the highest-ROI fixes from Claude quality audit.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/config/speaker-counts.json`
- `docs/asr-benchmark/score.py`
- `docs/asr-model-research.md`
- this `### Implementation Quality Benchmark Follow-up` block in `.agents/task-board.md`

Goal:

- preserve GigaSTT punctuation/casing from JSON `text` in timestamped speaker segments;
- explicitly run GigaSTT with `--punctuation on --itn auto`;
- remove hidden low speaker ceilings from benchmark/problem files;
- make Claude's readability scorer usable with `--terms`.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- `gigastt transcribe` smoke on `Носников 0–30s`: punctuation/casing appears in JSON `text`;
- `PYTHONPATH=app/src` smoke: segment exports inherit punctuation/casing from a punctuated GigaSTT JSON;
- `docs/asr-benchmark/score.py` works with `--terms` before or after file arguments.

### Implementation Claude Audit Closure

Status: DELIVERED (2026-06-27), Codex. Turn Claude audit recommendations into explicit project status and glossary support.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/gigastt.py`
- `app/config/hotwords.txt`
- `docs/claude-audit-closure.md`
- `docs/asr-model-research.md`
- this `### Implementation Claude Audit Closure` block in `.agents/task-board.md`

Goal:

- answer whether all Claude findings/recommendations are found and closed;
- add optional GigaSTT hotwords support through `app/config/hotwords.txt`;
- document which quality recommendations are closed, partial, ready-for-heavy-run, or deferred.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- CLI help exposes `--hotwords-file` and `--hotwords-default`;
- smoke run confirms `app/config/hotwords.txt` is resolved and passed to GigaSTT;
- closure document lists UX F1-F16 as closed and quality/ASR residual work explicitly.

### Implementation Stale Artifact Invalidation

Status: DELIVERED (2026-06-27), Codex. Prevent old ASR/diarization intermediates from masking quality fixes.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/cli.py`
- `docs/claude-audit-closure.md`
- this `### Implementation Stale Artifact Invalidation` block in `.agents/task-board.md`

Goal:

- explain and fix why UI reruns could still show no punctuation;
- annotate new GigaSTT JSON with punctuation/ITN/hotwords metadata;
- annotate new pyannote JSON with model/device/speaker constraint metadata;
- refresh stale intermediate JSON automatically when current options do not match.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- stale existing `outputs/pipeline/*gigastt.json` and `*.pyannote.json` return metadata mismatch;
- fresh 5s `transcribe-gigastt` smoke writes current ASR metadata and remains punctuated;
- synthetic diarization metadata smoke distinguishes current `2-12` from stale exact `2`.

### Implementation Short ASR Chunks For Punctuation

Status: DELIVERED (2026-06-27), Codex. Fix GigaSTT punctuation/casing loss on long ASR chunks.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `README.md`
- `docs/diarization-baseline.md`
- `docs/claude-audit-closure.md`
- this `### Implementation Short ASR Chunks For Punctuation` block in `.agents/task-board.md`

Goal:

- stop using 3600-second ASR chunks as the default, because GigaSTT punctuation disappears on long chunks;
- default to 600-second ASR chunks for files longer than 10 minutes;
- include chunking parameters in ASR JSON metadata version 2;
- include chunk start/duration in artifact file names so old hour-long chunk cache cannot be reused as a shorter chunk.

Checks:

- local smoke on `Модуль 3, день 2` showed punctuation/casing works at 60/180/300/600s and fails at 900s;
- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- ASR chunk smoke produced `part-001_0s_600s` artifacts and combined punctuation;
- old ASR JSON version 1 returns metadata mismatch.

### Implementation ASR Quality Diagnostics

Status: DELIVERED (2026-06-27), Codex. Surface ASR readability regressions in manifests and UI.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation ASR Quality Diagnostics` block in `.agents/task-board.md`

Goal:

- compute lightweight ASR quality metrics after loading GigaSTT output;
- write `asr_quality` into each manifest;
- show `Качество ASR` in the result overview;
- flag future low-punctuation/low-casing regressions without requiring manual inspection of long transcripts.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- manifest smoke includes `asr_quality.status=ok` for the refreshed long results;
- UI payload exposes `asr_quality` for disk results.

### Implementation Queue Cancellation

Status: DELIVERED (2026-06-27), Codex. Add safe stop/remove controls for accidental long jobs.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Queue Cancellation` block in `.agents/task-board.md`

Goal:

- allow queued jobs to be removed before they start;
- allow running jobs to request cancellation and terminate the child process group;
- keep canceled jobs visible with explicit `canceled` status until the user removes them;
- allow completed/failed/canceled jobs to be removed from the in-memory job list without deleting output files.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- running-cancel API smoke: `running -> canceling -> canceled`, child return code `-15`;
- queued-cancel API smoke: `queued -> canceled` before start;
- delete API smoke removes done/canceled jobs from `/api/jobs`;
- generated HTML contains cancel/delete controls and extracted JS passes `node --check`.

### Implementation Speaker Quality Diagnostics

Status: DELIVERED (2026-06-27), Codex. Surface speaker-turn fragmentation before changing diarization heuristics.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation Speaker Quality Diagnostics` block in `.agents/task-board.md`

Goal:

- compute lightweight metrics for speaker switchiness and very short speaker turns;
- write `speaker_quality` into manifests;
- show `Качество спикеров` in the result overview;
- make phrase-splitting problems visible on long recordings without manual transcript inspection.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- synthetic speaker-island smoke returns `warning` with `short_speaker_islands`;
- existing result JSON smoke flags `Носников` and `Модуль 3, день 2` as `warning`;
- generated HTML contains `Качество спикеров` and extracted JS passes `node --check`;
- in-app Browser on `http://127.0.0.1:8790/`: page loads, console clean, disk result overview shows `Качество спикеров`; legacy manifests without `speaker_quality` show `-` until rerendered.

### Implementation Quality Manifest Refresh

Status: DELIVERED (2026-06-27), Codex. Backfill quality diagnostics for existing manifests without rerunning ASR or diarization.

Scope:

- `app/src/voice_recognizer/cli.py`
- `README.md`
- this `### Implementation Quality Manifest Refresh` block in `.agents/task-board.md`

Goal:

- add a CLI command that reads existing `*.manifest.json`, `*.gigastt.json` and `*.pyannote.json`;
- refresh `asr_quality` and `speaker_quality` fields only;
- avoid launching GigaSTT, pyannote or touching audio files;
- make old UI result cards show speaker quality after a lightweight backfill.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- CLI help exposes `refresh-quality`;
- `/tmp` manifest smoke updates `asr_quality`, `speaker_quality`, `quality_refreshed_at` and honors `--force --no-smooth-speakers`;
- `outputs/pipeline` backfill updated existing `Модуль 3, день 2` and `Носников` manifests without launching ASR/diarization;
- in-app Browser on `http://127.0.0.1:8790/`: refreshed `Модуль 3, день 2` overview shows `Качество спикеров: проверить · коротких 19.6% · смен 2.5/мин · островков 42`, console clean.

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
