# Prompt: Claude Local Setup Proposal

Read:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/product-requirements.md`
- `docs/implementation-plan.md`
- `docs/local-mac-product-plan.md`
- `scripts/start_server.sh`
- `scripts/setup_gigastt.sh`

Task:

Propose the smallest reliable local Mac setup path for a non-technical user.

Do not edit application code. Write only `.agents/claude-local-setup-proposal.md`.

Include:

1. User journey from downloaded folder to first successful transcript.
2. Required setup checks.
3. Which dependencies can be installed automatically and which need manual consent.
4. Model download strategy.
5. Failure states and user-facing messages.
6. Files/scripts that should be implemented next.

Constraints:

- local/private by default;
- no regular payments;
- no Docker/self-host yet;
- do not expose tokens;
- do not assume the user can use Terminal.
