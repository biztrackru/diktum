# Handoff — UX implementation F3/F4

Дата: 2026-06-26.
Автор: Codex implementation track.

## Summary

Implemented portion 2 from `.agents/next-task-ux-implementation.md`: long-running jobs now show a coarse pipeline stage, elapsed time, start time and heartbeat; failed/offline states now show human-readable diagnostics with concrete next steps.

## Files Changed

- `app/src/voice_recognizer/web.py` - added progress/status UI, client-side stage inference from job logs, elapsed/start formatting, heartbeat extraction, and diagnostic mapping for common failures.
- `.agents/task-board.md` - marked F3/F4 implementation as delivered and recorded checks.
- `.agents/handoff-ux-f3-f4.md` - this handoff.

## Checks Run

- `.venv/bin/python -m compileall app/src` - pass.
- `node --check /tmp/voice-recognizer-f3.js` after extracting the rendered `<script>` from `http://127.0.0.1:8782/` - pass.
- Browser/IAB desktop 1280x720 - page loads, console clean, running 120-second job shows `ASR`, elapsed, start time, stage rail and heartbeat.
- Browser/IAB failed-job smoke - intentionally used invalid `device`; UI showed `Неподдерживаемое устройство обработки`, concrete next steps, and `role=alert`.
- Browser/IAB mobile 390x760 - no horizontal overflow, failed diagnostic remains readable, console clean.

## Not Checked

- A real multi-hour job was not run end to end in this pass. The UI uses the same job payload fields, so the main remaining risk is whether log signatures need tuning for rare backend messages.

## Risks

- Stage inference is heuristic and based on current log lines. If future engines log different strings, the stage may stay on an earlier step until mappings are extended.
- Error diagnostics are intentionally coarse. Unknown failures still fall back to a generic safe recovery card.

## Next Suggested Task

Implement portion 3 from `.agents/next-task-ux-implementation.md`: F15/F16 in `app/src/voice_recognizer/web.py` for disk-backed results from `outputs/**/*.manifest.json` and Inbox badges for already processed files. Coordinate before touching `cli.py`.
