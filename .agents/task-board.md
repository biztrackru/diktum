# Task Board

Дата: 2026-06-26.

## Current Product Focus

Сделать нормальный локальный Mac-продукт до self-host и публичной публикации.

Definition of "normal local product":

- пользователь скачивает/получает папку или установщик;
- запускает понятный setup/launcher;
- setup проверяет Python/ffmpeg/модели/токены и сам объясняет, что делать;
- web UI открывается локально;
- можно загрузить аудио, запустить обработку, назвать спикеров и открыть результаты;
- проблемы показываются человеческим языком, не только traceback.

## Active Branches

- `main` - baseline.
- `codex/upload-files-queue` - upload UI and project coordination changes.

## Active Work

### Codex

Scope:

- `AGENTS.md`
- `CLAUDE.md`
- `.agents/`
- `docs/implementation-plan.md`
- `docs/local-mac-product-plan.md`
- `README.md`

Goal:

- подготовить репозиторий к безопасной параллельной работе Codex + Claude Code;
- отложить self-host;
- определить путь к локальному Mac-продукту.

### Claude Code

Not started.

Suggested first task:

```text
Read AGENTS.md, CLAUDE.md, docs/product-requirements.md, docs/implementation-plan.md, and docs/local-mac-product-plan.md.

Do not edit code yet. Review the local Mac product plan and propose the smallest setup/installer path for a non-technical Mac user. Write your proposal to .agents/claude-local-setup-proposal.md only.
```

## Next Implementation Tasks

1. Local setup doctor:
   - detect Python version;
   - detect ffmpeg/ffprobe;
   - detect `.venv`;
   - detect GigaSTT binary and model files;
   - detect HF token presence without printing it;
   - show clear next actions.

2. Local setup launcher:
   - double-clickable setup `.command`;
   - creates `.venv`;
   - installs dependencies;
   - runs model setup or explains manual model download;
   - ends with "Start Voice Recognizer".

3. UI upload completion:
   - keep uploaded file selected;
   - add duration metadata once probing is fast enough;
   - support checked subset batch mode.

4. Long task UX:
   - stage labels;
   - elapsed time;
   - last successful artifact;
   - retry/resume language.

5. Speaker workflow:
   - robust sample playback;
   - stable name inputs during polling;
   - per-file speaker count and speaker names.

## Coordination Rules

- Claim one task and one write scope before editing.
- Do not edit files listed under another active owner.
- Commit small, thematic changes.
- Review before merging to `main`.
- If a task requires touching shared files like `README.md`, mention it in the handoff.
