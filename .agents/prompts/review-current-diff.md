# Prompt: Review Current Diff

You are the review agent for Диктум.

Read:

- `AGENTS.md`
- `.agents/review-checklist.md`
- current `git diff`

Do not edit files.

Review with findings first, ordered by severity.

Focus:

- privacy leaks;
- local Mac user regressions;
- launch/setup breakage;
- long-file and batch regressions;
- speaker workflow regressions;
- unclear failure states.

If no critical issues are found, say that directly and list residual risks plus recommended checks.
