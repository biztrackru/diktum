# Claude Prototype Integration Subtasks

Дата: 2026-06-27.
Автор: Codex.
Тип: UX/product triage, без изменений `web.py`.

## Цель

Проверить, насколько UI-прототип Claude из `docs/ux/voice-recognizer-prototype.html` реально перенесен в текущий `app/src/voice_recognizer/web.py`, и разложить оставшиеся куски на подзадачи.

Это не заменяет текущий P0 порядок в `.agents/product-backlog.md`. Подзадачи ниже привязаны к уже существующим P0/P1 задачам, чтобы implementation-агенты могли брать их как narrowed scope.

## Проверка

Что проверено:

- исходники: `docs/ux/voice-recognizer-prototype.html`, `docs/ux-audit.md`, `docs/ux-acceptance-scenarios.md`, `.agents/handoff-ux-redesign.md`, `app/src/voice_recognizer/web.py`;
- live UI: `http://127.0.0.1:8791/`;
- desktop viewport: default in-app browser viewport;
- mobile viewport: `390x844`;
- flow: load app -> switch to `Готовые` -> open disk-backed result -> switch to `Спикеры` -> type speaker name and wait through polling.

Evidence:

- page identity: `Voice Recognizer` at `http://127.0.0.1:8791/`;
- console health: no browser `warn`/`error` logs during checked flows;
- desktop: 5 Inbox files, 15 disk-backed results, 5 processed Inbox badges, no horizontal overflow;
- mobile `390x844`: 5 Inbox rows, run modes visible, `Очередь/Готовые` visible, no horizontal overflow;
- disk result opens from `Готовые`, result tabs render, transcript preview loads, export groups render;
- F2 regression passes: typed `Тестовое имя Codex`, waited through a polling cycle, value/focus/caret stayed in the speaker-name input.

Limitations:

- The in-app Browser blocks direct `file://` navigation, so the prototype HTML itself was not opened as a rendered page in Browser. Reference comparison used source inspection of the prototype plus live rendering of the integrated UI.
- No real heavy ASR/diarization job was started during this triage.
- No private audio or generated output was modified.

## Integration Status

| Area | Status | Notes |
| --- | --- | --- |
| F1 focus-visible | Done | Focus rules exist for main controls. A human keyboard Tab pass is still useful before release. |
| F2 speaker input vs polling | Verified done | Live browser regression passed on a disk-backed result. |
| F3 stages/elapsed/heartbeat | Partial | Coarse stage inference from logs exists. Structured stage/chunk progress and resume belong to `P0-003`. |
| F4 error recovery | Partial | Failed jobs and offline state get diagnostic cards. Launch/upload/results read errors can still fall back to raw log text. |
| F5 localized statuses | Done | Queue and result statuses are Russian in user-facing UI. |
| F6 test fragment controls | Done | `Тест-фрагмент`, presets, `mm:ss`, and clip validation exist. |
| F7 Inbox metadata | Done | Duration, format, modified time, processed badges are visible. |
| F8 export grouping | Mostly done | Groups exist for text/read/edit/diagnostics. DOCX-specific group waits for DOCX output. |
| F9 polling/log churn | Partial | Log auto-scroll is guarded, but queue/result lists still rebuild with listener rewiring. The raw journal remains prominent. |
| F10 aria-live/alerts | Partial | Main status regions and diagnostic alerts exist. Needs a systematic accessibility pass for upload/form errors and success announcements. |
| F11 batch subset | Done | Batch mode has checkboxes and all/none controls. |
| F12 workflow stepper | Superseded | First-screen workflow strip was removed as acceptance-test noise; structured long-file progress still belongs to `P0-003`. |
| F13 contrast/status meaning | Done enough | Current UI uses text labels with status colors; keep checking when adding new muted text. |
| F14 motion polish | Done enough | Transitions and reduced-motion handling exist. |
| F15 disk results | Done | `/api/results` reads `outputs/**/*.manifest.json`; results survive server restart. |
| F16 Inbox result link | Done | Processed badges open disk-backed results. |

## Subtasks

### UX-P0-008 Launch UI Cleanup

Status: DELIVERED (2026-06-28).

