# ASR-модели и читабельность (пунктуация / регистр / «ё» / термины)

Дата: 2026-06-27.
Автор: Claude (analysis track).
Связано с: `docs/quality-benchmark-references.md` (бенчмарк vs референс).

Вопрос владельца: насколько пунктуация, заглавные, «ё», правильные слова/термины/имена зависят от самой ASR-модели; провести ресёрч в интернете и тесты не только текущей, но и других моделей.

## TL;DR

1. **Да, читабельность сильно зависит от класса модели.** CTC/RNN-T модели (наш случай) выдают «сырой» нижний регистр без пунктуации; seq2seq (Whisper) и end-to-end модели (GigaAM **v3 e2e**) дают пунктуацию и регистр нативно.
2. **Но у нас есть и локальная причина:** в пайплайн уже вшита модель восстановления пунктуации **RUPunct** (`.models/gigastt/punct/rupunct_small_int8.onnx`), и мы передаём `--punct-model-dir` бинарю — **но в выводе пунктуации нет вообще**. То есть мы уже возим модель пунктуации, которая не применяется.
3. Эмпирически (скорер ниже): у нас пунктуация ≈ 0 на 100 слов, заглавные ≈ 0%, «ё» = 0; у референса ~31/100, регистр предложений 62–99%, «ё» 19–30 на 1000 слов.
4. Тесты других моделей и auto-перепрогон диаризации **не запускались из песочницы** (Linux aarch64, бинарь GigaSTT — macOS, сеть для pip/HF заблокирована). Готовый протокол и скрипты для запуска на Mac — ниже.

## Локальная причина (с привязкой к коду)

- Бинарь вызывается с `--punct-model-dir` и `--format json` (`app/src/voice_recognizer/gigastt.py:81-95`), но в `*.gigastt.json` и поле `text`, и `words[]` — сырые: нижний регистр, без знаков, без «ё».
- Все читаемые выводы (`*.transcript.md`, `*.clean*.md`, `*.timeline.txt`) собираются из **сырых пословных токенов**: `_segment_from_words` → `text=" ".join(word.word for word in words)` (`gigastt.py:263`). Пунктуированный `text` нигде не используется по сути (идёт только в summary-блок, `gigastt.py:197`, и тоже сырой).
- Вшитая модель — RUPunct (`config.json`: `BertForTokenClassification`, метки `UPPER_*` / `LOWER_*` + period/comma/question/tire/voskl/dvoetochie/…), то есть восстанавливает И регистр, И пунктуацию. Файлы: `rupunct_small_int8.onnx` (~29 МБ) + `tokenizer.json`.

Вывод: либо бинарь не применяет punct в json-режиме (нужно проверить его флаги/формат на Mac), либо punct надо применять самим в Python. Модель уже есть локально — это не «нет модели», а «модель не подключена к выводу».

## Почему это зависит от модели (ресёрч)

