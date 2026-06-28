# Task Board

Дата: 2026-06-28.

Назначение: active claims, delivery journal, blockers and handoffs.

Источник правды для приоритетов и acceptance criteria: `.agents/product-backlog.md`.

Правило: перед кодовой работой агент должен claim'ить один task ID из `.agents/product-backlog.md` в секции `Active Claims`.

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
- `codex/ux-f1-f2` - current local work branch with UX/productization commits.

## Active Claims

No active claims.

Next agent should pick exactly one `READY` task from `.agents/product-backlog.md`, add a claim here, and then edit files.

Claim template:

```md
### <Agent> - <TASK-ID> <short title>

Status: CLAIMED (YYYY-MM-DD).

Scope:

- `path`

Goal:

- concrete outcome

Acceptance:

- copied from `.agents/product-backlog.md`, narrowed if needed

Notes:

- risks/blockers
```

## Delivery Journal

### Codex - UX-P0-008 Launch UI Cleanup

Status: DELIVERED (2026-06-28). First-screen launch UI noise removed.

Scope:

- `app/src/voice_recognizer/web.py`
- `.agents/product-backlog.md`
- `.agents/claude-prototype-integration-subtasks.md`
- `.agents/task-board.md`

Trigger:

- User feedback after successful spouse-Mac acceptance: launch settings showed premature `Имена спикеров`, and the top `1 Inbox / 2 Настройки / 3 Очередь / 4 Спикеры / 5 Экспорт` strip looked like accidental UI noise.

What changed:

- Removed the top workflow strip and its unused CSS/JS state updater.
- Removed `Имена спикеров` from launch settings; speaker naming stays in the result `Спикеры` tab after processing.
- Kept device/output/overwrite behind `Подробнее`.
- Updated backlog and Claude subtask notes so the next highest-priority task is `P0-007 Local Smoke Suite`.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-165258.zip`

Checks:

- Browser QA on `http://127.0.0.1:8796/`: page title `Voice Recognizer`, meaningful first screen rendered, no framework overlay, no console warn/error logs.
- Browser interaction: `Подробнее` opens/closes; `Готовые` -> first disk result -> `Спикеры` shows speaker-name inputs and `Применить имена`.
- Browser DOM checks: no `.workflow`, `.workflow-step`, `.step-index`; launch form text no longer contains `Имена спикеров`.
- `.venv/bin/python -m compileall app/src`;
- `PYTHONPATH=app/src .venv/bin/python -m voice_recognizer.cli --help`;
- `git diff --check`;
- `rg -n "Имена спикеров|workflow|workflow-step|updateWorkflow|workflowSteps|step-index" app/src/voice_recognizer/web.py` returned no matches;
- `PATH='' app/scripts/build_install_pack.sh`;
- archive scan confirmed no real `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- secret scan found no real HF/OpenAI tokens.

### Codex - P0-001 First Run Diarization Visibility

Status: DELIVERED (2026-06-28). First processing run no longer looks silent after ASR.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/web.py`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- External first test-file run on the spouse Mac stayed `Выполняется` for 5+ minutes after ASR with the last technical log line: `Matplotlib is building the font cache; this may take a moment.`

What changed:

- `run_pyannote` now prepares `.cache/matplotlib` and emits progress messages before import, model load, device move, audio load, diarization run and completion.
- CLI passes a progress callback and flushes progress lines.
- Web jobs now run `python -u -m voice_recognizer.cli ...` and set `PYTHONUNBUFFERED=1`.
- Web stage detection treats `pyannote`, `speaker separation`, `Matplotlib` and `font cache` as `Диаризация`.
- Setup now pre-warms the Matplotlib font cache after Python runtime is ready.
- README, spouse checklist and generated `START_HERE.txt` explain that first diarization can take longer and should show `Diarization / pyannote: ...` heartbeat lines.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-154116.zip`

Checks:

- `.venv/bin/python -m compileall app/src`;
- `PATH='' /bin/zsh -n Настроить/Проверить/Запустить/Остановить/Разблокировать .command app/scripts/setup_local_mac.sh app/scripts/doctor_local_mac.sh app/scripts/start_server.sh app/scripts/stop_server.sh app/scripts/unblock_macos.sh app/scripts/build_install_pack.sh`;
- `PATH='' /bin/bash -n app/scripts/setup_gigastt.sh`;
- `PYTHONPATH=app/src .venv/bin/python -m voice_recognizer.cli --help`;
- local setup completed with `failures=0` and pre-warmed Matplotlib font cache;
- Python check confirmed web job commands start with `python -u -m voice_recognizer.cli`;
- archive scan confirmed no real `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- `git diff --check`;
- secret scan found no real HF/OpenAI tokens.

### Codex - P0-001 GigaSTT Punctuation Setup And Doctor Hang

Status: DELIVERED (2026-06-28). GigaSTT punctuation model setup and faster doctor.

Scope:

- `app/scripts/setup_gigastt.sh`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/doctor_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- External setup log `/Users/andrey/Downloads/setup-20260628-122805.log` showed `tools/bin/gigastt` and RNNT model files ready, but stage `4/5: GigaSTT/GigaAM v3` failed because `punct/rupunct_small_int8.onnx`, `punct/config.json` and `punct/tokenizer.json` were missing.
- User reported `Проверить Voice Recognizer.command` hanging on one step for several minutes before interruption.

Root cause:

- `gigastt download --model-dir ... --prequantized` prepares the main GigaAM/RNNT model, but does not fetch the optional punctuation model directory used by our `gigastt transcribe --punctuation on --punct-model-dir ...` path.
- Doctor imported `pyannote.audio` just to check package presence. That is a heavy Torch/Lightning import and can look frozen on first launch.

What changed:

- `setup_gigastt.sh` now explicitly downloads/checks RUPunct files from public `ekhodzitsky/rupunct-small-onnx` URLs into `.models/gigastt/punct/`.
- The RUPunct downloads use SHA-256 checksums and reuse existing good files.
- Setup text now names `.models/gigastt/punct/` as a separate punctuation/casing model, and failure guidance points at missing GigaSTT/GigaAM/punct files instead of only "network/VPN".
- Doctor now checks Python package metadata with `importlib.metadata` instead of importing `pyannote.audio`, avoiding the multi-minute heavy import in default checks.
- README, trial `START_HERE.txt` generator and spouse-Mac checklist now mention the RUPunct files.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-123608.zip`

Checks:

- `PATH='' /bin/bash -n app/scripts/setup_gigastt.sh`;
- `PATH='' /bin/zsh -n Настроить/Проверить/Запустить/Остановить/Разблокировать .command app/scripts/setup_local_mac.sh app/scripts/doctor_local_mac.sh app/scripts/start_server.sh app/scripts/stop_server.sh app/scripts/unblock_macos.sh app/scripts/build_install_pack.sh`;
- local `PATH='' /bin/bash app/scripts/setup_gigastt.sh` found/reused main models and all three `punct/` files;
- local `PATH='' VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 /bin/zsh app/scripts/doctor_local_mac.sh` completed quickly with `failures=0`;
- local `PATH='' VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 /bin/zsh app/scripts/setup_local_mac.sh` completed with `failures=0` and recognized GigaSTT ready;
- HEAD checks against the three Hugging Face RUPunct URLs returned HTTP 200 after redirects;
- `PATH='' app/scripts/build_install_pack.sh`;
- packed scripts/docs contain the RUPunct setup and fast metadata doctor changes;
- archive scan confirmed no real `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- `git diff --check`;
- secret scan found no real HF/OpenAI tokens.

