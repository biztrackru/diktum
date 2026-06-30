# Handoff — UX implementation F1/F2

Дата: 2026-06-26.
Автор: Codex implementation track.

## Summary

Implemented portion 1 from `.agents/next-task-ux-implementation.md`: visible focus rings for main interactive controls and stable speaker-name inputs during 2-second polling.

## Files Changed

- `app/src/voice_recognizer/web.py` - added `:focus-visible` CSS for buttons/rows/export chips; added local speaker-name draft state, focus/caret capture, and input rewiring after result re-render.
- `.agents/task-board.md` - marked the implementation task as delivered and recorded checks.
- `.agents/handoff-ux-f1-f2.md` - this handoff.

## Checks Run

- `.venv/bin/python -m compileall app/src` - pass.
- `VOICE_RECOGNIZER_PORT=8782 VOICE_RECOGNIZER_OUTPUT_DIR=outputs/ui-f2-smoke VOICE_RECOGNIZER_OPEN_BROWSER=0 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/start_server.sh` - pass.
- Browser/IAB page identity - `http://127.0.0.1:8782/`, title `Диктум`, console warnings/errors empty.
- F2 live regression - processed a 30-second job with two speaker samples; typed `Андрей Петрович` into speaker 1 in chunks, waited 6.9 seconds, value/focus/caret stayed intact.
- Apply names smoke - export rerender completed with `ASR: -, diarization: -`; console stayed clean.
- Mobile smoke at 390x760 - no horizontal overflow, console clean.

## Not Checked

- Manual human Tab navigation in the visible desktop browser. The IAB keyboard runtime did not advance focus with Tab from body/input, so focus-ring validation used CSS rule inspection plus rendered browser smoke.

## Risks

- F1 CSS is present for `.btn`, `.segment`, `.file-row`, `.job-row`, `.link-chip`; a human keyboard pass should still be done in a normal browser because IAB did not deliver Tab traversal reliably.
- F2 stores unsaved speaker-name drafts per in-memory job id. This is correct for live jobs, but disk-backed results from future F15/F16 will need the same pattern with synthetic result ids.

## Next Suggested Task

Implement portion 2 from `.agents/next-task-ux-implementation.md`: F3 + F4 in `app/src/voice_recognizer/web.py` for pipeline stage/elapsed visibility and human-readable error recovery.
