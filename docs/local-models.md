# Local Models

Дата осмотра: 2026-06-25.

## Статус ASR backend'ов

| Backend | Статус | Комментарий |
| --- | --- | --- |
| `gigastt-gigaam-v3` | работает | Текущий основной ASR: GigaSTT с GigaAM v3 RNNT из `.models/gigastt`. |
| `handy-gigaam-v3` | кандидат | Handy-модель найдена, но это single-file ONNX, не совместимый напрямую с GigaSTT split RNNT files. |
| `handy-whisper-large-v3` | кандидат | Handy Whisper Large v3 найден в формате `ggml`; нужен backend через `whisper.cpp`. |
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

## Правило переиспользования

Модель можно переиспользовать, когда выполнены все условия:

- известен формат модели;
- есть совместимый локальный runtime;
- понятны tokenizer/vocab/config;
- приложение-владелец не ожидает эксклюзивную структуру папки;
- мы читаем модель read-only или копируем/symlink в `.models/`.

Если хотя бы одно условие не выполнено, безопаснее скачать/хранить отдельный проверенный артефакт проекта.