Immediate external-Mac next step:

- Copy/unpack `.dist/Voice Recognizer Trial 20260628-123608.zip` over the existing trial folder, making sure root `.command` files and `app/scripts/` are overwritten. Keeping old `.models`, `.venv`, `.env`, `.cache` and `tools/bin` is fine. Then run `Настроить Voice Recognizer.command`; it should download only the missing `punct/` files if the main GigaSTT model is already present. After that run `Проверить Voice Recognizer.command` again.

### Codex - P0-001 Stable macOS Script PATH

Status: DELIVERED (2026-06-28). Finder-launched setup PATH hardening.

Scope:

- `Настроить Voice Recognizer.command`
- `Проверить Voice Recognizer.command`
- `Запустить Voice Recognizer.command`
- `Остановить Voice Recognizer.command`
- `Разблокировать Voice Recognizer.command`
- `app/scripts/setup_gigastt.sh`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/doctor_local_mac.sh`
- `app/scripts/start_server.sh`
- `app/scripts/stop_server.sh`
- `app/scripts/unblock_macos.sh`
- `app/scripts/build_install_pack.sh`
- `.agents/task-board.md`

Trigger:

- External setup log `/Users/andrey/Downloads/setup-20260628-121409.log` from the spouse Mac showed the previous `/bin/bash` fix worked, but `setup_gigastt.sh` then failed with `dirname: No such file or directory` and `mkdir: No such file or directory`.

Root cause:

- The `.command` launch environment on the target Mac had a minimal or broken `PATH`, so even standard macOS utilities from `/usr/bin` and `/bin` were not discoverable inside the helper scripts.

What changed:

- All root `.command` launchers and `app/scripts/*.sh` helpers now export a safe macOS `PATH` before running external commands:
  `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}`.
- `setup_gigastt.sh` still uses `#!/bin/bash`, and `setup_local_mac.sh` still invokes it through `/bin/bash "$APP_DIR/scripts/setup_gigastt.sh"`.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-121828.zip`

Checks:

- `PATH='' /bin/zsh -n Настроить/Проверить/Запустить/Остановить/Разблокировать .command app/scripts/setup_local_mac.sh app/scripts/doctor_local_mac.sh app/scripts/start_server.sh app/scripts/stop_server.sh app/scripts/unblock_macos.sh app/scripts/build_install_pack.sh`;
- `PATH='' /bin/bash -n app/scripts/setup_gigastt.sh`;
- `PATH='' VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/unblock_macos.sh`;
- `rg` confirmed the safe `PATH` export in all root launchers and helper scripts;
- `git diff --check`;
- `PATH='' app/scripts/build_install_pack.sh`;
- packed scripts in `.dist/Voice Recognizer Trial 20260628-121828` contain the safe `PATH` export;
- packed `setup_gigastt.sh` starts with `#!/bin/bash`;
- packed `setup_local_mac.sh` invokes `/bin/bash "$APP_DIR/scripts/setup_gigastt.sh"`;
- archive scan confirmed no real `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- secret scan found no real HF/OpenAI tokens in the repo diff/files scanned by `rg`.

Immediate external-Mac next step:

- Copy/unpack `.dist/Voice Recognizer Trial 20260628-121828.zip` over the existing trial folder. Keeping the old `.models`, `.venv`, `.env`, `.cache` and `tools/bin` is fine, but the root `.command` files and `app/scripts/` must be overwritten. Then run `Настроить Voice Recognizer.command` again and send `logs/setup-latest.log` if the GigaSTT step still fails.

### Codex - P0-001 GigaSTT Bash Path Fix

Status: DELIVERED (2026-06-28). Clean-Mac setup script runtime fix.

Scope:

- `app/scripts/setup_gigastt.sh`
- `app/scripts/setup_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `.agents/task-board.md`

Trigger:

- External setup log from `/Users/appleside/Documents/Voice Recognizer Trial 20260627-212358/logs/setup-20260628-120509.log` showed GigaSTT model download failing with `env: bash: No such file or directory`, despite network being available.

Root cause:

- `app/scripts/setup_gigastt.sh` used `#!/usr/bin/env bash`, which depends on `bash` being discoverable in the `.command` process `PATH`. On the target Mac, `env` could not find `bash`.

What changed:

- `setup_gigastt.sh` now uses `#!/bin/bash`, the standard macOS bash path.
- `setup_local_mac.sh` now invokes GigaSTT setup with `/bin/bash "$APP_DIR/scripts/setup_gigastt.sh"`, so the target `.command` PATH no longer affects this step.
- Setup now emits a specific failure if `/bin/bash` itself is unavailable.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-121003.zip`

Checks:

- `zsh -n app/scripts/setup_local_mac.sh app/scripts/*.sh`;
- `/bin/bash -n app/scripts/setup_gigastt.sh`;
- `git diff --check`;
- `app/scripts/build_install_pack.sh`;
- packed `setup_gigastt.sh` starts with `#!/bin/bash`;
- packed `setup_local_mac.sh` calls `/bin/bash "$APP_DIR/scripts/setup_gigastt.sh"`;
- packed helper and all root `.command` launchers are executable;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`.

Immediate external-Mac workaround:

- In the already-unpacked old folder, run `/bin/bash app/scripts/setup_gigastt.sh` from Terminal to finish the missing `punct/` model files, then rerun doctor. For continued testing, prefer the rebuilt archive above.

### Codex - P0-001 macOS Gatekeeper Unblock Helper

Status: DELIVERED (2026-06-28). Trial-pack first-run unblock workaround.

Scope:

- `Разблокировать Voice Recognizer.command`
- `app/scripts/unblock_macos.sh`
- `app/scripts/build_install_pack.sh`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- macOS Gatekeeper blocks unsigned `.command` files from the transferred zip with a scary `не удалось проверить на наличие вредоносного ПО` prompt and defaults to moving files to Trash.

What changed:

- Added `Разблокировать Voice Recognizer.command`, a one-time helper launcher.
- Added `app/scripts/unblock_macos.sh`; it runs `xattr -r -d com.apple.quarantine` on the unpacked Voice Recognizer folder, verifies remaining quarantine attributes and prints a Terminal fallback.
- Trial pack now copies the unblock launcher and marks it executable along with the other `.command` launchers.
- `START_HERE.txt`, README and spouse-Mac checklist now explain Gatekeeper/quarantine, the one-time helper, the Terminal drag-and-drop fallback and the real future fix: Apple Developer ID signing + notarization.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-120506.zip`

Checks:

- `zsh -n Разблокировать Voice Recognizer.command app/scripts/unblock_macos.sh app/scripts/*.sh`;
- `VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/unblock_macos.sh` completed and reported quarantine removed on the local folder;
- `git diff --check`;
- `app/scripts/build_install_pack.sh`;
- packed helper and all root `.command` launchers are executable;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- packed `START_HERE.txt`, README, spouse checklist and helper contain the new Gatekeeper/quarantine instructions.

Remaining:

- This is still a workaround. Smooth public distribution needs Developer ID signing and notarization.

### Codex - P0-001 GigaSTT Setup Verification Logs

Status: DELIVERED (2026-06-28). First-run model diagnostics update.

Scope:

- `app/scripts/setup_local_mac.sh`
- `app/scripts/setup_gigastt.sh`
- `app/scripts/doctor_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `.gitignore`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- External Mac setup appeared to download GigaSTT/GigaAM successfully, but web UI still reported `GigaSTT не настроен`; rerunning setup did not reveal which file was missing.

Root cause found:

- `ensure_gigastt` in setup accepted only `tools/bin/gigastt` plus `v3_rnnt_encoder.onnx`, while web UI also requires decoder, joint, vocab and punctuation files under `.models/gigastt/punct/`. A partial model download could therefore look successful in setup but fail in UI.

What changed:

- Setup now verifies the same GigaSTT/GigaAM runtime surface as the UI: binary, encoder or INT8 encoder, decoder, joint, vocab, `punct/rupunct_small_int8.onnx`, `punct/config.json` and `punct/tokenizer.json`.
- `setup_gigastt.sh` prints a model file inventory and exits non-zero if required files are still missing after download.
- `doctor_local_mac.sh` now checks punctuation files and prints the same model inventory.
- Setup and doctor now write local shareable logs to `logs/setup-<timestamp>.log`, `logs/setup-latest.log`, `logs/doctor-<timestamp>.log` and `logs/doctor-latest.log`.
- `.gitignore` excludes `logs/`.
- `START_HERE.txt`, README and spouse-Mac checklist tell users to forward only `logs/setup-latest.log` and `logs/doctor-latest.log`, not `.env`, Inbox audio or outputs.

Built artifact:

- `.dist/Voice Recognizer Trial 20260628-115050.zip`

Checks:

- `zsh -n app/scripts/*.sh`;
- `bash -n app/scripts/setup_gigastt.sh`;
- `.venv/bin/python -m compileall app/src`;
- `git diff --check`;
- local noninteractive `app/scripts/doctor_local_mac.sh` created `logs/doctor-20260628-115009.log`, found all required GigaSTT/GigaAM files and reported `failures=0`;
- local noninteractive `app/scripts/setup_local_mac.sh` created `logs/setup-20260628-115010.log`, printed GigaSTT inventory and reported GigaSTT ready;
- `_asr_runtime_status(Path.cwd())` reports `GigaSTT готов`; `_asr_runtime_status(empty root)` reports missing binary, encoder, decoder, joint, vocab and punct;
- `app/scripts/build_install_pack.sh`;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `.dist`, `logs/`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- packed setup, doctor, setup_gigastt, README, `START_HERE.txt` and spouse checklist contain the new log/model diagnostics.

Immediate external-Mac next step:

- Install from `.dist/Voice Recognizer Trial 20260628-115050.zip`, rerun setup and doctor, then send `logs/setup-latest.log` and `logs/doctor-latest.log` if UI still reports `GigaSTT не настроен`.

### Codex - P0-001 GigaSTT First-Launch Setup And Compact Settings

Status: DELIVERED (2026-06-27). First-run install and UI clarity update.

Scope:

- `app/scripts/setup_local_mac.sh`
- `app/scripts/setup_gigastt.sh`
- `app/scripts/doctor_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `app/src/voice_recognizer/web.py`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- First launch after installation showed `GigaSTT не настроен` in the UI without explaining what GigaSTT is or how to complete that setup.
- User also asked to hide settings that only apply to selected menu variants and collapse extra settings under `Подробнее`.

What changed:

- Setup now explains GigaSTT/GigaAM v3 as the local Russian ASR engine, lists `tools/bin/gigastt`, `.models/gigastt/` and `.cache/downloads/`, and says the network download can be rerun safely.
- GigaSTT setup failure/skip now records a blocking setup failure instead of allowing a misleading "ready" launch.
- Doctor now explains missing GigaSTT binary/model files and points to `Настроить Voice Recognizer.command`, stage `4/5: GigaSTT/GigaAM v3`.
- Web UI GigaSTT missing status now says the local ASR is not ready and names the exact setup stage to run.
- Web UI hides start/duration unless `Тест-фрагмент` is selected, hides speaker count fields unless `Точно` or `Диапазон` is selected, and collapses device/output/speaker names/overwrite into `Подробнее`.
- Switching back from `Тест-фрагмент` to full-file mode clears hidden start/duration values so they cannot affect a full run silently.
- `START_HERE.txt`, README and spouse-Mac checklist now explain GigaSTT/GigaAM v3 for a non-technical install.

Built artifact:

- `.dist/Voice Recognizer Trial 20260627-234802.zip`

Checks:

- `zsh -n app/scripts/*.sh`;
- `.venv/bin/python -m compileall app/src`;
- `git diff --check`;
- `_asr_runtime_status` on an empty root returns the new `GigaSTT не настроен` explanation and stage `4/5` next step;
- in-app Browser on `http://127.0.0.1:8794/`: page title `Voice Recognizer`, no console errors/warnings, desktop and mobile `390x844` had no horizontal overflow;
- UI state checks: initial full-file mode hides start/duration, speaker numeric fields and advanced fields; `Тест-фрагмент` shows start/duration presets; `Точно` shows only exact speaker count; `Диапазон` shows min/max; `Подробнее` reveals device/output/speaker names/overwrite;
- returning from `Тест-фрагмент` to full-file mode clears hidden start/duration values;
- `app/scripts/build_install_pack.sh`;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- packed `START_HERE.txt`, setup scripts, doctor, README, checklist and web UI contain the new GigaSTT/settings changes.

Remaining:

- External Mac acceptance still needed: rerun the new pack on the target Mac and confirm stage `4/5: GigaSTT/GigaAM v3` completes under that network.

### Codex - P0-001 HF Token Setup Explanation

Status: DELIVERED (2026-06-27). Trial-pack safety copy update.

Scope:

- `app/scripts/setup_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `README.md`
- `docs/setup-secrets.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- Clean-Mac setup reached the HF token prompt without enough explanation of why it is needed, where to get it, and whether it is safe to ship a token with the pack.

What changed:

- Setup now explains that HF token is only for pyannote speaker diarization; ASR/UI can be installed without it, but speaker diarization remains unready.
- Setup gives the pyannote model URL, Hugging Face token settings URL, read-only token guidance, hidden-input behavior and skip consequence.
- `START_HERE.txt`, README, setup secrets doc and spouse-Mac checklist now recommend a dedicated read-only test token passed separately from the zip, not embedded in the archive.

Built artifact:

- `.dist/Voice Recognizer Trial 20260627-231609.zip`

Checks:

- `zsh -n app/scripts/*.sh`;
- `.venv/bin/python -m compileall app/src`;
- `git diff --check`;
- `app/scripts/build_install_pack.sh`;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- packed `START_HERE.txt` and packed `setup_local_mac.sh` contain the new HF token explanation.

Recommendation:

- Do not put a real HF token into the trial zip. For the spouse-Mac test, create a separate read-only Hugging Face token, paste it during setup, and revoke it after the test if desired.

### Codex - P0-001 Staged Setup After Clean-Mac Feedback

Status: DELIVERED (2026-06-27). Trial-pack update; external Mac retry needed.

Scope:

- `app/scripts/setup_local_mac.sh`
- `app/scripts/build_install_pack.sh`
- `README.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/task-board.md`

Trigger:

- Clean-Mac install screenshot showed Homebrew ffmpeg dependencies failing from `ghcr.io` with `curl: (28)` timeout and `curl: (35)` SSL errors.

What changed:

- Setup now runs in explicit stages: base tools, Python runtime, HF token, GigaSTT/GigaAM, checks.
- Setup stops after failed base tools or Python runtime instead of continuing to Python dependencies, HF token, GigaSTT binary/model downloads and pyannote checks.
- Homebrew ffmpeg step now explains that `ghcr.io` timeout/SSL failures are network/retry issues and that setup can be safely rerun.
- `START_HERE.txt`, README and spouse-Mac checklist now document the Homebrew retry behavior.

Built artifact:

- `.dist/Voice Recognizer Trial 20260627-225847.zip`

Checks:

- `zsh -n app/scripts/*.sh`;
- `git diff --check`;
- `app/scripts/build_install_pack.sh`;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- fresh-pack setup smoke with no interactive stdin: stopped at `Этап 2/5: Python runtime`, did not prompt for HF token and did not attempt GigaSTT/model download;
- fresh-pack doctor smoke still reports missing `.venv`, `.env`, GigaSTT binary/models with next steps.

Immediate user guidance:

- If Homebrew keeps failing on `ghcr.io`, stop with `Ctrl+C`, retry later or on another network/hotspot, then rerun `Настроить Voice Recognizer.command`; already downloaded Homebrew bottles are usually reused.

### Codex - P0-001 Mac Install Acceptance Trial Pack

Status: DELIVERED (2026-06-27). Trial-pack prep; external Mac acceptance still pending.

Scope:

- `app/scripts/build_install_pack.sh`
- `.gitignore`
- `README.md`
- `docs/local-mac-product-plan.md`
- `docs/spouse-mac-install-trial.md`
- `.agents/product-backlog.md`
- `.agents/task-board.md`

Goal:

- prepare a safe install archive and checklist for the first spouse-Mac installation attempt.

What changed:

- Added `app/scripts/build_install_pack.sh`, an allowlist-based pack builder that creates `.dist/Voice Recognizer Trial <timestamp>.zip`.
- Added `.dist/` to `.gitignore` for generated local archives.
- Added `docs/spouse-mac-install-trial.md` with clean/semi-clean Mac steps, success criteria, blockers and report template.
- Updated README and local Mac product plan with the trial-pack path and privacy exclusions.

Built artifact:

- `.dist/Voice Recognizer Trial 20260627-212358.zip`

Checks:

- `zsh -n app/scripts/*.sh`;
- `git diff --check`;
- `app/scripts/build_install_pack.sh`;
- archive scan confirmed no `.env`, `.venv`, `.models`, `.cache`, `tools/bin`, audio files, generated outputs, `.docx`, `__pycache__`, `.pyc` or `__MACOSX`;
- pack doctor smoke: expected fresh-pack failures for missing `.venv`, `.env`, GigaSTT binary/models, with next steps and hidden token behavior;
- pack setup non-interactive smoke: did not install/download without input; explained `.venv`, HF token and GigaSTT next steps;
- unzip smoke to `/tmp`: archive expands, Cyrillic `.command` launchers are present and executable.

Remaining:

- `P0-001` stays open until setup/doctor/start/stop are run on the target Mac and the result is recorded.

### Codex - UX-P0-002 Compact Journal And Polling Efficiency

Status: DELIVERED (2026-06-27). Implementation; no pipeline changes.

Scope:

- `app/src/voice_recognizer/web.py`
- `.agents/claude-prototype-integration-subtasks.md`
- `.agents/task-board.md`

Goal:

- make the active job journal compact by default and reduce queue/result polling churn.

What changed:

- Added compact `#log-summary` above a collapsible `#raw-log-details` full technical journal.
- `setLogText(...)` now updates line count, summary status/stage/elapsed/heartbeat, and preserves raw-log scroll when the reader is away from the bottom.
- Queue and result lists now use delegated click handlers and signature-based HTML patching instead of reattaching row listeners every polling cycle.

Checks:

- `.venv/bin/python -m compileall app/src`;
- `git diff --check`;
- rendered HTML smoke: `Voice Recognizer`, `#log-summary`, `#raw-log-details`, delegated list handlers and signature patch helpers present; inline script parsed with `new Function(...)`;
- Chrome/CDP smoke on `http://127.0.0.1:8791/`: opened first ready result, compact summary showed `Готово / Готовый результат`, raw log stayed collapsed but contained the manifest log, raw-log scroll stayed stable through synthetic update, runtime events empty;
- Chrome/CDP desktop `1280x900` and mobile `390x844`: `scrollWidth == clientWidth`, 5 Inbox rows and 15 result rows loaded;
- test server and headless Chrome stopped.

### Codex - UX-P0-001 Inline Launch And API Error Recovery

Status: DELIVERED (2026-06-27). Implementation; no pipeline changes.

Scope:

- `app/src/voice_recognizer/web.py`
- `.agents/claude-prototype-integration-subtasks.md`
- `.agents/task-board.md`

Goal:

- make foreground UI/API errors actionable instead of only writing raw `String(error)` into the journal.

What changed:

- Added shared frontend helper `showForegroundProblem(...)` that renders the existing diagnostic cards for foreground action failures and keeps technical detail in the journal.
- Wired it into single/batch launch, upload HTTP errors, Inbox/results reads, missing disk result, speaker-name apply, rerun, cancel and delete failures.
- Added specific diagnostics for upload validation, `output_dir` outside `outputs/`, invalid time fields, speaker setting mismatches, results/Inbox read failures, launch/batch failures, apply-name failures and rerun failures.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8791/`: page identity `Voice Recognizer`, console clean;
- synthetic POST validation smoke: set `Результаты=../outside-outputs`, clicked run, saw `Папка результатов вне outputs`, `role=alert`, preserved selected source and form value, created 0 job rows, technical `output_dir must stay inside outputs/` stayed in the journal;
- offline/read smoke: stopped server, polling showed `Сервер не отвечает`, next steps, `role=alert`, preserved form/source, technical `Failed to fetch` stayed in the journal;
- mobile viewport `390x844`: console clean, 5 Inbox rows, run modes visible, no horizontal overflow;
- test server stopped.

### Codex - UX Prototype Integration Triage

Status: DELIVERED (2026-06-27). UX/product triage; code intentionally not changed.

Scope:

- `.agents/claude-prototype-integration-subtasks.md`
- `.agents/product-backlog.md`
- `.agents/task-board.md`

Goal:

- verify how Claude's UI prototype is integrated into the current web UI;
- create concrete follow-up subtasks for remaining prototype/product gaps.

Findings:

- Integrated and browser-verified: desktop/mobile render, `Готовые`, disk-backed result opening, result tabs, transcript preview, processed Inbox badges, and F2 speaker-name polling preservation.
- Partial follow-ups remain around foreground error recovery, compact journal/polling efficiency, structured long-file chunk progress, batch session summaries, engine-profile UX, richer speaker workspace, result maintenance, and automated prototype smoke coverage.
- Prototype HTML could not be opened directly through in-app Browser because `file://` navigation is blocked by Browser policy; comparison used source inspection plus live UI rendering.

Deliverable:

- `.agents/claude-prototype-integration-subtasks.md`
- backlog pointer in `.agents/product-backlog.md`

Checks:

- in-app Browser on `http://127.0.0.1:8791/`: page identity `Voice Recognizer`, console clean, 5 Inbox rows, 15 disk results, 5 processed badges, no desktop horizontal overflow;
- in-app Browser interaction: opened `Готовые` result, result tabs rendered, transcript preview loaded, export groups rendered, speaker tab preserved `Тестовое имя Codex` through polling with focus/caret intact;
- mobile viewport `390x844`: console clean, no horizontal overflow, Inbox/run modes/center switch visible;
- `git diff --check`.

### Claude Code

Status: DELIVERED (2026-06-26), ready for implementation handoff. UX/product track. Docs done; код (`web.py`) намеренно не тронут — реализация за implementation-агентом.

Deliverables: `docs/ux-audit.md` (F1–F16, вкл. персистентность/результаты + оценка S/M/L), `docs/ux/voice-recognizer-prototype.html` (эталон поведения; вид «Готовые» + бейдж «обработан → готово»), `docs/ux-acceptance-scenarios.md` (S1–S10 + матрица). Передача, приоритеты и Data contract — `.agents/handoff-ux-redesign.md`. Порядок реализации: 1) F1+F2, 2) F3+F4, 3) F15+F16 (библиотека результатов из `outputs/`), 4) F5–F8, полировка F9–F14.

Scope (write):

- `docs/ux-audit.md` (new)
- `docs/ux/voice-recognizer-prototype.html` (new)
- `docs/ux-acceptance-scenarios.md` (new)
- `.agents/handoff-ux-redesign.md` (new)
- this `### Claude Code` block in `.agents/task-board.md`

Goal:

- grounded UX-аудит фактического web UI (`app/src/voice_recognizer/web.py`) с severity / file:line / risk / fix;
- интерактивный self-contained прототип целевого интерфейса (vanilla HTML/CSS/JS под текущий стек, без сборки), пригодный для переноса в `web.py`;
- приёмочные UX-сценарии (Given/When/Then + ручные проверки), привязанные к `review-checklist.md` и `agent-redesign-proposal.md`.

Read-only (не редактирую): `app/src/voice_recognizer/web.py` — только источник для аудита; реализацию в коде отдаю implementation-агенту через handoff.

Не пересекается с активным scope Codex (`setup_local_mac.sh`, `*.command`, `implementation-plan.md`, `local-mac-product-plan.md`, `README.md`).

### Claude Code — задача 2: бенчмарк качества vs референс

Status: DELIVERED (2026-06-27). Analysis-only, код не тронут.

Что: сравнение нашей ASR+диаризации против референсного сервиса (`references/*.docx`) на 4 одинаковых файлах (Модуль 3 ×3, Носников), наши прогоны — `outputs/pipeline/`.

Итог (кратко): ASR по полноте/скорости на уровне референса или выше (слов столько же или больше, покрытие 100%, RTF≈0.03); главный разрыв ASR — нет пунктуации/заглавных/«ё» и теряются термины/имена. Диаризация: на истинно 2-спикерных файлах совпадает (2=2); на многоголосых наши числа занижены, **но это в основном артефакт настроек** (Носников запущен с `num_speakers=2`, день2 упёрся в `max_speakers=8` при референсных 5 и 21). Сырых turn'ов pyannote достаточно (1712/2295) — проблема в кластеризации/лимитах, не в сегментации.

Deliverable: `docs/quality-benchmark-references.md`. Рекомендации завязаны на этапы 4/5 `implementation-plan.md` и на дефолты диаризации в `web.py`.

Read-only: `references/`, `outputs/pipeline/`, `app/src/...` — только источники. Не пересекается со scope Codex.

### Claude Code — задача 3: ASR-модели и пунктуация/регистр

Status: DELIVERED (2026-06-27). Analysis + ресёрч, код не тронут.

Находка (важно для implementation): мы уже возим модель пунктуации RUPunct (`.models/gigastt/punct/rupunct_small_int8.onnx`) и передаём `--punct-model-dir`, но в выводе пунктуации/регистра/«ё» нет вообще (эмпирически: punct≈0/100w, caps≈0%, ё=0 против ~31 / 62–99% / 19–30 у референса). Все читаемые тексты собираются из сырых пословных токенов (`gigastt.py:263`), пунктуированный путь не используется.

Варианты фикса: (B) заставить бинарь применять punct — проверить `gigastt transcribe --help` на Mac; (A) применить вшитый RUPunct пост-шагом в Python; (C) GigaAM v3 **e2e** (нативная пунктуация); (D) Whisper large-v3. Тесты других моделей и auto-диаризацию из песочницы запустить нельзя (Linux vs macOS-бинарь, сеть pip/HF закрыта) — протокол и скрипты для Mac в отчёте.

Deliverables: `docs/asr-model-research.md`, `docs/asr-benchmark/score.py` (dependency-free скорер читабельности — гонять при смене модели). Привязка: этап 4/5.

### Claude Code — задача 4: верификация закрытия (после правок Codex)

Status: DELIVERED (2026-06-27). Analysis-only, проверка по коду + свежим выводам.

Проверено независимо. **Закрыто и подтверждено:** пунктуация/регистр работают на новых выводах (день2 24.3 знака/100сл, 77.6% caps; Носников 21.6/74.1; было 0/0), 600s-чанки, снятие капов спикеров в config, stale-инвалидация (manifest v2), UX F1–F16 присутствуют в `web.py` (focus-visible/aria-live/alert/локализация/этапы/`/api/results`/«обработан»/группировка/elapsed/тест-фрагмент).

**Остаётся открытым (с данными):** (1) «ё» = 0 во всех выводах; (2) термины всё ещё теряются несмотря на hotwords — «НФЛО»→«Пу», «пубертат»/«Дапринт» выпали (наш день2 0/3, Носников 1/3 vs реф 1/3 и 2/3).

**Исправление по диаризации (2026-06-27):** владелец подтвердил Носников = 2 спикера → наш результат верен, у референса 5 = «виртуальные» спикеры (дрейф ID: появляются в 10:39/20:11/1:02:46). Прежний тезис «мы недосегментируем» снят. Не тюнить «вверх» под референс; мерить против истинного числа; для день2 уточнить истину (референсный 21 ненадёжен). Приоритет остатка: термины > «ё» > (диаризация: anti-drift/оценка по истине).

Deliverable: `docs/verification-2026-06-27.md` (матрица closed/partial/open + след. шаги). Приоритет остатка: диаризация > термины > «ё».

### Implementation

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 1 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation` block in `.agents/task-board.md`

Goal:

- F1: visible keyboard focus for `.btn`, `.segment`, `.file-row`, `.job-row`, `.link-chip`;
- F2: speaker-name inputs keep typed values, focus and caret during 2-second polling;
- keep diff small and do not touch pipeline or UX docs.

Checks:

- `.venv/bin/python -m compileall app/src`;
- Browser/IAB on `http://127.0.0.1:8782/`: page loads, console clean, F2 live job regression passes after 6.9s and two polling cycles, mobile 390px has no horizontal overflow;
- smoke job output was isolated to `outputs/ui-f2-smoke` and removed after verification.

### Implementation F3/F4

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 2 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F3/F4` block in `.agents/task-board.md`

Goal:

- F3: show coarse pipeline stage, elapsed time, start time and last meaningful log for queued/running jobs;
- F4: replace dead-end failed/offline messages with human-readable diagnostics and concrete next steps;
- keep the change local to the web UI; no pipeline or manifest changes.

Checks:

- `.venv/bin/python -m compileall app/src`;
- extracted rendered HTML script and ran `node --check /tmp/voice-recognizer-f3.js`;
- Browser/IAB on `http://127.0.0.1:8782/`: running job shows stage rail, elapsed/start and heartbeat; failed job shows diagnostic block with `role=alert`; desktop 1280px and mobile 390px have no horizontal overflow; console clean.

### Implementation F15/F16

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 3 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F15/F16` block in `.agents/task-board.md`

Goal:

- F15: add a disk-backed results library from `outputs/**/*.manifest.json`;
- F16: mark Inbox files that already have matching results and open those results from the UI;
- keep the change local to the web UI unless a manifest/pipeline blocker appears.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: 15 disk results found, 5 Inbox files marked processed;
- Chrome/Playwright on `http://127.0.0.1:8782/`: results library renders, Inbox processed badge opens a result, export link returns `200`, console clean, desktop/mobile no horizontal overflow.

