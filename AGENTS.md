# Диктум Agent Guide

Дата: 2026-06-30.

Этот файл обязателен для Codex, Claude Code и любых других AI-агентов, работающих в этом репозитории.

## Цель продукта

Диктум - приватный local-first продукт для macOS, который превращает длинные диктофонные записи в текст с разделением по спикерам.

Ближайший ориентир качества: обычный пользователь Mac должен установить и запустить приложение локально без помощи разработчика. Self-host/server profile отложен до этапа перед публичной публикацией.

Ключевые продуктовые требования:

- локально и приватно по умолчанию;
- без обязательных регулярных платежей;
- обычные аудиофайлы с телефонов, диктофонов и петличек;
- выбор локальных AI/ASR моделей, включая сильные русскоязычные модели;
- пакетная обработка;
- практическое отсутствие лимита длины файла за счет chunking/resume;
- понятный web UI или desktop launcher для не-технического пользователя.

## Структура проекта

- `app/src/voice_recognizer/` - код приложения и pipeline.
- `app/scripts/` - запуск, остановка и установка runtime/model helpers.
- `app/config/` - примерные/проектные конфиги. Персональные конфиги должны быть local-only.
- `docs/` - документация продукта, архитектуры и исследований.
- `.agents/` - координация AI-агентов, task board, промпты, приемка.
- `Inbox/` и `inbox/` - локальные пользовательские аудиофайлы, не коммитить.
- `outputs/`, `.cache/`, `.models/`, `.venv/` - runtime/generated/local-only, не коммитить.

Приложение уже перенесено в `app/`. Корень репозитория остается рабочей зоной проекта и местом для локальных пользовательских данных (`inbox/`, `outputs/`, `.models/`, `.cache/`, `.venv`, `.env`).

Публичное имя продукта: `Диктум`. Технические идентификаторы `voice_recognizer`, `voice-recognizer` и `VOICE_RECOGNIZER_*` пока сохраняются для совместимости; не переименовывать Python-пакет/модуль без отдельной миграционной задачи.

## Приватность и безопасность

Никогда не коммитить:

- `.env`, реальные токены и API keys;
- аудиозаписи пользователя;
- generated transcripts, speaker samples, cache, model files;
- приватные `.docx`/черновики из корня;
- абсолютные пути к личным данным, если они не нужны для локального запуска.

Перед коммитом проверить:

```bash
git status --short --ignored
git diff --cached --check
git diff --cached | rg --pcre2 -n "hf_(?!your_token_here)[A-Za-z0-9]{12,}|sk-[A-Za-z0-9]{12,}|OPENAI_API_KEY=.*[A-Za-z0-9]{8}"
```

Код не должен отправлять аудио, текст или токены во внешние сервисы без явного пользовательского выбора.

## Git workflow

- `main` - локальный стабильный baseline.
- Новые работы делать в ветках `codex/<topic>`, `claude/<topic>` или `agent/<topic>`.
- Не работать нескольким агентам над одним файлом без явного ownership.
- Не делать большие рефакторы вместе с продуктовыми изменениями.
- Не откатывать чужие изменения.
- Перед коммитом перечислить, что изменено и что проверено.

Если агент не уверен, что его задача конфликтует с другой, он должен остановиться и записать вопрос в `.agents/task-board.md`, а не переписывать соседний код.

## Task accounting workflow

Источник правды по следующим задачам: `.agents/product-backlog.md`.

`.agents/task-board.md` используется как:

- журнал доставленных delivery-блоков;
- место для активного claim;
- место для вопросов/блокеров между агентами.

Перед любой нетривиальной работой агент обязан:

1. Прочитать `.agents/product-backlog.md` и `.agents/task-board.md`.
2. Выбрать один task ID из backlog, например `P0-002 Durable Job Queue`.
3. Добавить или обновить active claim в `.agents/task-board.md`: агент, task ID, scope, файлы, acceptance, время.
4. Работать только в заявленном scope. Если нужен новый scope, сначала обновить claim.
5. В конце добавить delivery block в `.agents/task-board.md`: что сделано, какие файлы, какие проверки, что не проверено, риски.
6. Если задача завершена, обновить статус в `.agents/product-backlog.md` или явно записать, почему осталась `READY/BLOCKED`.

Запрещено:

- брать "мелкую удобную" задачу, если она не двигает текущий P0 backlog или пользователь явно не попросил;
- оставлять claim в состоянии active после коммита;
- смешивать разные P0 задачи в одном diff без необходимости;
- делать крупный кодовый refactor под видом task accounting.

## Роли

### Implementation agent

Пишет код и тесты в заранее выбранном scope. Обязан проверять запуск/compile и не оставлять тестовые серверы в фоне.

### UX/product agent

Пишет предложения и acceptance criteria. По умолчанию меняет только `docs/` или `.agents/`, не код.

### Review agent

Проверяет diff. Не исправляет код, если задача не просит. Ответ начинает с findings по серьезности.

## Приоритеты ближайших задач

Актуальный порядок находится в `.agents/product-backlog.md`.

Текущий operational order:

1. `P0-008 Installable Layout And Update-Safe Data Split` / private trial distribution readiness.
2. `P0-003 Long-File Resume And Progress` only if trial feedback or release acceptance exposes a blocker.
3. `P0-004 Batch Reliability` only if trial feedback or release acceptance exposes a blocker.
4. `P0-009 Release Channel And Manual Updater` after the first private trial artifact is stable.
5. `P0-006 Speaker Quality Improvement Loop` after real-user feedback identifies speaker quality as the main blocker.
6. `P0-010 Transcript Quality Repair And Postprocessing` after real-user feedback identifies text quality as the main blocker.
7. `P0-005 Engine Registry And Model Profiles` deferred until an alternate engine beats the current baseline or users clearly need backend choice.

`P0-001 Mac Install Acceptance` delivered for the private trial; only regressions/packaging polish should be tracked there.
`P0-007 Local Smoke Suite` delivered; run `app/scripts/smoke_local.sh` before release/trial-pack steps and meaningful code changes.

Current release decision: stop active ASR-model exploration for the private trial. Ship the strongest current baseline (`gigastt-gigaam-v3` plus edited exports), collect feedback from real users, then choose the next quality or reliability investment from evidence.

Self-host/Docker/Cloud отложены до отдельного будущего этапа.

## Проверки

Минимум для Python-изменений:

```bash
.venv/bin/python -m compileall app/src
```

Для web UI изменений:

- поднять локальный сервер на тестовом порту;
- открыть страницу в браузере;
- проверить console errors;
- остановить сервер после проверки.

Для launcher/setup изменений:

- проверить `zsh -n app/scripts/*.sh`;
- проверить сценарии: свободный порт, занятый порт, остановка сервера.

## Definition of Done

- Изменение двигает локальный/private Mac-продукт.
- Пользовательский путь не обрывается без понятного next step.
- Приватные данные не попали в git.
- Есть понятная проверка результата.
- Документация/инструкции обновлены, если изменился способ запуска или использования.
