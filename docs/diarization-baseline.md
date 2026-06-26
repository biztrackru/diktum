# Diarization Baseline

Дата: 2026-06-25.

## Что проверено

Основной рабочий backend для разделения спикеров: `pyannote/speaker-diarization-community-1`.

Модель запускается локально через `pyannote.audio`. Для загрузки нужен Hugging Face token и принятые условия модели. Команда проверки:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer check-pyannote-access
```

В проекте используется `exclusive_speaker_diarization`, потому что она не содержит пересекающихся speaker-turns и лучше совмещается с word-level ASR timestamps.

## Важная техническая правка

`torchaudio.load` в текущем окружении пытался использовать `torchcodec`, который не смог загрузить arm64 ffmpeg dylib из-за установленного `/usr/local` Homebrew ffmpeg. Поэтому нормализованный WAV читается напрямую через стандартный модуль `wave` и `numpy`, а в pyannote передается tensor `{"waveform": ..., "sample_rate": ...}`.

Это сохраняет локальность пайплайна и не требует переустановки Homebrew.

## Замеры

`Inbox/Оля коридоре а сайта восторга.m4a`, первые 120 секунд, `num_speakers=2`:

- CPU diarization: 89.09s.
- MPS diarization: 6.44s.
- Result: 25 turns, 2 speakers.
- После speaker reconciliation: 90 words, 0 unknown speaker labels.

`Inbox/Носников дапринт + нфло.m4a`, первые 120 секунд, `num_speakers=2`:

- CPU diarization: 88.87s.
- Result: 20 turns, 2 speakers.
- После speaker reconciliation: 98 words, 1 unknown speaker label у границы 120s clip.

## Команды

Один файл:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' --start 0 --duration 120
```

Папка:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer batch-process Inbox --output-dir outputs/pipeline-batch
```

CPU fallback:

```bash
.venv/bin/voice-recognizer process 'Inbox/Оля коридоре а сайта восторга.m4a' --device cpu
```

## Вывод

Связка GigaSTT + pyannote Community-1 на Apple MPS уже годится как рабочий локальный прототип для интервью и обучений. Самые полезные следующие доработки:

- chunked punctuation для длинных файлов;
- LLM-постобработка через LM Studio;
- редактор speaker labels и текста;
- DOCX/TXT экспорт.