### Implementation F5/F8

Status: DELIVERED (2026-06-26), Codex. UX implementation portion 4 from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F5/F8` block in `.agents/task-board.md`

Goal:

- F5: localize user-facing job/status labels;
- F6: add a test-fragment run mode with mm:ss parsing and presets;
- F7: show practical Inbox metadata such as duration, format and modified time;
- F8: group export files by user intent.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: Inbox files include duration/format/modified metadata;
- Chrome/Playwright on `http://127.0.0.1:8782/`: test-fragment mode and presets work, status labels are localized, export groups render, `mm:ss` parser works, console clean, desktop/mobile no horizontal overflow.

### Implementation F9/F14

Status: DELIVERED (2026-06-26), Codex. UX polish portion from `.agents/next-task-ux-implementation.md`.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F9/F14` block in `.agents/task-board.md`

Goal:

- F9: reduce polling churn where it affects reading/focus, especially log scroll;
- F10: add polite status announcements and alert semantics for failures;
- F12: make workflow step labels reflect the current active stage instead of staying decorative;
- F13/F14: keep muted text readable and add restrained transitions with reduced-motion support.

Checks:

- `.venv/bin/python -m compileall app/src`;
- Chrome/Playwright on `http://127.0.0.1:8782/`: workflow moves from settings to export, status regions expose `aria-live=polite`, log no longer auto-scrolls when reading from top, console clean, desktop/mobile no horizontal overflow.

