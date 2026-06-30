# Диктум

**Диктум** - локальный инструмент для macOS, который превращает длинные русскоязычные аудиозаписи в рабочие текстовые протоколы: с пунктуацией, таймкодами, разделением по спикерам и экспортом в Markdown/TXT.

Проект создается для интервью, обучений, вебинаров, консультаций, семинаров и больших диктофонных архивов, где нужен не просто сырой текст, а материал, с которым можно дальше работать человеку или AI-агенту.

## Что умеет

- Распознает русскую речь локально через `GigaSTT / GigaAM v3 RNNT`.
- Разделяет запись по спикерам через pyannote.
- Обрабатывает длинные файлы чанками, без практического лимита в 1-2 часа.
- Поддерживает пакетную обработку папки `Inbox/`.
- Позволяет прослушать samples спикеров и назначить имена после обработки.
- Сохраняет результаты локально в `outputs/`.
- Экспортирует raw, clean и edited варианты в Markdown/TXT.
- Запускается как локальный web UI в браузере через double-click `.command` launchers.

## Приватность

Диктум спроектирован как local-first инструмент:

- аудио остается в `Inbox/`;
- результаты остаются в `outputs/`;
- токены лежат только в локальном `.env`;
- web UI слушает `127.0.0.1` и не предназначен для доступа из сети;
- обработка аудио не отправляет записи во внешние ASR-сервисы.

Сеть нужна при установке и первом запуске моделей:

- Homebrew/ffmpeg/Python dependencies;
- GigaSTT binary and models;
- pyannote model download through your Hugging Face token.

## Статус

Alpha / private-trial stage.

Проект уже пригоден для локального тестирования на Mac, но пока не является подписанным `.app` из App Store. macOS может показывать Gatekeeper/quarantine warnings для `.command` файлов из zip.

## Связь и обновления

Telegram-канал проекта: https://t.me/+ByvsbIefhtkyZGIy

Там будут новости сборок, сбор обратной связи от первых пользователей и короткие заметки по развитию продукта.

GitHub Releases: https://github.com/biztrackru/diktum/releases

## Требования

Рекомендуется:

- macOS на Apple Silicon;
- 16 GB RAM минимум;
- 32 GB RAM комфортнее для длинных записей и batch;
- 20-30 GB свободного места для моделей, cache и результатов;
- интернет при первой настройке;
- Hugging Face token с доступом к `pyannote/speaker-diarization-community-1`, если нужно разделение по спикерам.

Ориентир по установочному трафику: несколько GB, зависит от уже установленных Homebrew/Python/модельных компонентов.

## Быстрый старт

### Через trial pack

Если у вас есть zip-сборка:

1. Распакуйте архив в обычную папку.
2. Откройте `START_HERE.txt`.
3. При необходимости запустите `Разблокировать Диктум.command`.
4. Запустите `Настроить Диктум.command`.
5. Запустите `Проверить Диктум.command`.
6. Запустите `Запустить Диктум.command`.
7. Откройте локальный интерфейс на `http://127.0.0.1:8765/`.

### Из исходников

```bash
git clone https://github.com/biztrackru/diktum.git dictum
cd dictum
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e 'app[diarization]'
cp app/.env.example .env
```

Добавьте в `.env` read-only Hugging Face token:

```bash
HF_TOKEN=hf_your_token_here
```

Подготовьте GigaSTT/GigaAM:

```bash
app/scripts/setup_gigastt.sh
```

Запустите локальный web UI:

```bash
.venv/bin/dictum web --port 8765
```

Старый CLI-алиас `voice-recognizer` сохранен для совместимости:

```bash
.venv/bin/voice-recognizer web --port 8765
```

## Как пользоваться

1. Положите `.m4a`, `.mp3`, `.wav` или `.mp4` в `Inbox/` либо загрузите файл через web UI.
2. Выберите файл и параметры обработки.
3. Запустите обработку.
4. Дождитесь статуса `done`.
5. Прослушайте samples спикеров и задайте имена.
6. Откройте Markdown/TXT результат из интерфейса.

CLI-пример:

```bash
.venv/bin/dictum process 'Inbox/recording.m4a' --asr-engine gigastt-gigaam-v3
```

Batch-пример:

```bash
.venv/bin/dictum batch-process Inbox --output-dir outputs/pipeline-batch
```

## Сборка дистрибутива

```bash
app/scripts/build_install_pack.sh
```

Скрипт создает `.dist/Диктум Trial <timestamp>.zip` и кладет туда только пользовательскую поверхность:

- root launchers;
- `START_HERE.txt`;
- `VERSION.txt`;
- `FEEDBACK_TEMPLATE.txt`;
- `app/`;
- пустые `Inbox/` и `outputs/`.

В архив намеренно не попадают `.env`, `.venv`, `.models`, `.cache`, `logs`, `tools/bin`, приватные аудио, outputs, internal/agent files, tests, docs and developer-only scripts.

## Конфигурация

`app/config/speaker-counts.json` можно использовать для локальных подсказок по числу спикеров для конкретных файлов. В публичной версии файл пустой.

Для ASR hotwords создайте локальный файл:

```bash
cp app/config/hotwords.example.txt app/config/hotwords.txt
```

`app/config/hotwords.txt` игнорируется Git и не должен попадать в публичные коммиты.

## Ограничения

- Сейчас основной ASR backend один: `gigastt-gigaam-v3`.
- Диаризация зависит от pyannote и Hugging Face model access.
- Качество разделения спикеров может снижаться на перекрывающихся голосах и шумных записях.
- macOS signing/notarization пока не настроены.
- Self-host/Docker profile и native macOS wrapper находятся в roadmap, но не в текущем alpha baseline.

## License

MIT. См. [LICENSE](LICENSE).