- **GigaAM v2** (RNN-T/CTC) генерирует текст без пунктуации и регистра; **GigaAM v3** в вариантах `v3_e2e_ctc` / `v3_e2e_rnnt` выдаёт пунктуированный и нормализованный текст напрямую, без отдельной постобработки. Наша сборка использует `v3_rnnt` (см. `.models/gigastt/v3_rnnt_*`) — то есть **не** e2e-вариант. [GigaAM](https://github.com/salute-developers/GigaAM), [ai-sage/GigaAM-v3](https://huggingface.co/ai-sage/GigaAM-v3), [gigaam (PyPI)](https://pypi.org/project/gigaam/), [onnx-asr](https://pypi.org/project/onnx-asr/).
- **Whisper large-v3** (seq2seq) выдаёт пунктуацию и заглавные нативно, прямо в декодере; есть русские дообучения с меньшим WER. [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3), [whisper-large-v3-russian](https://dataloop.ai/library/model/antony66_whisper-large-v3-russian/).
- **Постобработка (модель-агностично):** если ASR не пунктуирует — ставят отдельный восстановитель: [kontur-ai/sbert_punc_case_ru](https://huggingface.co/kontur-ai/sbert_punc_case_ru) (пунктуация + регистр, делался под ASR), Silero punctuation ([Habr](https://habr.com/en/articles/581960/)), [neuro-comma](https://github.com/sviperm/neuro-comma), [ru-autopunctuation](https://github.com/kotikkonstantin/ru-autopunctuation). Наш вшитый RUPunct — из этого класса.
- «**ё**» обычно не восстанавливается ни ASR, ни большинством punct-моделей (в метках RUPunct «ё» нет) — нужен отдельный yoficator (словарный, напр. `eyo`/`yoficator`), если «ё» важна.
- Локальные приложения как референс для тестов: [Handy models](https://handy.computer/docs/models) (Whisper/Parakeet), MacWhisper/whisper.cpp, LM Studio. Обзор открытых STT 2026: [Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks).

## Эмпирический базлайн (скорер, запущен сейчас)

Скрипт `docs/asr-benchmark/score.py` (без зависимостей) на нашем выводе vs референс:

| Источник | punct/100w | upper% | предложений с заглавной | «ё»/1000 слов |
|----------|:---:|:---:|:---:|:---:|
| Наш (gigaam-v3 rnnt) — 4 файла | 0.0–2.6 | 0–1.1 | 0–20% | **0** |
| Референс — 4 файла | 30.5–33.0 | 1.8–3.7 | 62–99% | 19–30 |

Термины/имена: «НФЛО» — у нас 0, у референса 2; «пубертат» — у нас 0, у референса 1.

Разрыв тотальный по всем трём осям (пунктуация, регистр, «ё»), что подтверждает: punct-модель в нашем пайплайне фактически не применяется.

## Варианты исправления (от дешёвого к крупному)

| # | Что | Плюсы | Минусы | Размер |
|---|-----|-------|--------|--------|
| A | Применить вшитый RUPunct (`rupunct_small_int8.onnx`) как явный пост-шаг в Python (onnxruntime) поверх сегментов | модель уже есть, офлайн, локально; сохраняет таймкоды/спикеров | свой код инференса BERT-token-classification + маппинг меток в текст | M |
| B | Заставить бинарь GigaSTT реально применять punct (проверить `gigastt transcribe --help`: возможно, нужен флаг или не-json формат) | возможно, правка в одну строку | зависит от возможностей бинаря; проверять на Mac | S–? |
| C | Перейти на GigaAM **v3 e2e** (`v3_e2e_rnnt/ctc`) — пунктуация и нормализация нативно, та же семья | без отдельной модели; нормализация чисел/дат | другая сборка/веса; проверить, поддерживает ли наш бинарь e2e | M |
| D | Whisper large-v3 (рус. дообучение) как альтернативный движок | нативная пунктуация+регистр, силён на шуме | медленнее, другой стек, проверить MPS | M–L |

«ё»: при A/B/C при необходимости добавить отдельный yoficator (S).

Рекомендация: проверить B (быстро, на Mac), иначе A (используем уже вшитую модель). C/D — стратегически, через тест ниже.

## Implementation follow-up (Codex, 2026-06-27)

Путь **B** проверен на Mac: `gigastt transcribe --help` показывает `--punctuation`, `--itn` и варианты `rnnt/e2e_rnnt`. Короткий прогон `Носников 0–30s` с `--punctuation on --itn auto` подтвердил, что поле `text` в JSON получает пунктуацию и регистр, а `words[]` остаются сырыми.

Что реализовано:

- `app/src/voice_recognizer/gigastt.py` теперь явно вызывает GigaSTT с `--punctuation on --itn auto`;
- при `load_result()` пунктуация/регистр из `text` переносятся на timestamped `words[]`, поэтому clean/timeline/Markdown сегменты сохраняют таймкоды и спикеров, но становятся читаемее;
- `app/config/speaker-counts.json` больше не зажимает обучающие записи в `max_speakers=8`, а спорный `Носников` больше не фиксируется как `num_speakers=2`;
- `docs/asr-benchmark/score.py` починен для `--terms "..."`.

Осталось как отдельные шаги: GigaAM v3 e2e/Whisper comparison, восстановление `ё`, доменный глоссарий/hotwords и честный перепрогон длинных файлов с новыми speaker limits.

## Протокол тестов на Mac (то, что не запустить из песочницы)

Песочница — Linux aarch64; бинарь GigaSTT — macOS; pip/HF закрыты. Поэтому ниже — то, что нужно прогнать на Mac (владельцу или агенту с доступом к Mac).

### A. Перепроверка диаризации (auto) — финализирует вывод бенчмарка

```bash
# Носников: без жёсткого num_speakers
.venv/bin/python -m voice_recognizer.cli process "Inbox/Носников дапринт + нфло.m4a" \
  --output-dir outputs/bench-auto --asr-engine gigastt-gigaam-v3 --device auto --min-speakers 2 --max-speakers 12
# Модуль 3 день2: поднять потолок
.venv/bin/python -m voice_recognizer.cli process "Inbox/Модуль 3, день 2, 1ч.m4a" \
  --output-dir outputs/bench-auto --asr-engine gigastt-gigaam-v3 --device auto --min-speakers 2 --max-speakers 24
# сравнить speaker_count с референсом (5 и 21)
python3 - <<'PY'
import json,glob
for m in glob.glob('outputs/bench-auto/*.manifest.json'):
    d=json.load(open(m)); print(d['speaker_count'], d['source'])
PY
```

### B. Сравнение ASR-моделей на одинаковых клипах

1. Нарезать 2–3 клипа по 90–120 c из файлов, где есть референс (например Носников 0:00–1:35, где реф с таймкодами):

```bash
ffmpeg -y -i "Inbox/Носников дапринт + нфло.m4a" -ss 0 -t 95 -ac 1 -ar 16000 outputs/asr-clips/nos_0-95.wav
```

2. Прогнать каждую модель на клипе и сохранить .txt:
   - **текущая** (gigaam-v3 rnnt) — наш CLI;
   - **GigaAM v3 e2e** — `pip install gigaam`; `gigaam.load_model("v3_e2e_rnnt").transcribe(wav)` (или onnx-asr `gigaam-v3-e2e-rnnt`);
   - **Whisper large-v3** — whisper.cpp / faster-whisper / MacWhisper, язык ru;
   - **ваши локальные** — LM Studio / Wisper / Handy: выгрузить текст того же клипа.

3. Сравнить читабельность одной командой:

```bash
python3 docs/asr-benchmark/score.py outputs/asr-clips/*.txt --terms "НФЛО,пубертат,емейл"
# и приложить эталон:
python3 docs/asr-benchmark/score.py "<reference excerpt as .txt>"
```

Смотреть на `punct/100w`, `upper%`, `sent_caps%`, `yo/1k`, `terms`. Модель с высокими punct/upper/sent_caps даёт читаемый вывод «из коробки»; нули — нужна постобработка (вариант A).

## Рекомендации (приоритет)

R1. **Включить пунктуацию/регистр, которые уже почти есть.** Сначала B (флаг бинаря), иначе A (применить вшитый RUPunct в Python). Это закрывает главный разрыв с референсом, не меняя движок. Привязка: этап 4/5 `implementation-plan.md`.
R2. **Прогнать тест B** на Mac и решить про GigaAM v3 e2e (C) vs текущий+RUPunct — выбрать по качеству пунктуации и нормализации чисел.
R3. **Финализировать диаризацию** через тест A (auto) — текущие низкие числа спикеров были артефактом настроек (см. бенчмарк-отчёт).
R4. **«ё» и термины/имена** — отдельный yoficator + опц. глоссарий-биасинг для доменных слов (НФЛО, «пубертат» и т.п.).
R5. **Закрепить как регрессию:** `docs/asr-benchmark/score.py` + `references/` — гонять при смене модели/пайплайна, следить, чтобы punct/upper/yo не падали.

## Оговорки

- Скорер измеряет **читабельность** (плотность пунктуации, регистр, «ё», наличие терминов), а не WER. Высокий `punct/100w` ≠ правильная пунктуация, но нулевой однозначно = её нет.
- Модели на компьютере владельца и auto-диаризацию я **не запускал** — нет доступа к Mac-рантайму из песочницы; всё вынесено в протокол выше.
- Референс — вывод другого сервиса, не золотой эталон.

## Источники

- [salute-developers/GigaAM](https://github.com/salute-developers/GigaAM), [ai-sage/GigaAM-v3](https://huggingface.co/ai-sage/GigaAM-v3), [gigaam (PyPI)](https://pypi.org/project/gigaam/), [istupakov/gigaam-v3-onnx](https://huggingface.co/istupakov/gigaam-v3-onnx), [onnx-asr](https://pypi.org/project/onnx-asr/), [gigaam-mlx](https://github.com/aystream/gigaam-mlx)
- [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3), [whisper-large-v3-russian](https://dataloop.ai/library/model/antony66_whisper-large-v3-russian/)
- [kontur-ai/sbert_punc_case_ru](https://huggingface.co/kontur-ai/sbert_punc_case_ru), [Silero punctuation (Habr)](https://habr.com/en/articles/581960/), [neuro-comma](https://github.com/sviperm/neuro-comma), [ru-autopunctuation](https://github.com/kotikkonstantin/ru-autopunctuation)
- [Handy models](https://handy.computer/docs/models), [Northflank: best open STT 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
