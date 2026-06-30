# WhisperLiveKit Research Gate

Дата: 2026-06-26.

Source: https://github.com/QuentinFuxa/WhisperLiveKit

## Decision

WhisperLiveKit is not a replacement for Диктум's current local-file workflow.

It is a strong reference for:

- model manager commands;
- setup/doctor/troubleshooting style;
- benchmark harness;
- backend profile separation;
- optional Whisper/Voxtral/Qwen backend integration;
- OpenAI-compatible local API surface.

It should not expand the next local Mac product scope with:

- live microphone transcription;
- WebSocket UI;
- Docker/self-host production setup;
- translation;
- chrome extension;
- multi-user server concerns.

## What To Borrow Now

For the next setup/installer work, borrow the idea shape, not code:

- explicit model checks and download commands;
- clear optional dependency profiles;
- user-facing troubleshooting;
- benchmark task as a later dev tool.

## What To Evaluate Later

Before adding Whisper as a local engine:

1. Try `wlk transcribe` on the Russian sample files.
2. Compare quality and speed against `gigastt-gigaam-v3`.
3. Check Apple Silicon MLX dependencies on the target Mac.
4. Decide whether to integrate through CLI, Python API, or local OpenAI-compatible API.

Apache-2.0 allows reuse with attribution and notices, but we avoid copying code until there is a concrete reason.
