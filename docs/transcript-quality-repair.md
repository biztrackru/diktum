# Transcript Quality Repair Plan

Дата: 2026-06-29.

## Задача

Текущий pipeline уже умеет получать raw ASR, diarization, clean exports и diagnostics. Но итоговый текст все еще может терять смысл: отдельные слова искажаются, пунктуация ломается, регистр становится случайным, а одна человеческая фраза иногда разрезается между соседними speaker turns.

Цель `P0-010 Transcript Quality Repair And Postprocessing` - добавить проверяемый слой качества поверх raw transcript. Raw результат должен оставаться доступным всегда, а исправленная версия должна быть отдельным артефактом с понятным журналом изменений.

Приватные фрагменты пользователя, аудио, transcripts и эталонные ответы нельзя коммитить. Для оценки качества использовать local-only fixtures или заметки вне git.

## Классы проблем

- ASR lexical loss: отдельные слова пропущены, склеены или заменены похожим звучанием.
- Broken punctuation: вопросы и законченные фразы превращаются в поток без границ.
- Broken casing: случайные заглавные буквы, all-caps токены и предложения без прописной буквы.
- Speaker fragmentation: одна фраза разделена между соседними speaker labels из-за коротких speaker islands.
- Context loss at chunk boundaries: ошибка появляется около границы ASR chunk/window.
- Domain vocabulary: имена, термины обучения, фамилии и профессиональные слова распознаются нестабильно.

## Принципы

- Не перезаписывать raw ASR, diarization JSON и raw markdown.
- Любой repair экспортировать отдельно: например `*.edited.md`, `*.edited.txt`, `*.repair.json`.
- Сохранять timestamps и speaker labels; если speaker boundary выглядит сомнительно, помечать это как uncertain.
- Не делать внешний API-вызов с аудио или текстом по умолчанию.
- Local LLM допустим только как явный профиль, например LM Studio/OpenAI-compatible endpoint на `localhost`.
- Не переписывать весь многочасовой файл одним opaque prompt. Работать короткими windows с соседним контекстом.
- Разделять "text repair" и "targeted re-ASR": если слов нет в raw тексте, LLM не должен уверенно додумывать их без аудио или альтернативного ASR.

## Предлагаемый pipeline

1. Detect suspicious spans.

   Использовать `asr_quality`, `speaker_quality`, segment length, punctuation density, all-caps artifacts, very short turns, chunk boundaries and suspicious tokens.

2. Build local repair windows.

   Для каждого span собрать соседние сегменты до/после, speaker labels, timestamps, source engine, chunk metadata and diagnostics. Не включать лишний приватный контекст сверх нужного окна.

3. Choose repair mode.

   - `punctuation-casing`: исправляет пунктуацию, регистр и очевидные склейки без изменения смысла.
   - `semantic-light`: осторожно правит очевидные ASR-искажения, но помечает unsure edits.
   - `targeted-reasr`: перезапускает ASR на коротком audio window или альтернативном engine profile, если текстовый repair не может восстановить смысл.

4. Produce artifacts.

   - `*.edited.md`: readable edited transcript.
   - `*.edited.txt`: edited transcript without markdown.
   - `*.repair.json`: spans, original text, edited text, confidence/status, reasons, model/profile used.
   - Optional diagnostic markdown with raw vs edited excerpts.

5. Show in UI.

   Result card should show whether edited transcript exists. Exports should expose raw/clean/edited variants separately. User should be able to open raw and edited files by click.

## Local LLM profile

Первый pragmatic target - LM Studio с OpenAI-compatible local server:

- endpoint: configurable local URL, default disabled;
- model: user-selected local model;
- privacy: text goes only to local endpoint;
- timeout/retry: short windows, resumable queue;
- prompt: strict editor role, no new facts, preserve timestamps/speakers, mark uncertainty.

This belongs near `P0-005 Engine Registry And Model Profiles`, but can start as an optional transcript-repair profile if the registry is not finished yet.

## Targeted Re-ASR

Если span явно потерял слова или смысл, text-only repair недостаточен. Тогда нужен режим:

- взять audio window with padding around timestamps;
- rerun ASR with shorter chunk/window or alternate engine profile;
- compare candidate text against raw text;
- keep both candidates when confidence is low;
- never silently replace long regions without repair manifest entry.

This depends on stable long-file resume/progress from `P0-003` and engine profiles from `P0-005`, but the acceptance benchmark can start earlier on short private windows.

## Acceptance Benchmark

Public/git-safe fixtures:

- synthetic manifest/result snippets with artificial punctuation/casing/speaker-island problems;
- no private audio or real transcript text.

Private local benchmark:

- user-selected problematic spans from real recordings;
- optional reference text from another trusted service or manual correction;
- stored under ignored local path, for example `.local-quality/`, never committed.
- run with `benchmark-quality` against existing manifest files; it compares raw transcript windows and deterministic edited windows with local references.

Scoring should track:

- punctuation/casing improvement;
- obvious ASR artifact reduction;
- sentence boundary quality;
- speaker boundary preservation or uncertainty marking;
- no hallucinated new claims;
- raw/edited diff readability.

## Local Reference Benchmark

Private references live outside git:

```text
.local-quality/
  references/
    nosnikov-external-service.json
    module-3-day-2-snippets.json
  reports/
    transcript-quality-benchmark.json
```

Reference file schema:

```json
{
  "references": [
    {
      "id": "nosnikov-000008-000139",
      "source": "Носников дапринт + нфло.m4a",
      "start": "00:00:08",
      "end": "00:01:39",
      "reference": "Paste trusted external-service or manual transcript text here.",
      "terms": ["email", "НФЛО"]
    }
  ]
}
```

Run benchmark for one result:

```bash
PYTHONPATH=app/src .venv/bin/python -m voice_recognizer.cli benchmark-quality \
  "outputs/pipeline/Носников_дапринт_+_нфло.manifest.json" \
  --references .local-quality/references \
  --output .local-quality/reports/nosnikov-quality.json
```

Run for all pipeline results:

```bash
PYTHONPATH=app/src .venv/bin/python -m voice_recognizer.cli benchmark-quality \
  outputs/pipeline \
  --recursive \
  --references .local-quality/references
```

The report contains average raw/edited token F1, word similarity, character similarity, punctuation density, term coverage and per-snippet winners. Token F1 is the main quick-read metric because it is more tolerant when an excerpt captures a little extra neighboring speech. With default `--include-excerpts`, the JSON report contains private transcript text, so keep it under `.local-quality/`.

## First Implementation Slice

1. Done: add a `repair-quality` CLI command that reads existing manifests and transcripts and produces `*.repair.json` with detected suspicious spans only.
2. Done: add synthetic tests for span detection without private data.
3. Done: add edited export generation for punctuation/casing repair with a deterministic local rule-based baseline.
4. Done: add `benchmark-quality` for private local reference snippets in ignored `.local-quality/`.
5. Add optional LM Studio repair profile behind explicit config.
6. Done for the first UI slice: `process` writes edited exports, the Text tab prefers `*.edited.md` / `*.edited.txt`, file links label edited artifacts as primary results, and applying speaker names rewrites edited exports.

This order gives us a safe baseline before asking a neural model to rewrite anything.