### Implementation F11

Status: DELIVERED (2026-06-26), Codex. UX implementation for controlled batch selection.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation F11` block in `.agents/task-board.md`

Goal:

- F11: in batch mode, let the user include/exclude Inbox files before queueing;
- keep single-file and test-fragment selection unchanged;
- avoid uncontrolled heavy batch starts.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: batch mode exposes 5 checkboxes, `Все` selects all, `Ни одного` disables run, row click toggles one file and updates `4 из 5 выбрано`, console clean;
- mobile viewport 390px: no horizontal overflow.

### Implementation Disk Speaker Names

Status: DELIVERED (2026-06-26), Codex. Extend speaker labeling to disk-backed results.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Disk Speaker Names` block in `.agents/task-board.md`

Goal:

- allow applying speaker names to results opened from `outputs/**/*.manifest.json`;
- reuse existing ASR/diarization artifacts via CLI `--skip-existing`;
- refresh the result library and Inbox badges after applying names.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke: `_apply_result_speaker_names` updates a short disk result and logs `Using ASR JSON` + `Using diarization JSON`;
- in-app Browser on `http://127.0.0.1:8782/`: disk result opens, speaker name input applies via `POST /api/results/<id>/speaker-names`, label updates, console clean.

### Implementation Clip Validation