Parent backlog: `P0-001 Mac Install Acceptance`, `P0-007 Local Smoke Suite`.

Problem:

- Spouse-Mac acceptance showed two bits of first-screen UI noise:
  - `Имена спикеров` in launch settings asks the user to name unknown speaker IDs before processing;
  - the top workflow strip `1 Inbox / 2 Настройки / 3 Очередь / 4 Спикеры / 5 Экспорт` reads like accidental debug/navigation text rather than useful guidance.

Scope:

- `app/src/voice_recognizer/web.py`

Acceptance:

- Delivered: launch settings no longer show `Имена спикеров`.
- Delivered: speaker naming remains available after processing in the speaker/result workspace.
- Delivered: top workflow strip is removed.
- Delivered: job launch no longer depends on a start-form speaker-name field.

### UX-P0-001 Inline Launch And API Error Recovery

Status: DELIVERED (2026-06-27).

Parent backlog: `P0-001 Mac Install Acceptance`, `P0-007 Local Smoke Suite`.

Problem:

- Prototype expects errors to become actionable UI states.
- Current failed/offline jobs do this, but some foreground actions still write raw `String(error)` into the journal: create job, upload, `loadResults`, result rerun/apply-name failures.

Scope:

- `app/src/voice_recognizer/web.py`
- optional smoke fixture in `.agents/` or docs

Acceptance:

- Delivered: `/api/jobs` validation errors, upload errors, unavailable `outputs`, and apply/rerun failures render a human-readable diagnosis or field-level message.
- Delivered: form state and selected file are preserved after foreground errors.
- Delivered: raw technical detail remains accessible in the journal, but is not the only user-facing message.
- Delivered: browser smoke covered a synthetic POST validation failure and an offline/read failure.

Delivery notes:

- `web.py` now uses a shared `showForegroundProblem(...)` helper for foreground UI failures.
- Confirmed validation case: `output_dir` outside `outputs/` shows `Папка результатов вне outputs`, keeps source/form values, creates no job.
- Confirmed offline case: after stopping the server, polling shows `Сервер не отвечает` with next steps and keeps technical `Failed to fetch` in the journal.

### UX-P0-002 Compact Journal And Polling Efficiency

Status: DELIVERED (2026-06-27).

Parent backlog: `P0-003 Long-File Resume And Progress`, `P0-007 Local Smoke Suite`.

Problem:

- Prototype treats raw log as secondary/collapsible.
- Current UI improved auto-scroll, but still gives the journal a large always-visible panel and rebuilds queue/result rows with listeners during polling.

Scope:

- `app/src/voice_recognizer/web.py`

Acceptance:

- Delivered: active job/result shows compact status/stage/elapsed/heartbeat first; full raw log is behind a collapsible details block.
- Delivered: raw log scroll position is preserved when reading from the middle/top during updates.
- Delivered: queue/result central lists use delegated click handling plus signature-based HTML patching.
- Delivered: Chrome/CDP smoke confirmed no horizontal overflow on desktop `1280x900` and mobile `390x844`.

Delivery notes:

- `web.py` now renders `#log-summary` above `#raw-log-details`, with raw line count and compact recent pipeline state.
- `setLogText(...)` preserves raw log scroll when the user is not near the bottom.
- `jobsNode` and `resultsList` no longer reattach row listeners after every polling refresh.

### UX-P0-003 Structured Long-File Progress In UI

Parent backlog: `P0-003 Long-File Resume And Progress`.

Problem:

