# Voice Recognizer

Локальное приложение для транскрибации диктофонных записей с iPhone: русский ASR, разделение по спикерам, удобный экспорт в текстовые форматы.

## Цель

Собрать приватный локальный конвейер, который принимает запись интервью, обучения или встречи и выдает полноценную текстовую версию:

- текст на русском языке с пунктуацией;
- реплики, сгруппированные по спикерам;
- таймкоды для проверки и редактирования;
- экспорт в Markdown, TXT, DOCX и при необходимости SRT/VTT;
- возможность переименовывать и объединять спикеров после распознавания.

## Приватность и безопасность

Voice Recognizer спроектирован как локальный однопользовательский инструмент.

**Что остаётся на вашем Mac (никуда не отправляется):**

- ваши аудиозаписи (`Inbox/`);
- все расшифровки и результаты (`outputs/`);
- ваш HF-токен (`.env`, хранится с правами `chmod 600`).

**Что обращается к сети — и когда:**

- *установка* (`Настроить…`) скачивает Homebrew/ffmpeg/Python-пакеты, бинарь
  GigaSTT (с GitHub, проверка SHA-256) и модель RUPunct (с Hugging Face,
  проверка SHA-256);
- *первый запуск диаризации* один раз скачивает модель pyannote с huggingface.co
  под вашим токеном (уходит только запрос модели — **не аудио**);
- после установки обработка идёт офлайн.

**Сетевая модель:** веб-интерфейс слушает только `127.0.0.1` (localhost) и не
имеет аутентификации — он не рассчитан на доступ из сети. Сервер проверяет
заголовки `Host`/`Origin`, чтобы другие сайты в браузере не могли обратиться к
локальному серверу (защита от DNS-rebinding и CSRF). Не открывайте его на
`0.0.0.0`/в LAN без доверенной сети.

**Происхождение ASR:** бинарь GigaSTT и модель пунктуации берутся из публичных
репозиториев пользователя `ekhodzitsky` (GitHub/Hugging Face) и пиннятся по
SHA-256 в `app/scripts/setup_gigastt.sh`. Модели GigaAM v3 публикует
Salute/Sber.

Сообщить об уязвимости: см. [`SECURITY.md`](SECURITY.md). Аудит безопасности:
`docs/security-audit-2026-06-28.md`.

## Текущее окружение

- MacBook на Apple M4 Max, 48 GB RAM.
- macOS 26.5.1.
- Python 3.12.6 доступен.
- Homebrew доступен.
- `ffmpeg` и `ffprobe` доступны через CLI и используются для подготовки WAV.
- На компьютере уже установлены LM Studio, Handy с Whisper Large и GigaAM, а также Whisper Transcription с Whisper Large V3 Turbo.

## Уточненные требования

- Типичные записи: десятки минут, иногда 1.5-2 часа.
- Сценарии: интервью, диалоги, обучения, вебинары, семинары, вопросы участников.
- Приоритет: максимальное качество важнее скорости.
- Модели можно загружать вручную; разовая загрузка и токены для доступа к моделям допустимы.
- Первый интерфейс: локальная web-страница в браузере или CLI-прототип.
- Форматы результата: Markdown/TXT/DOCX, позже можно добавить SRT/VTT/JSON.
- На первом этапе достаточно стабильной маркировки `Спикер 1`, `Спикер 2`, `Спикер 3` внутри одной записи.

## Рабочие документы

- `docs/product-requirements.md` - текущие продуктовые требования: local-first/self-host, приватность, batch, выбор моделей, длинные файлы.
- `docs/implementation-plan.md` - ближайший план реализации без публичной упаковки и лендинга.
- `docs/local-mac-product-plan.md` - путь к локальному Mac-продукту для обычного пользователя.
- `docs/agent-workflow.md` - правила работы нескольких AI-агентов, prompts для UX/redesign и review ролей.
- `AGENTS.md` и `CLAUDE.md` - корневые инструкции для Codex, Claude Code и других AI-агентов.
- `.agents/` - task board, prompts и checklist для параллельной работы агентов.
- `docs/user-scenarios.md` - основные пользовательские сценарии локального web-сервиса.
- `docs/architecture.md` - текущая архитектурная гипотеза pipeline.

## Тестовые файлы

