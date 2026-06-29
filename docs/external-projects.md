# External Projects

## daowolf/transcribe

Source: https://gitverse.ru/daowolf/transcribe

Первичный вывод: проект полезен как референс пайплайна, но не как основа, которую стоит переносить целиком.

Что в нем есть:

- GUI на Tkinter;
- Docker-образ для Linux/NVIDIA;
- daemon-режим для папки входящих файлов;
- GigaAM для ASR;
- pyannote для диаризации;
- `sbert_punc_case_ru` для пунктуации;
- Ollama/Qwen для LLM-постобработки;
- склейка соседних pyannote-сегментов одного спикера перед ASR.

Что стоит перенять:

- daemon/batch-идею: входная папка -> выходная папка;
- структуру этапов: подготовка аудио -> диаризация -> транскрибация по сегментам -> постобработка;
- LLM-постобработку с пользовательским контекстом терминов;
- объединение коротких/соседних сегментов одного спикера.

Почему не копируем целиком:

- проект заточен под Docker и NVIDIA CUDA, а у нас Apple Silicon;
- используется GigaAM v2, в нашем случае интереснее GigaAM v3/GigaSTT;
- зависимости старые и конфликтные для macOS ARM (`torch==2.1.0`, `pyannote.audio==3.1`, `numpy<2.0`);
- основной файл монолитный, около двух тысяч строк GUI и логики;
- локальная работа без интернета достигается за счет заранее собранного Docker-образа, а не чистой macOS-установки.

Итог: берем архитектурные идеи, но продолжаем свой модульный пайплайн.

## QuentinFuxa/WhisperLiveKit

Source: https://github.com/QuentinFuxa/WhisperLiveKit

Статус: обязательно изучить перед следующим большим implementation-блоком.

Первичный вывод: проект не дублирует нашу главную задачу целиком, но закрывает часть смежной инфраструктуры лучше нас. WhisperLiveKit сильнее в real-time/self-host STT: WebSocket streaming, OpenAI-compatible API, модельный менеджер, бенчмарки, несколько Whisper/Voxtral/Qwen backend'ов, optional Apple Silicon MLX extras, Docker profiles и real-time diarization. Наш текущий фокус другой: локальный Mac-продукт для обычного пользователя, длинные готовые файлы, batch, GigaAM/GigaSTT для русского, speaker labeling и удобные экспорты.

Что в нем есть:

- `wlk transcribe` для транскрибации файла без сервера;
- `wlk models`, `wlk pull`, `wlk rm` для управления моделями;
- `wlk bench` и reproducible benchmark scripts;
- OpenAI-compatible `/v1/audio/transcriptions`;
- native WebSocket `/asr` для real-time streaming;
- backend selector: MLX Whisper, Faster-Whisper, Whisper, OpenAI API, Voxtral, Qwen3/vLLM;
- optional extras для Apple Silicon MLX, CPU, CUDA, translation, diarization;
- diarization через Sortformer/Diart;
- VAD/VAC и streaming policies для низкой задержки;
- troubleshooting docs и production/Docker guide.

Что стоит рассмотреть без раздувания фич:

- модель `doctor + model manager`: понятные команды проверки/скачивания/удаления моделей;
- benchmark harness как отдельный dev-инструмент для сравнения GigaAM vs Whisper/Voxtral на наших русских файлах;
- optional WhisperLiveKit backend только для file transcription или локального OpenAI-compatible endpoint;
- идею OpenAI-compatible local API как будущую интеграционную поверхность, не как обязательный основной UI;
- dependency extras/profile matrix: не смешивать несовместимые backend'и в одном окружении;
- troubleshooting формат для setup ошибок;
- `wlk transcribe --format srt` как подсказку для будущих SRT/VTT exports.

Что пока не берем:

- live microphone/WebSocket UI как главную функцию;
- Docker/self-host production profile до готового локального Mac-продукта;
- translation;
- chrome extension;
- multi-user server logic;
- полный набор backend'ов и optional extras.

Вопросы research-gate:

1. Можно ли подключить WhisperLiveKit как optional local Whisper backend без переписывания нашего pipeline?
2. Есть ли смысл использовать его CLI/API вместо собственной Whisper-интеграции?
3. Насколько хорошо его Apple Silicon MLX profile работает на русских диктофонных файлах?
4. Может ли его benchmark framework стать основой нашего quality benchmark?
5. Какие license/NOTICE условия Apache-2.0 надо выполнить, если мы берем код, а не только идеи?

Итог: не заменяем наш продукт WhisperLiveKit'ом, но до implementation setup/engine registry делаем короткое сравнение и берем только узкие инфраструктурные идеи.

## Local Whisper ecosystem

Sources:

- https://github.com/ggml-org/whisper.cpp
- https://github.com/argmaxinc/WhisperKit
- https://github.com/SYSTRAN/faster-whisper

Статус: активное research-направление для `P0-005` и `P0-010`.

Что найдено локально:

- Handy хранит `ggml-large-v3-q5_0.bin`, совместимый по формату с `whisper.cpp`.
- Whisper Transcription/MacWhisper хранит CoreML WhisperKit models:
  - `openai_whisper-large-v3-v20240930`;
  - `openai_whisper-small`.
- CLI `whisper.cpp`/`whisper-cli` пока не установлен в PATH.

Что это значит для нас:

- `whisper.cpp` - самый прямой путь проверить Handy Whisper Large v3 без обращения к приватному Handy runtime.
- WhisperKit - самый прямой путь проверить CoreML-модель, уже скачанную MacWhisper, но продуктово лучше использовать открытый Argmax runtime/CLI, а не MacWhisper runner bundles.
- `faster-whisper` полезен как переносимый Python/CTranslate2 профиль, но он не переиспользует найденные `ggml`/CoreML файлы напрямую; его стоит подключать только после решения по downloads/model manager.

Что берем:

- разделение engine profile и model asset: один UI-профиль должен показывать runtime, model path, status and next step;
- benchmark-first workflow: сначала экспорт кандидата в `.local-quality/candidates/`, затем `benchmark-quality --candidate`;
- runtime-specific names вместо общего "Whisper": `whispercpp-handy`, `macwhisper-whisperkit`, `faster-whisper`.

Что не берем:

- приватные bundles из `/Applications/Whisper Transcription.app/Contents/Resources`;
- прямую зависимость от GUI-приложения MacWhisper;
- автоматическую отправку аудио в OpenAI/Groq/Deepgram runners, даже если они есть в app bundle.

Следующий gate:

1. Получить один MacWhisper export для `Носников` и сравнить его с Speech2Text/GigaSTT через текущий `benchmark-quality`.
2. Если MacWhisper выигрывает хотя бы на проблемных фрагментах, добавить WhisperKit profile в engine registry как `missing-runtime`/`ready` по фактической установке.
3. Отдельно решить, ставим ли `whisper.cpp` для Handy `ggml` и делаем второй кандидатный прогон.

## Speech2Text.ru

Source: https://speech2text.ru/

Статус: внешний quality reference, публичного open-source не найдено.

Что видно публично:

- сервис делает распознавание, разделение говорящих и пунктуацию;
- есть API/integration page;
- на сайте указаны `Linux`, `PHP`, `Python`, `MySQL`, `yt-dlp`, `whisper`, `ffmpeg`;
- продукт включен в реестр российского ПО;
- подробное описание pipeline, моделей или репозиторий с наработками не найдены.

Вывод:

- Не используем как зависимость или source-код.
- Используем как внешний эталон качества: экспорт/копия результата кладется в ignored `.local-quality/references/` или `.local-quality/candidates/`.
- Через `benchmark-quality --candidate speech2text=...` можно сравнивать их вывод с нашим raw/edited и будущими локальными движками на тех же reference snippets.

Гипотеза:

- Хороший результат вероятно дает не один Whisper, а комбинация ASR, diarization, пунктуации и постобработки. Поэтому для нас правильный путь - не искать один “магический” движок, а строить измеряемый multi-candidate pipeline.