Status: DELIVERED (2026-06-26), Codex. Finish test-fragment validation UX.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Clip Validation` block in `.agents/task-board.md`

Goal:

- show readable test-fragment range after `mm:ss` parsing;
- validate selected clip against known Inbox duration;
- block run with a local message when the clip is outside the file.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: `2:00` shows `0:00-2:00`, `99:00` shows local out-of-file warning and disables run, `1:30` re-enables run, console clean;
- mobile viewport 390px: no horizontal overflow.

### Implementation Result Preview Tabs

Status: DELIVERED (2026-06-26), Codex. Add result tabs and transcript preview.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Result Preview Tabs` block in `.agents/task-board.md`

Goal:

- split result panel into Overview/Text/Speakers/Files tabs;
- load transcript preview from existing export files without changing pipeline;
- keep speaker naming and export links working inside the new structure.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: disk result opens with Text tab by default, transcript preview loads from export file, Speakers tab contains audio/name/apply controls, Files tab keeps grouped exports, Overview tab shows metadata, console clean;
- mobile viewport 390px: result tabs render after opening a result, no horizontal overflow.

### Implementation Privacy Signal

Status: DELIVERED (2026-06-26), Codex. Make local/private mode explicit in the UI.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Privacy Signal` block in `.agents/task-board.md`

Goal:

- show that the app is running locally on `127.0.0.1`;
- state that audio and transcripts stay on this Mac unless the user explicitly chooses another engine/profile later;
- keep the top bar compact on mobile.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: top bar shows `Локально · 127.0.0.1:8782` and `Аудио и тексты остаются на этом Mac`;
- mobile viewport 390px: no horizontal overflow.

### Implementation Source Freshness

Status: DELIVERED (2026-06-27), Codex. Warn when disk-backed results no longer match the source audio.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Source Freshness` block in `.agents/task-board.md`

