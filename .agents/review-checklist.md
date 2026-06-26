# Review Checklist

Use this checklist before merging or accepting agent work.

## Privacy

- No `.env`, real tokens, API keys, private audio, generated outputs, model files, or caches in git.
- No code path uploads audio/transcripts externally unless the user explicitly selected an external engine.
- Error logs do not print secrets.

## Local Mac Product

- A non-technical Mac user has a next step after every failure.
- Launch/stop scripts still work.
- New setup steps are documented and testable.
- Default behavior remains local/private.

## Pipeline

- Long files do not fail due to known ASR single-file limits.
- Existing intermediate artifacts can be reused when safe.
- Batch mode does not start uncontrolled parallel heavy jobs.
- Speaker count is per file, not hardcoded globally.

## UI

- Upload/select/run/result path completes without page reload.
- Polling does not wipe user edits in speaker name fields.
- Audio samples play through and support range requests.
- Results open from the UI.
- Empty/error states are clear.

## Code Quality

- Scope is small and intentional.
- No unrelated formatting churn.
- No broad rewrites without tests.
- Commands and paths work from the documented project root.

## Required Checks

For Python changes:

```bash
.venv/bin/python -m compileall src
```

For shell changes:

```bash
zsh -n scripts/*.sh
```

For web changes:

- start on a non-default test port;
- open in browser;
- check console errors;
- stop the server.
