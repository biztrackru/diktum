# Handy GigaAM v3 e2e CTC Runtime Spike

Дата: 2026-06-29.

## Короткий вывод

Handy `gigaam-v3-e2e-ctc` можно запустить вне Handy через чистый локальный стек `onnxruntime` + `torch`/`torchaudio` preprocessing. Это важный кандидат для качества русского текста: модель сразу выдает пунктуацию, регистр и нормализованный текст.

Это пока не готовая замена текущему `gigastt-gigaam-v3` engine, потому что:

- модель возвращает CTC-текст по аудио-фрагменту, но не word-level timestamps;
- текущий pipeline построен вокруг GigaSTT `words[]` и последующей привязки слов к speaker turns;
- качество сильно зависит от VAD/chunk stitching: тупая нарезка каждые 20 секунд и даже pyannote-turn нарезка уже работают, но пока не обгоняют текущий edited GigaSTT на private `Носников` reference.

## Что проверено

Локальный файл:

```text
~/Library/Application Support/com.pais.handy/models/giga-am-v3-int8/model.int8.onnx
```

ONNX metadata:

```text
inputs:
  features: float32 [batch_size, 64, seq_len]
  feature_lengths: int64 [batch_size]
outputs:
  log_probs: float32 [batch_size, seq_len, 257]
```

Vocab:

```text
~/Library/Application Support/com.pais.handy/models/giga-am-v3-int8/vocab.txt
```

Handy vocab содержит строки вида `token index`, а последняя строка - `<blk> 256`. Для CTC decode нужно брать token до последнего пробела и считать `256` blank id.

Препроцессинг совпадает с upstream GigaAM: mono 16 kHz, `MelSpectrogram` на 64 mel-bin, `win_length=400`, `hop_length=160`, `n_fft=400`, затем `log(clamp(mel))`.

Полезные upstream-ссылки:

- https://github.com/salute-developers/GigaAM
- https://raw.githubusercontent.com/salute-developers/GigaAM/main/gigaam/preprocess.py
- https://raw.githubusercontent.com/salute-developers/GigaAM/main/gigaam/onnx_utils.py
- https://raw.githubusercontent.com/salute-developers/GigaAM/main/gigaam/vad_utils.py

## Пробные результаты

Private artifacts, не коммитить:

```text
.local-quality/candidates/nosnikov-handy-gigaam-e2e-ctc-first2min.txt
.local-quality/candidates/nosnikov-handy-gigaam-e2e-ctc-pyannote-first2min.srt
.local-quality/reports/nosnikov-handy-gigaam-e2e-ctc-first2min.json
.local-quality/reports/nosnikov-handy-gigaam-e2e-ctc-pyannote-first2min.json
```

На первых 10 секундах `Носников` модель корректно распознала короткую фразу с вопросительным знаком и заглавной буквой. На первых 120 секундах:

| Candidate | Chunking | Token F1 vs private reference | Пунктуация |
| --- | --- | ---: | ---: |
| current raw GigaSTT | existing pipeline | 0.606 | 26.4 / 100 words |
| current edited GigaSTT | existing deterministic repair | 0.638 | 31.7 / 100 words |
| Handy GigaAM e2e CTC | fixed 20s chunks | 0.593 | 32.0 / 100 words |
| Handy GigaAM e2e CTC | pyannote speech turns | 0.603 | 29.9 / 100 words |
| Handy Whisper/whisper.cpp | SRT candidate | 0.511 | 0.0 / 100 words |

Интерпретация:

- e2e CTC заметно лучше выглядит по регистру и пунктуации;
- без правильного VAD/chunk stitching появляются обрезанные первые звуки, лишние повторы и ошибки на коротких/шумных участках;
- модель уже достаточно быстрая даже на CPUExecutionProvider для коротких проверок;
- как прямой replacement она пока не выигрывает benchmark, но как engine candidate и/или второй ASR-слой она гораздо перспективнее Whisper CPU-кандидата.

## Product decision

Не нужно подключать Handy как приложение или копировать его private runtime. Чистый путь:

1. Сделать отдельный experimental engine profile `handy-gigaam-v3-e2e-ctc`.
2. Сначала поддержать segment-level ASR output в pipeline:
   - `segments[]`: `start`, `end`, `text`, optional `speaker`;
   - no mandatory `words[]`.
3. Для e2e CTC использовать VAD-based chunks:
   - short speech chunks до 20-25 секунд;
   - padding до/после фразы;
   - merge маленьких adjacent chunks;
   - reject слишком коротких/noisy chunks или отправлять их в fallback.
4. Сохранить текущий GigaSTT как default, пока новый профиль не пройдет private benchmark на `Носников`, `Оля` и `Модуль 3`.
5. Рассмотреть e2e CTC как второй ASR-слой:
   - GigaSTT остается источником word timestamps;
   - e2e CTC дает cleaner text для тех же speech windows;
   - repair/ensemble выбирает между raw/edited/e2e по локальному confidence и reference benchmark.

## Next implementation slice

Минимальная полезная разработка:

- `P0-005`: engine registry должен уметь показывать `handy-gigaam-v3-e2e-ctc` как `experimental/missing` с понятным next step;
- `P0-010`: добавить reusable local helper для CTC candidate generation из WAV + diarization turns, но пока не включать по умолчанию;
- `P0-003/P0-004`: не смешивать с этой работой, потому что long-file resume и batch reliability не зависят от выбранного ASR.

Definition of Done для следующего slice:

- candidate helper не читает приватные Handy history/recordings;
- модель читается read-only из configured path или ignored `.models/`;
- отсутствие Handy model объясняется в UI человеческим языком;
- private benchmark умеет сравнить `handy-gigaam-v3-e2e-ctc` рядом с current raw/edited.