- Claude prototype's stage rail is now present, but it is still inferred from free-form logs.
- The product needs real long-file resume/progress: stages, chunks, partial artifacts, and restart-safe state.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/web.py`

Acceptance:

- Manifest records structured stage/chunk state: audio prepare, ASR chunks, diarization, merge, exports.
- UI shows concrete stage and `chunk N/M` when available.
- Re-run/resume skips completed matching chunks/artifacts.
- If a long run fails, UI distinguishes partial progress from total failure.

### UX-P0-004 Batch Session Summary

Parent backlog: `P0-004 Batch Reliability`.

Problem:

- Prototype covers subset selection; current UI implements that.
- The remaining gap is the "3 days by 6 hours" operator view: batch-level state, final report, filters, and quick access to ready results.

Scope:

- `app/src/voice_recognizer/web.py`
- queue/storage from `P0-002` when available
- `docs/user-scenarios.md`

Acceptance:

- A batch run has a visible grouped summary: selected, queued, running, done, failed, canceled, elapsed, next file.
- User can filter queue by `Все / Выполняется / Ошибки / Готовые`.
- User can open all ready results from the batch or jump through ready results without hunting in `outputs/`.
- Batch state survives refresh/restart after `P0-002`.

### UX-P0-005 Engine Profile UX Completion

Parent backlog: `P0-005 Engine Registry And Model Profiles`.

Problem:

- The UI has a readiness signal for GigaSTT/GigaAM, but the prototype/product docs expect model choices to communicate availability, next steps, and privacy impact.

Scope:

- `app/src/voice_recognizer/engines.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- `docs/local-models.md`

Acceptance:

- CLI and Web share one engine registry.
- Each engine/profile has `ready/missing/disabled/deferred` plus a user-facing next step.
- Unavailable engines do not look like ordinary runnable options.
- Any future external/API profile shows an explicit privacy warning before run.

### UX-P0-006 Speaker Workspace Details

Parent backlog: `P0-006 Speaker Quality Improvement Loop`, later `P1-010 Speaker Memory Experiment`.

Problem:

- Current speaker tab supports samples and names.
- Prototype/proposal expects the speaker area to also help judge quality: stable colors, first appearance, example line, turn counts, uncertainty/island warnings.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/web.py`

Acceptance:

- Speaker tab shows per-speaker turn count, first appearance, and one representative utterance.
- Transcript preview and speaker tab share stable speaker colors.
- Short-island/uncertain speaker diagnostics link from overview to affected speakers/turns.
- Future multiple samples per speaker have a UI affordance without changing the basic naming flow.

### UX-P1-001 Text Preview Search And Result Maintenance

Parent backlog: `P1-009 Result Maintenance UX`.

Problem:

- The result tabs and transcript preview are integrated.
- Remaining maintenance UX from the proposal is search, rerender/refresh-quality, archive/delete, and safer result housekeeping.

Scope:

- `app/src/voice_recognizer/web.py`
- optional CLI endpoints for refresh/rerender actions

Acceptance:

- Text tab supports local search within loaded preview.
- UI exposes `refresh-quality` and rerender exports without rerunning ASR/diarization.
- Archive/delete result actions distinguish "remove UI record" from "delete generated files" and never delete source audio accidentally.
- Missing/partial result files show a recovery action instead of only an empty state.

### UX-P0-007 Prototype Acceptance Smoke

Parent backlog: `P0-007 Local Smoke Suite`.

Problem:

- UX F1-F16 are implemented enough, but acceptance is still mostly manual.
- Future changes to `web.py` can regress the prototype integration quietly.

Scope:

- `.agents/`
- `app/src/voice_recognizer/`
- optional docs

Acceptance:

- One local command validates shell syntax, Python compile, rendered HTML JS syntax, and core UI contracts.
- Synthetic fixtures cover Inbox metadata, disk results, processed badges, result tabs, quality diagnostics, and speaker-name draft preservation without private audio.
- Browser/manual checklist remains available, but the smoke suite catches the common regressions automatically.

## Not Subtasks

Do not spend implementation time on these unless the user explicitly asks:

- pixel-perfect visual match with the Claude prototype;
- copying the prototype footer mapping table into the product UI;
- loading IBM Plex fonts from CDN in the local-first product;
- decorative prototype-only waveforms or animations.

## Recommended Order

Keep the current product P0 order. For UI-specific follow-up, the highest leverage sequence is:

1. `UX-P0-007 Prototype Acceptance Smoke` alongside `P0-007`, so future UI work has a quick guardrail.
2. `UX-P0-003 Structured Long-File Progress In UI`, with `P0-003`.
3. `UX-P0-004 Batch Session Summary`, after durable queue work starts.
4. `UX-P0-006 Speaker Workspace Details`, when quality-loop work starts.
