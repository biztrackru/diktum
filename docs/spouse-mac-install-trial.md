# Spouse Mac Install Trial

Дата: 2026-06-27.

Цель: проверить, может ли обычный пользователь на Apple Silicon Mac распаковать Диктум, настроить его двойным кликом и запустить локальный web UI без помощи разработчика.

## Что передаем

Собрать архив на рабочем Mac:

```bash
app/scripts/build_install_pack.sh
```

Передавать файл из `.dist/Диктум Trial <timestamp>.zip`.

Архив намеренно не содержит:

- `.env` и токены;
- `.venv`;
- `.models`;
- `tools/bin`;
- аудио из `Inbox/`;
- результаты из `outputs/`;
- generated transcripts или приватные черновики.

HF token не вкладывать в zip. Для теста на семейном Mac лучше создать отдельный Hugging Face read-only token, например `dictum-family-test`, передать его отдельно от архива и вставить в setup скрытым вводом. После проверки token можно отозвать в Hugging Face settings.

macOS Gatekeeper может блокировать `.command` файлы из zip сообщением `не удалось проверить на наличие вредоносного ПО` и предлагать `Переместить в корзину`. Текущий trial pack не подписан Apple Developer ID и не notarized. Малый workaround: один раз запустить `Разблокировать Диктум.command`, который снимает quarantine-метку со всей распакованной папки. Если macOS блокирует даже helper, fallback через Terminal:

```bash
xattr -dr com.apple.quarantine "/path/to/Диктум Trial"
```

Путь удобнее не печатать руками: вставить `xattr -dr com.apple.quarantine ` с пробелом в конце, перетащить папку из Finder в Terminal и нажать Enter.

GigaSTT / GigaAM v3 тоже не входит в zip. Это основной локальный ASR-движок для русского языка: он превращает аудио в текст. Setup скачивает binary в `tools/bin/gigastt`, модели в `.models/gigastt/` и RUPunct-файлы в `.models/gigastt/punct/` на этапе `4/5: GigaSTT/GigaAM v3`. Для этого нужен интернет; если загрузка оборвалась, запустить setup повторно.

Setup и doctor пишут локальные логи в `logs/`. Если web UI после setup все еще пишет `GigaSTT не настроен`, запустить `Проверить Диктум.command` и переслать разработчику только:

- `logs/setup-latest.log`;
- `logs/doctor-latest.log`.

Не пересылать `.env`, аудио из `Inbox/`, результаты из `outputs/` или полный архив рабочей папки.

Первый тестовый файл после чистой установки может дольше обычного стоять на этапе `Диаризация`: pyannote впервые готовит локальный cache модели разделения спикеров. В техническом журнале задачи должны быть строки `Diarization / pyannote: ...`; это нормальный признак живого процесса.

## Подготовка целевого Mac

Желательно записать:

- модель Mac и чип;
- версия macOS;
- установлен ли Homebrew до теста;
- установлен ли Python до теста;
- есть ли Hugging Face аккаунт с принятыми условиями pyannote;
- подготовлен ли отдельный read-only HF token для теста;
- достаточно ли места и времени на загрузку GigaSTT/GigaAM v3 моделей.

Перед установкой token можно подготовить так:

1. Открыть https://huggingface.co/pyannote/speaker-diarization-community-1.
2. Войти в Hugging Face и принять условия доступа к pyannote.
3. Создать read-only token на https://huggingface.co/settings/tokens.
4. Передать token отдельно от zip. Предпочтительно через password manager или прямую вставку на целевом Mac; не пересылать reusable token в общем чате вместе с архивом.

## Сценарий A: почти чистый Mac

1. Распаковать zip в обычную папку, например `~/Applications/Диктум Trial`.
2. Открыть папку в Finder.
3. Если macOS блокирует `.command`, запустить `Разблокировать Диктум.command` или Terminal fallback выше.
4. Дважды кликнуть `Настроить Диктум.command`.
5. Если macOS все еще блокирует запуск, открыть через правый клик -> `Open` или System Settings -> Privacy & Security -> `Open Anyway`.
6. Прочитать каждый вопрос setup и выбрать безопасный happy path:
   - установить Homebrew, если его нет;
   - установить ffmpeg;
   - установить Python 3.12, если нет совместимого Python;
   - создать `.venv`;
   - установить Python dependencies;
   - создать `.env`;
   - вставить read-only HF token скрытым вводом, когда setup объяснит шаг;
   - скачать GigaSTT/GigaAM v3 на этапе 4/5.
