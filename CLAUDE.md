# Claude Code Instructions

Read this file first when working on Voice Recognizer.

## One sentence mission

Build a private local macOS transcription product that a normal Mac user can install and run without developer help.

## Must-read files

- `AGENTS.md` - shared agent rules and safety constraints.
- `.agents/task-board.md` - current task ownership and handoff rules.
- `docs/product-requirements.md` - product requirements.
- `docs/implementation-plan.md` - current staged plan.
- `docs/local-mac-product-plan.md` - local installer/product direction.

## Current focus

Do not prioritize Docker, cloud, public GitHub packaging, or a marketing landing page yet.

Focus on:

- local Mac setup;
- one-click launch/stop;
- model/runtime setup diagnostics;
- file upload and batch processing;
- long file reliability;
- speaker naming and export UX.

## Boundaries

Do not commit or read aloud secrets from `.env`.
Do not commit audio files, generated outputs, model files, caches, or user documents.
Do not modify `Inbox/`, `inbox/`, `outputs/`, `.cache/`, `.models/`, `.venv/` unless the task explicitly asks for runtime testing.

If you need to run a test that creates files there, clean up only the files you created.

## Coordination

Before editing, check:

```bash
git status --short --branch
```

If another agent has uncommitted changes in the same files, stop and ask for coordination.

Use a clear write scope in your task. Good examples:

- only `src/voice_recognizer/web.py`;
- only `scripts/setup_local_mac.sh` and docs;
- only `.agents/` docs.

Bad examples:

- "clean up the project";
- "improve the UI" without file ownership;
- broad formatting across unrelated files.

## Review style

When asked for review, answer with findings first:

- severity;
- file and line;
- concrete risk;
- suggested fix.

If no critical issues are found, say so directly and list remaining risks.

## Useful commands

```bash
.venv/bin/python -m compileall src
zsh -n scripts/start_server.sh scripts/stop_server.sh scripts/setup_gigastt.sh
git status --short --ignored
```

For local UI testing, prefer a non-default port:

```bash
VOICE_RECOGNIZER_PORT=8782 VOICE_RECOGNIZER_OPEN_BROWSER=0 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 scripts/start_server.sh
VOICE_RECOGNIZER_PORTS=8782 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 scripts/stop_server.sh
```