| Файл | Формат | Каналы | Частота | Длительность |
| --- | --- | --- | --- | --- |
| `Inbox/Оля коридоре а сайта восторга.m4a` | AAC `.m4a` | stereo | 48 kHz | 27:46 |
| `Inbox/Модуль 3, день 1, 5ч.m4a` | AAC `.m4a` | stereo | 48 kHz | 26:43 |
| `Inbox/Носников дапринт + нфло.m4a` | AAC `.m4a` | stereo | 48 kHz | 1:20:22 |

## Рабочая гипотеза

Первый прототип стоит строить как модульный локальный пайплайн:

1. Импорт аудио: `.m4a`, `.wav`, `.mp3`, возможно `.mp4`.
2. Нормализация: конвертация в mono/16 kHz WAV через `ffmpeg`.
3. ASR: GigaAM v3 для русского языка.
4. Диаризация: pyannote Community-1 или Apple Silicon-ориентированная обвязка вокруг pyannote.
5. Склейка: привязка слов/сегментов ASR к интервалам спикеров.
6. Постобработка: пунктуация, объединение коротких реплик, пользовательские имена спикеров.
7. Экспорт: Markdown/TXT/DOCX/SRT/VTT.
8. UI: сначала CLI или простая локальная web-форма, затем полноценное macOS-приложение при необходимости.

## Быстрый старт текущего прототипа

Самый простой путь на macOS:

1. Дважды кликнуть `Настроить Voice Recognizer.command`.
2. Разрешить установку Homebrew/ffmpeg/Python-зависимостей/моделей, если setup спросит и объяснит зачем.
3. Дважды кликнуть `Проверить Voice Recognizer.command`, чтобы получить отчет по Python, ffmpeg, моделям, `.env`, pyannote и портам.
4. Убедиться, что `.env` содержит `HF_TOKEN` для pyannote/speaker diarization. Setup объяснит, где взять read-only token, примет его скрытым вводом и сохранит локально.
5. Дважды кликнуть `Запустить Voice Recognizer.command`.

## Пробный установочный пак для другого Mac

Для первой попытки установки на Mac другого пользователя собрать чистый trial pack:

```bash
app/scripts/build_install_pack.sh
```

Скрипт создаст `.dist/Voice Recognizer Trial <timestamp>.zip`.

В архив входят launchers, `app/`, README и install-checklist. В архив намеренно не входят `.env`, `.venv`, `.models`, `.cache`, `tools/bin`, аудио из `Inbox/` и результаты из `outputs/`.

HF token нужен только для pyannote, то есть для разделения записи по спикерам. Для семейной проверки лучше создать отдельный Hugging Face read-only token, передать его отдельно от zip и вставить в setup скрытым вводом. Не вкладывайте реальный token в архив; при необходимости такой тестовый token можно потом отозвать в Hugging Face settings.

GigaSTT / GigaAM v3 - это основной локальный ASR-движок для русского языка: он превращает аудио в текст. Binary и модели не входят в zip, потому что они тяжелые и должны быть подготовлены на целевом Mac. На этапе `4/5: GigaSTT/GigaAM v3` setup скачивает `tools/bin/gigastt`, модели в `.models/gigastt/` и небольшую RUPunct-модель в `.models/gigastt/punct/` для пунктуации/регистра. Если сеть оборвалась, setup можно запустить повторно: готовые части будут переиспользованы.

Setup и doctor пишут локальные диагностические логи в `logs/`. Если после успешного setup web UI все еще пишет `GigaSTT не настроен`, запустите `Проверить Voice Recognizer.command` и пришлите только:

- `logs/setup-latest.log`
- `logs/doctor-latest.log`

Не пересылайте `.env`, аудио из `Inbox/` или результаты из `outputs/`. Логи печатают инвентарь GigaSTT/GigaAM файлов и missing-компоненты, но не должны печатать HF token.

Первый запуск обработки после чистой установки может дольше стоять на этапе `Диаризация`: pyannote впервые загружает/готовит локальный cache модели разделения спикеров. В журнале процесса должны появляться строки `Diarization / pyannote: ...`; если таких строк нет 10+ минут, пришлите технический лог задачи.

На целевом Mac:

1. Распаковать zip в обычную папку.
2. Открыть `START_HERE.txt`.
3. Если macOS показывает предупреждение `не удалось проверить на наличие вредоносного ПО`, один раз запустить `Разблокировать Voice Recognizer.command`.
4. Затем дважды кликнуть `Настроить Voice Recognizer.command`.
5. После setup запустить `Проверить Voice Recognizer.command`.
6. Если doctor показывает `failures=0`, запустить `Запустить Voice Recognizer.command`.
7. Провести сценарий из `docs/spouse-mac-install-trial.md`.

