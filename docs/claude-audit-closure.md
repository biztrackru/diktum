# Claude Audit Closure

Дата: 2026-06-27.

Этот документ фиксирует статус находок и рекомендаций Claude Code после UX-аудита и quality-аудита.

## Источники

- `docs/ux-audit.md` — UX-находки F1-F16.
- `docs/quality-benchmark-references.md` — сравнение с референсными расшифровками.
- `docs/asr-model-research.md` — ASR/readability research.
- `.agents/task-board.md` — implementation history.

## UX-аудит

Все UX-находки F1-F16 закрыты implementation-коммитами и записаны в `.agents/task-board.md`.

| Находки | Статус | Где закрыто |
|---|---|---|
| F1-F2 | Closed | `Implementation` |
| F3-F4 | Closed | `Implementation F3/F4` |
| F5-F8 | Closed | `Implementation F5/F8`, `Implementation Clip Validation`, `Implementation Result Preview Tabs` |
| F9-F14 | Closed | `Implementation F9/F14`, `Implementation F11` |
| F15-F16 | Closed | `Implementation F15/F16`, manifest/source freshness/result rerun follow-ups |
| Prototype left/middle alignment | Closed | `Implementation Left/Middle Prototype Alignment` |

Остаточный риск: ручная UX-приемка всегда полезна после крупных visual changes, но известных незакрытых UX-пунктов Claude-аудита сейчас нет.

## Quality benchmark

| Рекомендация | Статус | Что сделано | Что осталось |
|---|---|---|---|
| R1. Пунктуация/регистр | Mostly closed | GigaSTT вызывается с `--punctuation on --itn auto`; пунктуация/регистр из JSON `text` переносятся на timestamped words, поэтому новые clean/timeline/Markdown exports становятся читаемыми. | `ё` не восстановлена, это отдельный yoficator/glossary step. Старые outputs надо пересчитать или переэкспортировать. |
| R2. Дефолты диаризации | Closed for config/UI path | `app/config/speaker-counts.json`: обучающие записи подняты до `max_speakers=24`, Носников больше не зажат `num_speakers=2`; UI уже показывает режим/диапазон спикеров. | После честного перепрогона можно тюнить пороги, если кластеризация все еще слипает голоса. |
| R3. Честный перепрогон | Ready, not executed | CLI/UI теперь используют новые лимиты; команды есть в отчете. | Нужно запустить тяжелые full-run jobs для Носникова и день2, затем сравнить `speaker_count` с референсом. |
| R4. Тюнинг кластеризации | Deferred | Базовая причина `num=2/max=8` устранена. | Делать только после R3, если auto-перепрогон все еще слипает голоса. |
| R5. Имена и термины | Partially closed | Добавлен `app/config/hotwords.txt`; CLI автоматически применяет его как GigaSTT `--hotwords-file`; в manifest пишется hotwords metadata. | Проверить на длинных файлах, расширить глоссарий под домены пользователя; built-in `--hotwords-default` оставлен ручным из-за неоднозначного smoke. |
| R6. Регрессионный фикс-сет | Partially closed | Добавлен `docs/asr-benchmark/score.py`, исправлен `--terms`; документы описывают протокол сравнения. | Автоматический WER/docx benchmark не внедрен: в текущем venv нет `python-docx`/`jiwer`, а референсы приватные и ignored. |

## ASR/readability research

| Рекомендация | Статус | Комментарий |
|---|---|---|
| R1. Включить punctuation/casing | Closed except `ё` | Выбран дешевый путь B: флаги GigaSTT + перенос display text на words. |
| R2. Сравнить GigaAM v3 e2e / Whisper | Deferred | Это осознанный model-benchmark этап, не блокирует текущий local product. |
| R3. Финализировать диаризацию через auto | Ready, not executed | Нужны тяжелые прогоны с новыми speaker limits. |
| R4. `ё` и термины | Partially closed | Термины покрыты hotwords-файлом; `ё` пока открыта. |
| R5. Закрепить regression scoring | Partially closed | Есть скорер читабельности и протокол; полноценный автоматический benchmark позже. |

## Следующий честный шаг

Запустить тяжелый перепрогон:

```bash
.venv/bin/python -m voice_recognizer.cli process "Inbox/Носников дапринт + нфло.m4a" \
  --output-dir outputs/bench-auto --asr-engine gigastt-gigaam-v3 --device auto --min-speakers 2 --max-speakers 12 --overwrite

.venv/bin/python -m voice_recognizer.cli process "Inbox/Модуль 3, день 2, 1ч.m4a" \
  --output-dir outputs/bench-auto --asr-engine gigastt-gigaam-v3 --device auto --min-speakers 2 --max-speakers 24 --overwrite
```

После этого:

```bash
python3 docs/asr-benchmark/score.py outputs/bench-auto/*.clean.txt --terms "НФЛО,пубертат,емейл"
python3 - <<'PY'
import json, glob
for path in sorted(glob.glob("outputs/bench-auto/*.manifest.json")):
    data = json.load(open(path))
    print(data["speaker_count"], data["source"], data.get("speaker_constraints"))
PY
```
