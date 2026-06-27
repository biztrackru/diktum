# Local Mac Product Plan

Дата: 2026-06-27.

## Цель

Сделать Voice Recognizer локальным Mac-продуктом, который обычный пользователь может установить и запустить без помощи разработчика.

Практический ориентир: пользователь получает папку или установочный пакет, кликает setup/launch файлы, отвечает на понятные вопросы, загружает запись через браузер и получает текстовый результат.

Целевой первый пользовательский Mac: Apple Silicon M5, 32 GB RAM.

## Что считаем готовым локальным продуктом

- Есть double-click setup для macOS.
- Setup проверяет окружение и объясняет проблемы обычным языком.
- Setup может устанавливать Homebrew/ffmpeg/Python-зависимости только после явного вопроса с объяснением.
- Пользователь не обязан открывать Terminal вручную.
- Пользователь не обязан знать Python, venv, pip, ffmpeg, HF token, pyannote или GigaSTT.
- Модели и зависимости устанавливаются автоматически там, где это юридически и технически безопасно.
- Если нужна ручная загрузка модели/токена, UI или setup дает прямую инструкцию и проверяет результат.
- Для первых приватных пользователей допустимо использовать один read-only HF token автора, если он хранится только в локальном `.env` и не попадает в git.
- Запуск и остановка сервера делаются double-click ярлыками.
- Web UI открывается сам.
- В UI можно загрузить аудиофайл, запустить обработку, назвать спикеров и открыть результаты.
- Приватность по умолчанию: данные остаются на Mac.

## Не делаем до этого этапа

- Docker/self-host profile.
- Cloud deployment.
- Публичный GitHub release.
- Лендинг.
- Полную SwiftUI/macOS-native перепись.

## Текущая структура

Приложение отделено от рабочей зоны проекта:

```text
Voice Recognizer/
  app/src/voice_recognizer/     # код приложения
  app/scripts/                  # setup/start/stop helpers
  app/config/                   # проектные конфиги и примеры
  docs/                     # документация
  .agents/                  # координация AI-агентов
  Inbox/ или inbox/         # локальные аудио, не git
  outputs/                  # результаты, не git
  .cache/                   # временные файлы, не git
  .models/                  # модели, не git
  .venv/                    # Python runtime, не git
```

Код программы уже отделен от рабочих файлов в `app/src/voice_recognizer/`. Рабочие файлы агентов вынесены в `.agents/`.

Следующий возможный перенос в отдельную installable layout стоит делать отдельным шагом:

```text
VoiceRecognizerLocal/
  Voice Recognizer.command
  Stop Voice Recognizer.command
  Настроить Voice Recognizer.command
  app/
    src/
    scripts/
    config/
    pyproject.toml
  user-data/
    Inbox/
    outputs/
    models/
```

Такой packaging-перенос затронет пути `.venv`, launchers, cache, outputs и документацию, поэтому его нужно делать отдельной миграцией.

## Setup UX

Первый setup должен идти по шагам:

1. Проверка macOS и архитектуры Apple Silicon.
2. Проверка Python.
3. Создание `.venv`.
4. Установка Python dependencies.
5. Проверка `ffmpeg`/`ffprobe`.
6. Установка или инструкция установки `ffmpeg`, если его нет.
7. Проверка GigaSTT binary.
8. Проверка GigaAM/GigaSTT model files.
9. Проверка pyannote/HF token без печати токена.
10. Мини-smoke: импорт Python modules, доступность CLI, запуск web help.
11. Предложение открыть Voice Recognizer.

Каждый шаг должен иметь состояния:

- `ok`;
- `can fix automatically`;
- `needs user action`;
- `failed with next step`.

## Model Download Strategy

Модели большие и могут иметь лицензионные условия, поэтому setup должен быть честным:

- показывать размер и назначение модели;
- спрашивать перед загрузкой;
- хранить модели локально в `.models/`;
- поддерживать ручное размещение файлов;
- проверять наличие файлов после ручного шага;
- не коммитить модели.

Для pyannote нужен token/acceptance на Hugging Face. Setup не должен печатать token и не должен сохранять его никуда, кроме локального `.env`.

## Installer Path Options

### Вариант A. Минимальный сейчас

- `Настроить Voice Recognizer.command`;
- текущие `Запустить` и `Остановить`;
- local web UI.

Плюсы: быстрее всего, меньше переписывания.
Минусы: это еще папка проекта, а не красивое `.app`.

### Вариант B. Полированный folder app

- отдельная installable папка;
- `app/` для кода;
- `user-data/` для аудио/outputs/models;
- setup пишет понятный status report.

Плюсы: ближе к реальному продукту.
Минусы: нужна миграция путей.

### Вариант C. Native wrapper позже

- Tauri или SwiftUI wrapper;
- web UI и Python backend остаются ядром;
- wrapper запускает backend и открывает UI.

Плюсы: лучший UX.
Минусы: рано для текущего состояния pipeline.

## Ближайшее решение

Идем по варианту A, затем B.

Текущий статус:

- добавить `app/scripts/setup_local_mac.sh`; готово;
- добавить `Настроить Voice Recognizer.command`; готово;
- добавить команду/скрипт `doctor`; готово;
- сделать человекочитаемый отчет окружения; готово на уровне скрипта, требуется clean Mac acceptance;
- развивать текущую структуру `app/` без смешивания кода приложения и локальных пользовательских данных; готово как dev/product hybrid.

Следующий implementation scope: `P0-001 Mac Install Acceptance` из `.agents/product-backlog.md`.

Не закрыто:

- прогон setup/doctor/start/stop на чистом или почти чистом пользовательском Mac;
- проверка сценария без ручного Terminal;
- решение, оставляем ли dev-folder layout для первых пользователей или переходим к `VoiceRecognizerLocal/app + user-data`;
- короткая инструкция "что делать, если модель/токен/ffmpeg не настроены" прямо в setup/doctor output и README.

## Acceptance Criteria

- На чистом или почти чистом Mac пользователь запускает setup двойным кликом.
- Если чего-то нет, setup говорит, что именно и как исправить.
- После setup пользователь запускает server double-click.
- Браузер открывается на `127.0.0.1`.
- Пользователь может загрузить `.m4a` через UI.
- Если модели/токен не готовы, ошибка содержит понятный next step.
- Никакие личные аудио, токены и outputs не попадают в git.
