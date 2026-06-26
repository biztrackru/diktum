# Next Task — UX implementation (from Claude UX track)

Дата: 2026-06-26. Подготовил: Claude (UX/product track). Для: implementation-агента.

UX-дорожка закрыта (аудит + прототип + приёмочные сценарии). Это бриф на перенос находок в код. Реализуется порциями, каждая — отдельный тематический diff. Не брать всё сразу.

## Контекст (прочитать перед стартом)

- `.agents/handoff-ux-redesign.md` — передача, приоритеты, **Data contract** для библиотеки результатов.
- `docs/ux-audit.md` — находки F1–F16 (`severity / file:line / risk / fix`) + оценка объёма.
- `docs/ux/voice-recognizer-prototype.html` — эталон целевого поведения (открыть в браузере).
- `docs/ux-acceptance-scenarios.md` — приёмка S1–S10 + матрица покрытия.
- `app/src/voice_recognizer/web.py` — единственный файл реализации для порций 1–2.

## Порядок порций

1. **F1 + F2** — `web.py`. Первый, самый безопасный diff. ← задача ниже.
2. **F3 + F4** — `web.py`. Этапы пайплайна + elapsed; диагностируемые ошибки.
3. **F15 + F16** — `web.py` (+ опц. `cli.py`, согласовать). Библиотека результатов из `outputs/` + бейдж «обработан → готово». Контракт — в handoff.
4. **F5–F8**, затем полировка **F9–F14**.

---

## Порция 1 (взять первой): F1 + F2

Write scope: **только `app/src/voice_recognizer/web.py`**.

### Что сделать

F1 — видимый фокус с клавиатуры:
- добавить `:focus-visible { outline:2px solid var(--accent); outline-offset:2px }` для `.btn`, `.segment`, `.file-row`, `.job-row`, `.link-chip` (сейчас `outline:none` на input без замены для кнопок/строк, `web.py:415`);
- у input оставить существующий focus-ring (`web.py:419-422`).

F2 — ввод имён спикеров не должен стираться 2-секундным polling'ом:
- сделать поля имён controlled от состояния (значение из последнего ввода), а не пересоздавать их из payload при каждом render;
- при необходимости перерисовки результата сохранять значение и каретку сфокусированного поля (паттерн `withPreservedFocus` в прототипе) либо не перерисовывать блок, пока поле в фокусе;
- эталон — функции `renderResult`/`withPreservedFocus` и обработчик `input` в `docs/ux/voice-recognizer-prototype.html`.

### Приёмка (из `docs/ux-acceptance-scenarios.md`)

- S4, регрессионный тест F2: на done-задаче печатать имя ≥6 c (≥2 цикла polling) — текст и каретка не теряются.
- S8: focus-visible виден на всех кнопках, сегментах, строках Inbox/очереди, chip'ах; Tab-порядок = визуальный.
- `.agents/review-checklist.md` → «Polling does not wipe user edits in speaker name fields».

### Проверки

```bash
.venv/bin/python -m compileall app/src
VOICE_RECOGNIZER_PORT=8782 VOICE_RECOGNIZER_OPEN_BROWSER=0 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/start_server.sh
# открыть http://127.0.0.1:8782 : проверить фокус с Tab и F2-регрессию, console без ошибок
VOICE_RECOGNIZER_PORTS=8782 VOICE_RECOGNIZER_PAUSE_ON_EXIT=0 app/scripts/stop_server.sh
```

### Definition of Done

- F2-регрессия проходит; фокус виден на всех контролах; console чистая; приватные данные не в git; diff маленький и тематический (только `web.py`); `review-checklist.md` для UI — зелёный.

### Координация

- Перед стартом взять задачу на `.agents/task-board.md` (завести `### Implementation` со scope `web.py`), работать в ветке `claude/<topic>` или `agent/<topic>`.
- Не трогать активный scope Codex (doctor/setup-скрипты, `implementation-plan.md`, `README.md`).
- Порция 3 (F15/F16), если затронет `cli.py` (формат манифеста), требует согласования с владельцем pipeline.

---

## Готовый промпт для следующего агента (скопировать)

```text
Ты implementation-агент проекта Voice Recognizer. Прочитай AGENTS.md, CLAUDE.md,
.agents/handoff-ux-redesign.md, docs/ux-audit.md и docs/ux-acceptance-scenarios.md,
открой эталон docs/ux/voice-recognizer-prototype.html.

Возьми ТОЛЬКО порцию 1 (F1 + F2) из .agents/next-task-ux-implementation.md.
Write scope: только app/src/voice_recognizer/web.py.

F1: добавь видимый :focus-visible на .btn/.segment/.file-row/.job-row/.link-chip.
F2: сделай поля имён спикеров controlled от состояния и сохраняй фокус/каретку при
2-секундном polling (паттерн из прототипа), чтобы ввод имени не стирался.

Прогон: .venv/bin/python -m compileall app/src; подними сервер на порту 8782,
проверь Tab-фокус и F2-регрессию (печатать имя ≥6 c), убедись что console чистая,
останови сервер. Diff держи маленьким и только в web.py.

Перед стартом застолби задачу на .agents/task-board.md (блок ### Implementation,
scope web.py) и работай в ветке claude/<topic> или agent/<topic>. Не трогай scope Codex.
По завершении заполни .agents/handoff-template.md.
```