Goal:

- detect whether a result source file is fresh, changed after processing, missing, or not safely checkable;
- surface changed/missing source state in Inbox badges, the results list, and result overview;
- avoid breaking result listing when a manifest source is absent or outside the project.

Checks:

- `.venv/bin/python -m compileall app/src`;
- API smoke with `PYTHONPATH=app/src`: 15 disk results expose `source_status=fresh`, Inbox summaries inherit source freshness;
- temporary manifest smoke: source mtime newer than manifest returns `source_status=changed`;
- in-app Browser on `http://127.0.0.1:8782/`: page loads, console clean, 15 results render, result overview shows `Исходник — исходник свежий`;
- mobile viewport 390px: no horizontal overflow, Inbox freshness tooltips remain readable.

### Implementation Rerun Stale Result

Status: DELIVERED (2026-06-27), Codex. Let users refresh a stale disk-backed result from the UI.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Rerun Stale Result` block in `.agents/task-board.md`

Goal:

- add a safe rerun endpoint for `outputs/**/*.manifest.json` results;
- reuse the result source, clip window, ASR engine, output directory and existing speaker names where available;
- show an update action for changed-source results without starting expensive work accidentally.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke with `PYTHONPATH=app/src`: `_create_result_rerun_job` preserves source/output/clip, adds `--overwrite`, and keeps existing speaker names;
- in-app Browser on `http://127.0.0.1:8782/` with a temporary ignored stale manifest: page loads, console clean, stale result shows `обновить`, opening it shows active `Обновить результат`;
- mobile viewport 390px: no horizontal overflow and rerun action remains visible;
- temporary smoke source/result files removed and test server stopped.

