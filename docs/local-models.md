# Local Models

Дата осмотра: 2026-06-29.

## Статус ASR backend'ов

| Backend | Статус | Комментарий |
| --- | --- | --- |
| `gigastt-gigaam-v3` | работает | Текущий основной ASR: GigaSTT с GigaAM v3 RNNT из `.models/gigastt`. |
| `handy-gigaam-v3` | кандидат | Handy-модель найдена, но это single-file ONNX, не совместимый напрямую с GigaSTT split RNNT files. |
| `handy-whispercpp-large-v3-q5_0` | кандидат | Handy Whisper Large v3 найден в формате `ggml`; чистый runtime - `whisper.cpp`, локального `whisper-cli` пока нет в PATH. |
| `macwhisper-whisperkit-large-v3-v20240930` | кандидат | Whisper Transcription/MacWhisper скачал CoreML WhisperKit large-v3-v20240930; чистый runtime - Argmax WhisperKit/CLI, не приватные app bundles. |
| `faster-whisper-large-v3` | кандидат/отложен | Переносимый Python/CTranslate2 путь, но найденные локальные `ggml`/CoreML модели напрямую не переиспользует; нужен отдельный download/convert. |
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
- На этой машине `whisper-cli`/`whisper-cpp` не найдены в PATH, поэтому сначала нужен runtime: Homebrew package или сборка `ggml-org/whisper.cpp`.
- Для benchmark не нужно копировать модель в git: runtime может читать файл read-only или мы можем положить symlink/copy в ignored `.models/whisper/`.
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

Bundle id: `com.goodsnooze.MacWhisper`, observed version `13.15`.

В app bundle есть runner bundles:

- `WhisperCPP_Runner_WhisperCPP_Runner.bundle`;
- `WhisperCPP_Runner_Wispa.bundle`;
- `Argmax_Runner_Argmax_Runner.bundle`;
- `WhisperOpenAI_Runner_WhisperOpenAI_Runner.bundle`;
- `WhisperOpenAICompatible_Runner_WhisperOpenAICompatible_Runner.bundle`;
- `WhisperGroq_Runner_WhisperGroq_Runner.bundle`;
- prompt/assistant runners for local/cloud LLM integrations.

Локальные данные MacWhisper:

- `~/Library/Containers/com.goodsnooze.MacWhisper/Data/Library/Application Support/MacWhisper` - около 2.6 GB.
- `.../models/whisperkit/models/argmaxinc/whisperkit-coreml/openai_whisper-large-v3-v20240930` - около 1.5 GB:
  - `AudioEncoder.mlmodelc`;
  - `MelSpectrogram.mlmodelc`;
  - `TextDecoder.mlmodelc`;
  - `config.json`;
  - `generation_config.json`.
- `.../models/whisperkit/models/argmaxinc/whisperkit-coreml/openai_whisper-small` - около 464 MB.
- `.../models/argmaxinc/whisperkit-coreml/config.json` указывает default `openai_whisper-large-v3-v20240930` для M2/M3/M4-class Macs.

Вывод:

- Это реальный локальный Whisper-кандидат, но формат отличается от Handy: CoreML/WhisperKit, не `ggml`.
- Нельзя встраивать приватные runner bundles MacWhisper как зависимость нашего продукта.
- Чистый путь интеграции: открытый Argmax WhisperKit CLI/Swift package или экспорт результата MacWhisper в `.local-quality/candidates/` для benchmark.
- Если MacWhisper умеет экспортировать `.txt`/`.md`/`.srt`/`.vtt`, его вывод можно сравнить уже сейчас через `benchmark-quality --candidate`.

### Whisper benchmark route

Сейчас есть три безопасных шага сравнения Whisper без переписывания pipeline:

1. MacWhisper GUI/export route.

   Открыть тот же файл в Whisper Transcription/MacWhisper, выбрать локальный WhisperKit large-v3-v20240930, экспортировать text/markdown/SRT в ignored path:

   ```text
   .local-quality/candidates/nosnikov-macwhisper-whisperkit.txt
   ```

   Затем сравнить:

   ```bash
   PYTHONPATH=app/src .venv/bin/python -m voice_recognizer.cli benchmark-quality \
     "outputs/pipeline/Носников_дапринт_+_нфло.manifest.json" \
     --references .local-quality/references \
     --candidate macwhisper-whisperkit=.local-quality/candidates/nosnikov-macwhisper-whisperkit.txt \
     --output .local-quality/reports/nosnikov-whisper-candidates.json
   ```

2. `whisper.cpp` route for Handy `ggml-large-v3-q5_0.bin`.

   Установить/собрать `whisper.cpp`, прогнать тот же аудиофайл, сохранить `.txt`/`.srt` в `.local-quality/candidates/` и сравнить тем же `benchmark-quality`.

3. Engine registry route.

   После `P0-005` добавить оба профиля как missing/ready engines с явным next step:

   - `whispercpp-handy-large-v3-q5_0`;
   - `whisperkit-large-v3-v20240930`;
   - optional `faster-whisper-large-v3` only after separate portable model download/convert decision.

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