7. В конце setup согласиться запустить Диктум, либо закрыть окно и запустить вручную `Запустить Диктум.command`.
8. Убедиться, что браузер открыл `http://127.0.0.1:8765/`.
9. Загрузить короткий безопасный тестовый аудиофайл через web UI.
10. Запустить `Тест-фрагмент` на 30-120 секунд.
11. Дождаться результата или понятной ошибки с next step.
12. Нажать `Остановить Диктум.command` и подтвердить остановку.

## Сценарий B: semi-clean Mac

Если Homebrew/Python уже есть:

1. Сначала запустить `Проверить Диктум.command`.
2. Записать все `[FAIL]` и `[WARN]`.
3. Запустить `Настроить Диктум.command`.
4. После setup снова запустить `Проверить Диктум.command`.
5. Считать сценарий успешным, если doctor показывает `failures=0`.

## Что считать успехом

- Пользователь не вводит команды Terminal вручную.
- Setup/doctor не печатает HF token.
- Если macOS Gatekeeper блокирует `.command`, helper или Terminal fallback снимают quarantine без ручного подтверждения каждого launcher.
- Setup объясняет, что HF token нужен только для pyannote/speaker diarization, и что его можно пропустить до отдельной настройки спикеров.
- Doctor объясняет отсутствующие зависимости понятным next step.
- Doctor видит `tools/bin/gigastt` и модели `.models/gigastt/`, либо явно просит повторить этап `4/5: GigaSTT/GigaAM v3`.
- Start открывает браузер на `127.0.0.1:8765`.
- Если порт занят, start предлагает остановить старый сервер, открыть текущий или выйти.
- Stop находит и останавливает сервер.
- В web UI можно загрузить файл и поставить тест-фрагмент в очередь.
- Ошибки модели/токена/ffmpeg показывают человекочитаемые инструкции.

## Если Homebrew не докачивает ffmpeg

Симптомы:

- `Failed to download resource`;
- `curl: (28) SSL connection timeout`;
- `curl: (35) LibreSSL SSL_connect`;
- ссылки вида `https://ghcr.io/v2/homebrew/core/...`.

Что делать:

1. Остановить текущий setup через `Ctrl+C`, если он долго повторяет ошибки.
2. Не переходить к Python dependencies, HF token и GigaSTT/model download в этом же прогоне.
3. Проверить обычные причины сетевого сбоя: стабильный Wi-Fi, VPN/proxy/adblock, дата/время macOS.
4. Попробовать другую сеть или мобильный hotspot.
5. Снова запустить `Настроить Диктум.command`.

Это не утечка данных Диктум. На этом шаге Homebrew скачивает ffmpeg и его зависимости. Уже скачанные части обычно переиспользуются при повторном запуске.

## Что записывать как blocker

- macOS не дает запустить `.command`, а инструкция через правый клик не помогает.
- `Разблокировать Диктум.command` и Terminal fallback не снимают Gatekeeper-блокировку.
- Setup требует непонятную ручную команду.
- Homebrew/ffmpeg/Python installation падает без понятного next step.
- `.env` создается, но token виден в логе.
- GigaSTT download/model setup не объясняет размер/назначение или падает без следующего шага.
- Start не открывает браузер.
- Stop не находит сервер.
- UI открывается, но запуск тест-фрагмента дает raw traceback без диагноза.

## После теста

Собрать короткий отчет:

```text
Mac:
macOS:
Что было установлено до теста:
Setup result:
Doctor result:
Start result:
Web UI result:
Test fragment result:
Stop result:
Blockers:
Screenshots/log excerpts without tokens:
```

Не отправлять `.env`, аудио, generated transcripts, `.models`, `.venv` или полный log с приватными путями/токенами.
