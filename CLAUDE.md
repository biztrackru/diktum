# Claude Code Instructions

Read this file first when working on Диктум.

## Mission

Build a private local macOS transcription product that a normal Mac user can install and run without developer help.

## Must-read files

- `AGENTS.md` - shared agent rules and safety constraints.
- `README.md` - public product and setup overview.
- `docs/product-requirements.md` - product requirements.
- `docs/architecture.md` - pipeline shape.
- `docs/user-scenarios.md` - core user workflows.

If a local `.agents/` directory exists, use it for local task ownership and handoffs. It is intentionally not published.

## Boundaries

Do not commit or read aloud secrets from `.env`.
Do not commit audio files, generated outputs, model files, caches, local benchmark references, or user documents.
Do not modify `Inbox/`, `inbox/`, `outputs/`, `.cache/`, `.models/`, `.venv/`, `.dist/` unless the task explicitly asks for runtime testing.

If you need to run a test that creates files there, clean up only the files you created.

## Useful commands

```bash
.venv/bin/python -m compileall app/src
zsh -n app/scripts/start_server.sh app/scripts/stop_server.sh app/scripts/setup_gigastt.sh
app/scripts/smoke_local.sh
git status --short --ignored
```

For local UI testing, prefer a non-default port:

```bash
VOICE_RECOGNIZER_PORT=8782 VOICE_RECOGNIZER_OPEN_BROWSER=0 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/start_server.sh
VOICE_RECOGNIZER_PORTS=8782 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/stop_server.sh
```