Про macOS Gatekeeper: текущий trial pack не подписан Apple Developer ID и не notarized, поэтому macOS может предлагать `Переместить в корзину`. Малый workaround - снять quarantine-метку с распакованной папки через `Разблокировать Voice Recognizer.command` или Terminal:

```bash
xattr -dr com.apple.quarantine "/path/to/Voice Recognizer Trial"
```

Правильное release-решение на будущее - Developer ID signing + notarization.

Если на этапе Homebrew/ffmpeg видны ошибки `Failed to download resource`, `curl: (28)` или `curl: (35)` для `ghcr.io`, это сетевой сбой скачивания bottle'ов Homebrew. Остановите setup, попробуйте другую сеть/позже и запустите `Настроить Voice Recognizer.command` снова. Setup можно повторять безопасно.

Ручной путь для разработки:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e 'app[diarization]'
app/scripts/setup_gigastt.sh
cp app/.env.example .env
```

В `.env` нужно добавить Hugging Face read-only token с доступом к `pyannote/speaker-diarization-community-1`:

```bash
HF_TOKEN=hf_your_token_here
```

Проверка доступа:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer check-pyannote-access
```

Локальная smoke-проверка для разработчиков и AI-агентов перед trial pack или крупной правкой:

```bash
app/scripts/smoke_local.sh
```

Она не запускает GigaSTT/pyannote, не требует приватных аудио и не пишет результаты в `Inbox/` или `outputs/`. Проверяются shell syntax, Python compile, ключевые CLI help, синтетические quality fixtures, manifest/result payload и web UI JavaScript syntax. Для проверки JavaScript нужен локальный `node`.

## Как пользоваться без Codex

Самый простой способ запуска на macOS:

1. Открыть папку проекта `/Users/andrey/Documents/Voice Recognizer`.
2. При первом запуске дважды кликнуть `Настроить Voice Recognizer.command`.
3. Если хочется проверить готовность без запуска сервера, дважды кликнуть `Проверить Voice Recognizer.command`.
4. После успешной настройки дважды кликнуть `Запустить Voice Recognizer.command`.
5. Оставить открывшееся окно Terminal работать.

Ярлык сам перейдет в папку проекта, запустит web-сервер на `127.0.0.1:8765` и откроет браузер.

Если порт `8765` уже занят старой версией сервера, ярлык покажет найденный процесс и спросит:

1. остановить старый процесс и запустить свежий сервер;
2. оставить старый процесс работать и открыть его в браузере;
3. выйти без изменений.

Запуск из Terminal вручную, если ярлык не нужен:

```bash
cd "/Users/andrey/Documents/Voice Recognizer"
.venv/bin/voice-recognizer web --port 8765
```

Если нажать `Ctrl+C`, закрыть окно Terminal или завершить процесс, web-интерфейс перестанет отвечать.

Проверка установки без запуска сервера:

```bash
cd "/Users/andrey/Documents/Voice Recognizer"
app/scripts/doctor_local_mac.sh
```

Doctor ничего не устанавливает и не скачивает. Он только показывает, что уже готово, что отсутствует и какие следующие действия нужны.

После запуска открыть в браузере:

```text
http://127.0.0.1:8765/
```

Обычный сценарий работы:

1. Положить `.m4a`, `.wav`, `.mp3` или `.mp4` в папку `Inbox` или загрузить файл через блок `Загрузить аудио` в web-интерфейсе.
2. Открыть `http://127.0.0.1:8765/`.
3. Выбрать файл в поле `Источник`.
4. Оставить `Длительность` пустой, если нужно обработать весь файл.
5. Оставить `ASR-движок` = `GigaSTT / GigaAM v3 RNNT`.
6. Оставить `Устройство` = `auto`; на Apple Silicon оно выберет MPS, когда это возможно.
7. Нажать `Запустить` и дождаться статуса `done`.
8. Открыть готовые файлы по ссылкам в блоке `Результаты`.
9. Прослушать samples спикеров, вписать имена и нажать `Применить имена`.

Проверить, что сервер жив:

```bash
curl -s http://127.0.0.1:8765/ >/dev/null && echo "server ok"
```

Остановить сервер корректно:

1. Дважды кликнуть `Остановить Voice Recognizer.command`.
2. Если ярлык нашел запущенный сервер, подтвердить остановку в окне Terminal.

Ручной способ:

1. Если сервер запущен в текущем окне Terminal, перейти в это окно и нажать `Ctrl+C`.
2. Проверить, освободился ли порт:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Если команда ничего не вывела, сервер остановлен.

Если порт все еще занят, `lsof` покажет PID процесса. Например:

```text
COMMAND   PID   USER   FD   TYPE   DEVICE SIZE/OFF NODE NAME
Python  95293 andrey    3u  IPv4      ...      0t0  TCP 127.0.0.1:8765 (LISTEN)
```

Остановить зависший сервер по PID:

```bash
kill 95293
```

Затем снова проверить порт:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Для сервера на другом порту заменить `8765` на нужный порт, например `8766`.

Если порт уже занят, можно запустить на другом:

```bash
.venv/bin/voice-recognizer web --port 8766
```

и открыть `http://127.0.0.1:8766/`.

Batch-обработка всей папки без web-интерфейса:

```bash
cd "/Users/andrey/Documents/Voice Recognizer"
set -a
source .env
set +a
.venv/bin/voice-recognizer batch-process Inbox --output-dir outputs/pipeline-batch
```

Один файл без web-интерфейса:

```bash
cd "/Users/andrey/Documents/Voice Recognizer"
set -a
source .env
set +a
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a'
```

Один файл, первые 2 минуты, ASR + speaker diarization + Markdown:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' --start 0 --duration 120
```

Полный файл:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a'
```

Результаты сохраняются в `outputs/pipeline/`:

- raw JSON от GigaSTT;
- JSON с turn-level diarization от pyannote;
- подробный Markdown с summary, полным текстом, сегментами и RTF;
- чистый Markdown с таймкодами;
- чистый Markdown без таймкодов;
- plain TXT без таймкодов;
- plain TXT с таймкодами;
- `.speaker-*.sample.wav` для прослушивания голосов и назначения имен;
- manifest JSON со списком всех артефактов.

Файлы, загруженные через браузер, сохраняются локально в `Inbox/`. Если файл с таким именем уже есть, сервис добавит суффикс, например `recording-2.m4a`, и не перезапишет исходник.

Имена спикеров можно передать сразу:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' \
  --start 0 \
  --duration 120 \
  --speaker-names '1=Оля,2=Андрей'
```

По умолчанию включено сглаживание коротких speaker-islands: если одно-два слова другого спикера попали внутрь непрерывной фразы, они мягко приклеиваются к окружающему спикеру. Для диагностики можно выключить:

```bash
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' --no-smooth-speakers
```

Если результат уже был создан старой версией и в интерфейсе напротив `Качество спикеров` показан `-`, можно обновить только диагностические поля manifest без повторного ASR и диаризации:

```bash
.venv/bin/voice-recognizer refresh-quality outputs/pipeline
```

Чтобы найти места, где итоговый текст стоит проверить или чинить отдельным repair-проходом, можно построить диагностические отчеты и portable edited exports без повторного ASR/диаризации:

```bash
.venv/bin/voice-recognizer repair-quality outputs/pipeline --recursive
```

Команда создает отдельные `*.repair.json`, `*.edited.md` и `*.edited.txt` рядом с manifest-файлами. Raw ASR JSON, Markdown/TXT exports и сами manifest не перезаписываются.

Batch-обработка папки с разделением по спикерам:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer batch-process Inbox --output-dir outputs/pipeline-batch
```

Команда создает отдельные `.gigastt.json`, `.pyannote.json` и `.transcript.md` для каждого файла, а также общий `batch_index.md`.

Известное число спикеров для тестовых файлов зафиксировано в `app/config/speaker-counts.json`.