### Implementation Engine Readiness Signal

Status: DELIVERED (2026-06-27), Codex. Show whether the local GigaSTT/GigaAM engine is actually ready.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Engine Readiness Signal` block in `.agents/task-board.md`

Goal:

- check local GigaSTT binary and GigaAM model files without network calls;
- show a compact ready/missing status next to ASR engine selection;
- keep unavailable Handy engines disabled until their runtime backends are integrated.

Checks:

- `.venv/bin/python -m compileall app/src`;
- backend smoke with `PYTHONPATH=app/src`: `_asr_runtime_status` returns `GigaSTT готов` on this Mac;
- in-app Browser on `http://127.0.0.1:8782/`: ASR settings show `GigaSTT готов` / `GigaAM v3 найден локально`, console clean;
- mobile viewport 390px: no horizontal overflow.

### Implementation Manifest Metadata Contract

Status: DELIVERED (2026-06-27), Codex. Enrich new manifests with explicit run metadata.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation Manifest Metadata Contract` block in `.agents/task-board.md`

Goal:

- write explicit clip, device, timing and source file metadata to new manifests;
- keep old manifests readable via filename/stat fallbacks;
- use explicit manifest fields for disk-result preview, speaker renaming and rerun where available.

Checks:

- `.venv/bin/python -m compileall app/src`;
- manifest v2 smoke: `_write_manifest` stores `clip_start`, `clip_duration`, `device`, source size/mtime, created/completed timestamps and speaker constraints;
- web payload smoke: `_result_payload` reads explicit manifest fields and `_create_result_rerun_job` preserves clip/device/speaker constraints;
- source freshness smoke: unchanged v2 source is `fresh`, size-changed source becomes `changed`;
- legacy manifest smoke: old filename-based clip fallback still returns `5.0 / 10.0`.

### Implementation Result Overview Metadata

Status: DELIVERED (2026-06-27), Codex. Surface manifest run metadata in the result overview.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Result Overview Metadata` block in `.agents/task-board.md`

Goal:

- show processing date, clip window and recognized audio duration in the overview tab;
- use existing formatting helpers and keep old manifests readable;
- verify desktop/mobile rendering with the in-app browser.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: opened a result, switched to `Обзор`, saw `Обработано`, `Окно`, `Распознано`, console clean;
- mobile viewport 390px: same overview fields render, no horizontal overflow;
- test server stopped.

### Implementation Left/Middle Prototype Alignment

Status: DELIVERED (2026-06-27), Codex. Bring the Inbox and center workbench closer to Claude's UX prototype.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Left/Middle Prototype Alignment` block in `.agents/task-board.md`

Goal:

- make Inbox processed badges explicit click-through actions such as `обработан · готово →`;
- combine queue and disk results into one center `Работа` panel with `Очередь / Готовые` switching;
- keep result opening, queue state and existing APIs unchanged.

Checks:

- `.venv/bin/python -m compileall app/src`;
- in-app Browser on `http://127.0.0.1:8782/`: queue view shows only jobs/queue badges, ready-results view shows 15 results/result badge, opening a ready result keeps `Готовые` active and renders the right column, console clean;
- mobile viewport 390px: Inbox badges, center switch and ready-results list render with no horizontal overflow;
- fixed hidden-state CSS so list/badge `hidden` is not overridden by component `display` rules.

### Implementation Quality Benchmark Follow-up

Status: DELIVERED (2026-06-27), Codex. Apply the highest-ROI fixes from Claude quality audit.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/config/speaker-counts.json`
- `docs/asr-benchmark/score.py`
- `docs/asr-model-research.md`
- this `### Implementation Quality Benchmark Follow-up` block in `.agents/task-board.md`

Goal:

- preserve GigaSTT punctuation/casing from JSON `text` in timestamped speaker segments;
- explicitly run GigaSTT with `--punctuation on --itn auto`;
- remove hidden low speaker ceilings from benchmark/problem files;
- make Claude's readability scorer usable with `--terms`.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- `gigastt transcribe` smoke on `Носников 0–30s`: punctuation/casing appears in JSON `text`;
- `PYTHONPATH=app/src` smoke: segment exports inherit punctuation/casing from a punctuated GigaSTT JSON;
- `docs/asr-benchmark/score.py` works with `--terms` before or after file arguments.

### Implementation Claude Audit Closure

Status: DELIVERED (2026-06-27), Codex. Turn Claude audit recommendations into explicit project status and glossary support.

Scope:

- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/gigastt.py`
- `app/config/hotwords.txt`
- `docs/claude-audit-closure.md`
- `docs/asr-model-research.md`
- this `### Implementation Claude Audit Closure` block in `.agents/task-board.md`

Goal:

- answer whether all Claude findings/recommendations are found and closed;
- add optional GigaSTT hotwords support through `app/config/hotwords.txt`;
- document which quality recommendations are closed, partial, ready-for-heavy-run, or deferred.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- CLI help exposes `--hotwords-file` and `--hotwords-default`;
- smoke run confirms `app/config/hotwords.txt` is resolved and passed to GigaSTT;
- closure document lists UX F1-F16 as closed and quality/ASR residual work explicitly.

### Implementation Stale Artifact Invalidation

Status: DELIVERED (2026-06-27), Codex. Prevent old ASR/diarization intermediates from masking quality fixes.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/diarization.py`
- `app/src/voice_recognizer/cli.py`
- `docs/claude-audit-closure.md`
- this `### Implementation Stale Artifact Invalidation` block in `.agents/task-board.md`

