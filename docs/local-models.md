# Local Models

Дата осмотра: 2026-06-25.

## Статус ASR backend'ов

| Backend | Статус | Комментарий |
| --- | --- | --- |
| `gigastt-gigaam-v3` | работает | Текущий основной ASR: GigaSTT с GigaAM v3 RNNT из `.models/gigastt`. |
| `handy-gigaam-v3` | кандидат | Handy-модель найдена, но это single-file ONNX, не совместимый напрямую с GigaSTT split RNNT files. |
| `handy-whisper-large-v3` | кандидат | Handy Whisper Large v3 найден в формате `ggml`; нужен backend через `whisper.cpp`. |
| `fluidaudio-parakeet-v3` | кандидат | WhyNote использует FluidAudio Parakeet TDT 0.6B v3 CoreML; модель найдена локально, нужен чистый runtime через FluidAudio/SwiftPM или экспорт кандидата. |
| LM Studio LLM | постобработка | Не ASR, но может чистить, структурировать и суммаризировать готовый текст. |

## Найдено

### Handy

Directory: `~/Library/Application Support/com.pais.handy/models`

- `giga-am-v3-int8/model.int8.onnx` — около 214 MB.
- `giga-am-v3-int8/vocab.txt`.
- `ggml-large-v3-q5_0.bin` — около 1.0 GB, Whisper Large v3 в формате whisper.cpp/ggml.

Вывод:

- Whisper `.bin` можно потенциально использовать через `whisper.cpp`.
- GigaAM ONNX из Handy пока не подключен: `gigastt` ожидает другой набор файлов (`encoder/decoder/joint/vocab`) и не принимает этот single-file ONNX напрямую.
- Нельзя безопасно писать временные файлы в папку Handy; свои модели держим в `.models/`.

### GigaSTT

Directory: `.models/gigastt`

- `v3_rnnt_encoder_int8.onnx`;
- `v3_rnnt_decoder.onnx`;
- `v3_rnnt_joint.onnx`;
- `v3_vocab.txt`;
- `wespeaker_resnet34.onnx`;
- `punct/`.

Вывод:

- Это сейчас основной рабочий ASR baseline.
- Для `gigastt 2.5.0` оставлен symlink `v3_rnnt_encoder.onnx -> v3_rnnt_encoder_int8.onnx`, чтобы команда `transcribe` не пыталась скачать FP32 encoder.

### LM Studio

Directory: `~/.lmstudio/models`

Найдены Qwen/Gemma и другие LLM в `.gguf`/`.safetensors`.

Вывод:

- Эти модели не подходят для ASR или диаризации напрямую.
- Их можно использовать для постобработки: чистка текста, восстановление структуры, выделение решений/задач, исправление терминов.
- Для интеграции удобнее подключаться к локальному OpenAI-compatible server LM Studio, а не читать файлы моделей напрямую.

### Wispr Flow

Directory: `~/Library/Application Support/Wispr Flow`

Явных ASR-моделей быстрый поиск не нашел; в основном cache/session-файлы.

### Whisper Transcription.app

App: `/Applications/Whisper Transcription.app`

Внутри app bundle явных `.bin`/`.onnx`/`.gguf` моделей быстрый поиск не нашел.

### WhyNote / FluidAudio

App: `/Applications/Whynote.app`

Version observed: `2.0.18`, bundle id `io.42apps.ainotetaker`.

В app bundle найдены профили:

- `local-fluid-audio-parakeet-v3` — local/shared, supported languages include `ru`;
- `cloud-nexara` — cloud/shared.

Локально скачанные модели:

- `~/Library/Application Support/Whynote/FluidAudio/parakeet-tdt-0.6b-v3-coreml` — около 461 MB, CoreML Parakeet ASR:
  - `Preprocessor.mlmodelc`;
  - `Encoder.mlmodelc`;
  - `Decoder.mlmodelc`;
  - `JointDecision.mlmodelc`;
  - `parakeet_v3_vocab.json`.
- `~/Library/Application Support/Whynote/FluidAudio/speaker-diarization-coreml`:
  - `pyannote_segmentation.mlmodelc`;
  - `wespeaker_v2.mlmodelc`;
  - `plda-parameters.json`.
- `~/Library/Application Support/Whynote/FluidAudio/silero-vad-coreml`.

Бинарные строки WhyNote указывают на `FluidAudio`, `HuggingFaceModelDownloader`, `FluidInference/parakeet-tdt-0.6b-v3-coreml`, `FluidInference/speaker-diarization-coreml`, `FluidInference/qwen3-asr-0.6b-coreml`, `FluidInference/silero-vad-coreml`.

Вывод:

- Нельзя безопасно встраивать или вызывать приватный код WhyNote как runtime.
- Модели можно рассматривать как read-only локальные артефакты для экспериментов, но переносимый продукт должен скачивать/использовать открытый runtime сам.
- Чистый путь интеграции: FluidAudio Swift package или отдельный CLI-wrapper, если он стабильно собирается на macOS.
- До полноценной интеграции можно экспортировать результат WhyNote/FluidAudio в `.local-quality/candidates/` и сравнивать через `benchmark-quality --candidate`.

## Правило переиспользования

Модель можно переиспользовать, когда выполнены все условия:

- известен формат модели;
- есть совместимый локальный runtime;
- понятны tokenizer/vocab/config;
- приложение-владелец не ожидает эксклюзивную структуру папки;
- мы читаем модель read-only или копируем/symlink в `.models/`.

Если хотя бы одно условие не выполнено, безопаснее скачать/хранить отдельный проверенный артефакт проекта.