Локальный web-интерфейс:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer web --port 8765
```

Открыть: http://127.0.0.1:8765

Web UI показывает файлы из `Inbox`, запускает тот же `process` pipeline, ведет лог задачи и дает ссылку на готовый Markdown из `outputs/`.

После завершения задачи web UI показывает:

- ссылки на все экспортные файлы;
- audio samples для каждого найденного спикера;
- поля для имен спикеров;
- кнопку применения имен без повторного ASR/diarization.

Для быстрой ASR-only проверки без pyannote:

```bash
.venv/bin/voice-recognizer transcribe-gigastt 'Inbox/Оля коридоре а сайта восторга.m4a' --start 0 --duration 120
.venv/bin/voice-recognizer batch-gigastt Inbox --output-dir outputs/batch
```

## ASR-движки и GigaAM V3

Да, GigaAM V3 уже используется в текущем рабочем прототипе: это backend `GigaSTT / GigaAM v3 RNNT` с моделями в `.models/gigastt/`.

Сейчас доступный ASR-движок:

```bash
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' --asr-engine gigastt-gigaam-v3
```

Что найдено на ноутбуке:

- `GigaSTT / GigaAM v3 RNNT` — подключен и работает сейчас.
- Handy `GigaAM V3` — файлы найдены, но это другой single-file ONNX runtime; напрямую в `gigastt` он не вставляется.
- Handy `Whisper Large v3` — файл найден в формате `ggml`; его можно будет подключить через `whisper.cpp`, если добавить такой backend.
- LM Studio — это LLM-модели; они полезны для постобработки текста, но не для первичного ASR.

Web UI уже показывает поле `ASR-движок`: рабочий вариант активен, кандидаты Handy видны как будущие backend’ы.

## Текущие замеры

На фрагменте `Оля...`, первые 120 секунд:

- GigaSTT ASR: около 6.3s, RTF 0.052.
- pyannote Community-1 на CPU: около 89s.
- pyannote Community-1 на Apple MPS: около 6.4s.
- Итог: 90 слов, 2 спикера, 0 неизвестных speaker labels после reconciliation.

На фрагменте `Носников...`, первые 120 секунд:

- GigaSTT ASR: около 6.0s.
- pyannote Community-1 на CPU: около 88.9s.
- Итог: 98 слов, 2 спикера, один неизвестный label на коротком слове у самой границы тестового клипа.

По умолчанию `--device auto` использует Apple MPS, если он доступен. Если MPS когда-нибудь даст ошибку на конкретной записи, можно запустить с `--device cpu`.

## Известные ограничения

- Встроенная offline diarization GigaSTT падает с `Invalid rank for input_features`; это предупреждение можно игнорировать, потому что speaker diarization делает pyannote.
- GigaSTT не принимает один аудиофайл длиннее примерно 2 часов, а его punctuation/casing postprocess заметно деградирует на длинных часовых кусках. Pipeline поэтому автоматически режет ASR на чанки по умолчанию до 600 секунд, сохраняет `*.part-XXX_<start>s_<duration>s.gigastt.json` и собирает общий `*.gigastt.json` с глобальными таймкодами. Размер можно изменить через `--asr-chunk-seconds`.
- Пунктуация на границах ASR-чанков может быть чуть менее аккуратной. Если понадобится редакторская полировка больших обучений, следующий шаг — LLM-постобработка через LM Studio.
- Сглаживание speaker-islands повышает читабельность, но иногда может поглотить короткую настоящую реплику вроде “да” или “угу”. Raw `.pyannote.json` сохраняется отдельно, а сглаживание можно выключить.
- Для многоспикерных обучений лучше задавать границы в `app/config/speaker-counts.json`: `num_speakers`, либо `min_speakers`/`max_speakers`.
- Сейчас экспорт основной — Markdown/TXT; DOCX можно добавить поверх уже сохраненных структурированных JSON.

## Этапы

### 1. Бенчмарк на реальных записях

Выбрать 3-5 коротких фрагментов по 5-15 минут:

- чистая диктовка одним голосом;
- интервью на 2 человека;
- обучение/созвон с 2-4 участниками;
- сложная запись с шумом, перебиваниями или расстоянием до микрофона.

### 2. Минимальный пайплайн

Собрать воспроизводимый CLI:

- принять файл;
- транскрибировать;
- диаризовать;
- сохранить Markdown с таймкодами и спикерами.

### 3. Сравнение движков

Проверить качество и скорость нескольких вариантов:

- GigaAM v3 + pyannote;
- GigaAM v3 ONNX/gigastt + pyannote;
- WhisperX/whispermlx как контрольный вариант;
- готовые приложения как ориентир UX, не как основной путь.

Текущий GigaSTT baseline на трех файлах из `Inbox`: 2:14:52 аудио обработались за 4:07. Диаризация в GigaSTT не сработала, поэтому рабочий speaker backend вынесен в pyannote Community-1.

### 4. Редактор результата

Добавить интерфейс для:

- прослушивания по таймкоду;
- переименования спикеров;
- объединения ошибочно разделенных спикеров;
- правки текста;
- экспорта.

### 5. Упаковка

После стабилизации пайплайна выбрать форму:

- локальный Python/Streamlit или FastAPI + web UI;
- Tauri/Electron;
- нативный Swift/macOS, если важна интеграция с Finder/iCloud/Voice Memos.
