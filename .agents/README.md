# AI Agent Workspace

This directory contains coordination files for Codex, Claude Code, and future review agents.

It is intentionally separate from application code. Agents can write planning, task ownership, handoff notes, and review prompts here without mixing them into the installable product surface.

Application code remains in `app/src/voice_recognizer/`.

Current coordination files:

- `task-board.md` - active work, ownership, and next tasks.
- `review-checklist.md` - acceptance checklist for diffs.
- `handoff-template.md` - format for agent handoffs.
- `prompts/` - reusable prompts for Claude/Codex/review roles.
