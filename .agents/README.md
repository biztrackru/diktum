# AI Agent Workspace

This directory contains coordination files for Codex, Claude Code, and future review agents.

It is intentionally separate from application code. Agents can write planning, task ownership, handoff notes, and review prompts here without mixing them into the installable product surface.

Application code remains in `app/src/voice_recognizer/`.

Current coordination files:

- `product-backlog.md` - source of truth for prioritized product tasks and acceptance criteria.
- `task-board.md` - active claims, delivery journal, blockers, and handoff notes.
- `review-checklist.md` - acceptance checklist for diffs.
- `handoff-template.md` - format for agent handoffs.
- `prompts/` - reusable prompts for Claude/Codex/review roles.

Workflow:

1. Read `product-backlog.md`.
2. Claim exactly one task in `task-board.md`.
3. Keep edits inside the claimed scope.
4. Record checks and residual risks in `task-board.md`.
5. Update backlog status only when the task is truly delivered or blocked.
