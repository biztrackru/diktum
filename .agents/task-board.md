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

- `app/scripts/setup_local_mac.sh`
- `Настроить Voice Recognizer.command`
- `docs/implementation-plan.md`
- `docs/local-mac-product-plan.md`
- `README.md`

Goal:

- реализовать первый double-click setup для локального Mac-продукта;
- учесть Apple Silicon M5/32GB как целевую машину;
- спрашивать разрешение перед установкой Homebrew/ffmpeg/dependencies/models;
- использовать локальный `.env` с read-only HF token без вывода секрета.

### Claude Code

Not started.

Suggested first task:

```text
Read AGENTS.md, CLAUDE.md, docs/product-requirements.md, docs/implementation-plan.md, and docs/local-mac-product-plan.md.

Do not edit code yet. Review the local Mac product plan and propose the smallest setup/installer path for a non-technical Mac user. Write your proposal to .agents/claude-local-setup-proposal.md only.
```

## Next Implementation Tasks

0. WhisperLiveKit research gate:
   - read `docs/external-projects.md` section `QuentinFuxa/WhisperLiveKit`;
   - decide whether to borrow model manager, doctor, benchmark, optional backend profile ideas;
   - do not add live WebSocket, Docker, translation, chrome extension, or multi-user features to the local Mac product yet;
   - write findings to `.agents/whisperlivekit-research.md` before implementing setup/engine registry changes.

1. Local setup doctor:
   - detect Python version;
   - detect ffmpeg/ffprobe;
   - detect `.venv`;
   - detect GigaSTT binary and model files;
   - detect HF token presence without printing it;
   - show clear next actions.
   - status: first double-click setup script exists, separate doctor command still pending.

2. Local setup launcher:
   - double-clickable setup `.command`;
   - creates `.venv`;
   - installs dependencies;
   - runs model setup or explains manual model download;
   - ends with "Start Voice Recognizer".
   - status: first launcher exists as `Настроить Voice Recognizer.command`.

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