Goal:

- explain and fix why UI reruns could still show no punctuation;
- annotate new GigaSTT JSON with punctuation/ITN/hotwords metadata;
- annotate new pyannote JSON with model/device/speaker constraint metadata;
- refresh stale intermediate JSON automatically when current options do not match.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- stale existing `outputs/pipeline/*gigastt.json` and `*.pyannote.json` return metadata mismatch;
- fresh 5s `transcribe-gigastt` smoke writes current ASR metadata and remains punctuated;
- synthetic diarization metadata smoke distinguishes current `2-12` from stale exact `2`.

### Implementation Short ASR Chunks For Punctuation

Status: DELIVERED (2026-06-27), Codex. Fix GigaSTT punctuation/casing loss on long ASR chunks.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `README.md`
- `docs/diarization-baseline.md`
- `docs/claude-audit-closure.md`
- this `### Implementation Short ASR Chunks For Punctuation` block in `.agents/task-board.md`

Goal:

- stop using 3600-second ASR chunks as the default, because GigaSTT punctuation disappears on long chunks;
- default to 600-second ASR chunks for files longer than 10 minutes;
- include chunking parameters in ASR JSON metadata version 2;
- include chunk start/duration in artifact file names so old hour-long chunk cache cannot be reused as a shorter chunk.

Checks:

- local smoke on `Модуль 3, день 2` showed punctuation/casing works at 60/180/300/600s and fails at 900s;
- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- ASR chunk smoke produced `part-001_0s_600s` artifacts and combined punctuation;
- old ASR JSON version 1 returns metadata mismatch.

### Implementation ASR Quality Diagnostics

Status: DELIVERED (2026-06-27), Codex. Surface ASR readability regressions in manifests and UI.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation ASR Quality Diagnostics` block in `.agents/task-board.md`

Goal:

- compute lightweight ASR quality metrics after loading GigaSTT output;
- write `asr_quality` into each manifest;
- show `Качество ASR` in the result overview;
- flag future low-punctuation/low-casing regressions without requiring manual inspection of long transcripts.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- manifest smoke includes `asr_quality.status=ok` for the refreshed long results;
- UI payload exposes `asr_quality` for disk results.

### Implementation Queue Cancellation

Status: DELIVERED (2026-06-27), Codex. Add safe stop/remove controls for accidental long jobs.

Scope:

- `app/src/voice_recognizer/web.py`
- this `### Implementation Queue Cancellation` block in `.agents/task-board.md`

Goal:

- allow queued jobs to be removed before they start;
- allow running jobs to request cancellation and terminate the child process group;
- keep canceled jobs visible with explicit `canceled` status until the user removes them;
- allow completed/failed/canceled jobs to be removed from the in-memory job list without deleting output files.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- running-cancel API smoke: `running -> canceling -> canceled`, child return code `-15`;
- queued-cancel API smoke: `queued -> canceled` before start;
- delete API smoke removes done/canceled jobs from `/api/jobs`;
- generated HTML contains cancel/delete controls and extracted JS passes `node --check`.

### Implementation Speaker Quality Diagnostics

Status: DELIVERED (2026-06-27), Codex. Surface speaker-turn fragmentation before changing diarization heuristics.

Scope:

- `app/src/voice_recognizer/gigastt.py`
- `app/src/voice_recognizer/cli.py`
- `app/src/voice_recognizer/web.py`
- this `### Implementation Speaker Quality Diagnostics` block in `.agents/task-board.md`

Goal:

- compute lightweight metrics for speaker switchiness and very short speaker turns;
- write `speaker_quality` into manifests;
- show `Качество спикеров` in the result overview;
- make phrase-splitting problems visible on long recordings without manual transcript inspection.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- synthetic speaker-island smoke returns `warning` with `short_speaker_islands`;
- existing result JSON smoke flags `Носников` and `Модуль 3, день 2` as `warning`;
- generated HTML contains `Качество спикеров` and extracted JS passes `node --check`;
- in-app Browser on `http://127.0.0.1:8790/`: page loads, console clean, disk result overview shows `Качество спикеров`; legacy manifests without `speaker_quality` show `-` until rerendered.

### Implementation Quality Manifest Refresh

Status: DELIVERED (2026-06-27), Codex. Backfill quality diagnostics for existing manifests without rerunning ASR or diarization.

Scope:

- `app/src/voice_recognizer/cli.py`
- `README.md`
- this `### Implementation Quality Manifest Refresh` block in `.agents/task-board.md`

Goal:

- add a CLI command that reads existing `*.manifest.json`, `*.gigastt.json` and `*.pyannote.json`;
- refresh `asr_quality` and `speaker_quality` fields only;
- avoid launching GigaSTT, pyannote or touching audio files;
- make old UI result cards show speaker quality after a lightweight backfill.

Checks:

- `.venv/bin/python -m compileall app/src docs/asr-benchmark/score.py`;
- CLI help exposes `refresh-quality`;
- `/tmp` manifest smoke updates `asr_quality`, `speaker_quality`, `quality_refreshed_at` and honors `--force --no-smooth-speakers`;
- `outputs/pipeline` backfill updated existing `Модуль 3, день 2` and `Носников` manifests without launching ASR/diarization;
- in-app Browser on `http://127.0.0.1:8790/`: refreshed `Модуль 3, день 2` overview shows `Качество спикеров: проверить · коротких 19.6% · смен 2.5/мин · островков 42`, console clean.

### Implementation Product Backlog Refresh

Status: DELIVERED (2026-06-27), Codex. Recenter project planning on the unfinished local-product critical path.

Scope:

- `.agents/product-backlog.md`
- `.agents/task-board.md`
- `.agents/README.md`
- `AGENTS.md`
- `docs/implementation-plan.md`
- `docs/local-mac-product-plan.md`

Goal:

- separate delivery journal from prioritized product backlog;
- identify major unfinished work from prior dialogs;
- create task IDs, statuses, scope and acceptance criteria for future agents;
- make task claim/update rules mandatory for Codex, Claude Code and review agents.

Checks:

- documentation-only change;
- verify no app code changed;
- `git diff --check`;
- secret scan on staged diff.

## Next Implementation Tasks

Use `.agents/product-backlog.md`.

Current P0 order:

1. `P0-001 Mac Install Acceptance`
2. `P0-002 Durable Job Queue`
3. `P0-003 Long-File Resume And Progress`
4. `P0-004 Batch Reliability`
5. `P0-005 Engine Registry And Model Profiles`
6. `P0-006 Speaker Quality Improvement Loop`
7. `P0-007 Local Smoke Suite`

The old Claude UX implementation list is completed enough for the current product stage and remains available as historical context in `.agents/next-task-ux-implementation.md`, `docs/ux-audit.md`, and `docs/ux-acceptance-scenarios.md`.

## Coordination Rules

- Claim one task ID from `.agents/product-backlog.md` and one write scope before editing.
- Do not edit files listed under another active owner.
- Commit small, thematic changes.
- Review before merging to `main`.
- If a task requires touching shared files like `README.md`, mention it in the handoff.
