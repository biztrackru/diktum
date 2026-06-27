from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from voice_recognizer.audio import AudioToolError, iter_media_files, normalize_audio, probe_audio, safe_stem
from voice_recognizer.diarization import (
    DiarizationError,
    assign_speakers,
    load_diarization_json,
    resolve_hf_token,
    run_pyannote,
    write_diarization_json,
)
from voice_recognizer.engines import ASR_ENGINE_LABELS, DEFAULT_ASR_ENGINE, normalize_asr_engine
from voice_recognizer.formatting import TranscriptSegment, write_markdown
from voice_recognizer.gigastt import (
    GigasttError,
    GigasttResult,
    GigasttSegment,
    GigasttWord,
    load_result,
    run_gigastt,
    segment_words,
    write_clean_markdown,
    write_plain_text,
    write_readable_markdown,
)


app = typer.Typer(no_args_is_help=True)
console = Console()

GIGASTT_SAFE_SINGLE_FILE_SECONDS = 6900.0
DEFAULT_ASR_CHUNK_SECONDS = 3600.0
MIN_ASR_CHUNK_SECONDS = 10.0
MIN_ASR_TAIL_SECONDS = 5.0


@dataclass(frozen=True)
class PipelineOutputs:
    asr_json: Path
    diarization_json: Path
    detailed_markdown: Path
    clean_timestamps_markdown: Path
    clean_markdown: Path
    clean_text: Path
    timeline_text: Path
    manifest_json: Path
    sample_paths: dict[int, Path]
    duration: float
    engine_seconds: float | None
    diarization_seconds: float | None
    word_count: int
    speaker_count: int
    asr_engine: str


@dataclass(frozen=True)
class AsrChunk:
    index: int
    start: float
    duration: float
    audio_path: Path
    json_path: Path


def _run_gigastt_to_outputs(
    *,
    source: Path,
    recognition_source: Path,
    stem: str,
    output_dir: Path,
    model_dir: Path,
    punct_model_dir: Path,
    gigastt_bin: Path,
    hotwords_file: Path | None = None,
    hotwords_default: bool = False,
    diarization_json: Path | None = None,
    max_gap_seconds: float = 1.8,
) -> tuple[Path, Path, float, float, int, int]:
    output_json = output_dir / f"{stem}.gigastt.json"
    output_markdown = output_dir / f"{stem}.transcript.md"
    if hotwords_file is not None:
        console.print(f"[cyan]ASR hotwords:[/cyan] {hotwords_file}")
    if hotwords_default:
        console.print("[cyan]ASR hotwords:[/cyan] built-in default lexicon enabled")
    engine_seconds = run_gigastt(
        gigastt_bin=gigastt_bin,
        source=recognition_source,
        output_json=output_json,
        model_dir=model_dir,
        punct_model_dir=punct_model_dir,
        hotwords_file=hotwords_file,
        hotwords_default=hotwords_default,
    )
    result = load_result(output_json)
    if diarization_json is not None:
        result = assign_speakers(result, load_diarization_json(diarization_json))
    segments = segment_words(result.words, max_gap_seconds=max_gap_seconds)
    write_readable_markdown(
        output_markdown,
        title=source.stem,
        result=result,
        segments=segments,
        engine_seconds=engine_seconds,
    )
    speaker_count = len({word.speaker for word in result.words if word.speaker is not None})
    return output_json, output_markdown, result.duration, engine_seconds, len(result.words), speaker_count


def _clip_suffix(start: float | None, duration: float | None) -> str:
    if start is None and duration is None:
        return ""
    start_label = int(start or 0)
    duration_label = int(duration or 0)
    return f"_{start_label}s_{duration_label}s"


def _load_speaker_config(path: Path | None) -> dict[str, dict[str, object]]:
    resolved_path = _resolve_speaker_config_path(path)
    if resolved_path is None:
        return {}
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict)
    }


def _resolve_speaker_config_path(path: Path | None) -> Path | None:
    if path is not None:
        return path if path.exists() else None
    app_dir = Path(__file__).resolve().parents[2]
    candidates = (
        Path("config/speaker-counts.json"),
        Path("app/config/speaker-counts.json"),
        app_dir / "config" / "speaker-counts.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_hotwords_path(path: Path | None) -> Path | None:
    if path is not None:
        if not path.exists():
            raise typer.BadParameter(f"hotwords file not found: {path}")
        return path
    app_dir = Path(__file__).resolve().parents[2]
    candidates = (
        Path("app/config/hotwords.txt"),
        Path("config/hotwords.txt"),
        app_dir / "config" / "hotwords.txt",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _speaker_settings_for_source(
    source: Path,
    speaker_config: dict[str, dict[str, object]],
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> tuple[int | None, int | None, int | None]:
    settings = {}
    for key in (source.name, source.stem, safe_stem(source)):
        if key in speaker_config:
            settings = speaker_config[key]
            break
    return (
        num_speakers if num_speakers is not None else _optional_int(settings.get("num_speakers")),
        min_speakers if min_speakers is not None else _optional_int(settings.get("min_speakers")),
        max_speakers if max_speakers is not None else _optional_int(settings.get("max_speakers")),
    )


def _speaker_names_for_source(
    source: Path,
    speaker_config: dict[str, dict[str, object]],
    explicit_names: str | None = None,
) -> dict[int, str]:
    names: dict[int, str] = {}
    settings = {}
    for key in (source.name, source.stem, safe_stem(source)):
        if key in speaker_config:
            settings = speaker_config[key]
            break
    configured = settings.get("speaker_names")
    if isinstance(configured, dict):
        for key, value in configured.items():
            index = _speaker_index_from_key(str(key))
            if index is not None and str(value).strip():
                names[index] = str(value).strip()
    elif isinstance(configured, list):
        for index, value in enumerate(configured):
            if str(value).strip():
                names[index] = str(value).strip()
    names.update(_parse_speaker_names(explicit_names))
    return names


def _parse_speaker_names(value: str | None) -> dict[int, str]:
    if not value:
        return {}
    names: dict[int, str] = {}
    normalized = value.replace(",", "\n").replace(";", "\n")
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            key, name = line.split("=", 1)
        elif ":" in line:
            key, name = line.split(":", 1)
        else:
            continue
        index = _speaker_index_from_key(key)
        name = name.strip()
        if index is not None and name:
            names[index] = name
    return names


def _speaker_index_from_key(value: str) -> int | None:
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return None
    index = int(digits) - 1
    return index if index >= 0 else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _plan_asr_chunks(
    *,
    duration_seconds: float,
    chunk_seconds: float,
    cache_dir: Path,
    output_dir: Path,
    stem: str,
) -> list[AsrChunk]:
    if duration_seconds <= 0:
        return []
    if chunk_seconds < MIN_ASR_CHUNK_SECONDS:
        raise GigasttError(f"ASR chunk size must be at least {MIN_ASR_CHUNK_SECONDS:.0f}s")
    chunks: list[AsrChunk] = []
    start = 0.0
    while start < duration_seconds:
        remaining = duration_seconds - start
        if chunks and remaining <= MIN_ASR_TAIL_SECONDS:
            previous = chunks[-1]
            chunks[-1] = AsrChunk(
                index=previous.index,
                start=previous.start,
                duration=previous.duration + remaining,
                audio_path=previous.audio_path,
                json_path=previous.json_path,
            )
            break
        current_duration = min(chunk_seconds, remaining)
        index = len(chunks) + 1
        chunks.append(
            AsrChunk(
                index=index,
                start=start,
                duration=current_duration,
                audio_path=cache_dir / f"{stem}.part-{index:03d}.wav",
                json_path=output_dir / f"{stem}.part-{index:03d}.gigastt.json",
            )
        )
        start += current_duration
    return chunks


def _run_asr_to_json(
    *,
    audio_path: Path,
    asr_json: Path,
    cache_dir: Path,
    output_dir: Path,
    stem: str,
    gigastt_bin: Path,
    model_dir: Path,
    punct_model_dir: Path,
    hotwords_file: Path | None,
    hotwords_default: bool,
    chunk_seconds: float,
    skip_existing: bool,
) -> float:
    audio_duration = probe_audio(audio_path).duration_seconds
    if chunk_seconds <= 0 or audio_duration <= GIGASTT_SAFE_SINGLE_FILE_SECONDS:
        return run_gigastt(
            gigastt_bin=gigastt_bin,
            source=audio_path,
            output_json=asr_json,
            model_dir=model_dir,
            punct_model_dir=punct_model_dir,
            hotwords_file=hotwords_file,
            hotwords_default=hotwords_default,
        )

    safe_chunk_seconds = min(chunk_seconds, GIGASTT_SAFE_SINGLE_FILE_SECONDS)
    chunks = _plan_asr_chunks(
        duration_seconds=audio_duration,
        chunk_seconds=safe_chunk_seconds,
        cache_dir=cache_dir,
        output_dir=output_dir,
        stem=stem,
    )
    console.print(
        f"[cyan]ASR chunking:[/cyan] {len(chunks)} parts, "
        f"up to {safe_chunk_seconds:.0f}s each for {audio_duration:.1f}s audio"
    )
    total_engine_seconds = 0.0
    combined_words: list[GigasttWord] = []
    text_parts: list[str] = []
    for chunk in chunks:
        if skip_existing and chunk.audio_path.exists():
            console.print(f"[yellow]Using ASR chunk audio:[/yellow] {chunk.audio_path}")
        else:
            normalize_audio(audio_path, chunk.audio_path, start=chunk.start, duration=chunk.duration)
        if skip_existing and chunk.json_path.exists():
            console.print(f"[yellow]Using ASR chunk JSON:[/yellow] {chunk.json_path}")
        else:
            console.print(
                f"[cyan]ASR chunk {chunk.index}/{len(chunks)}:[/cyan] "
                f"{chunk.start:.1f}s + {chunk.duration:.1f}s"
            )
            total_engine_seconds += run_gigastt(
                gigastt_bin=gigastt_bin,
                source=chunk.audio_path,
                output_json=chunk.json_path,
                model_dir=model_dir,
                punct_model_dir=punct_model_dir,
                hotwords_file=hotwords_file,
                hotwords_default=hotwords_default,
            )
        chunk_result = load_result(chunk.json_path)
        if chunk_result.text:
            text_parts.append(chunk_result.text)
        combined_words.extend(_shift_gigastt_words(chunk_result.words, offset=chunk.start, max_end=audio_duration))

    _write_gigastt_json(
        asr_json,
        GigasttResult(
            duration=audio_duration,
            text=" ".join(part for part in text_parts if part).strip(),
            words=combined_words,
        ),
    )
    console.print(f"[green]Combined ASR JSON:[/green] {asr_json}")
    return total_engine_seconds


def _shift_gigastt_words(words: list[GigasttWord], *, offset: float, max_end: float) -> list[GigasttWord]:
    shifted: list[GigasttWord] = []
    for word in words:
        start = max(0.0, word.start + offset)
        end = min(max_end, max(start, word.end + offset))
        shifted.append(
            GigasttWord(
                start=start,
                end=end,
                word=word.word,
                confidence=word.confidence,
                speaker=word.speaker,
            )
        )
    return shifted


def _write_gigastt_json(path: Path, result: GigasttResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "duration": result.duration,
        "text": result.text,
        "words": [
            {
                "confidence": word.confidence,
                "end": word.end,
                "start": word.start,
                "word": word.word,
                **({"speaker": word.speaker} if word.speaker is not None else {}),
            }
            for word in result.words
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def _render_transcript_bundle(
    *,
    source: Path,
    stem: str,
    output_dir: Path,
    result: GigasttResult,
    segments: list[GigasttSegment],
    engine_seconds: float | None,
    speaker_names: dict[int, str],
) -> dict[str, Path]:
    detailed_markdown = output_dir / f"{stem}.transcript.md"
    clean_timestamps_markdown = output_dir / f"{stem}.clean.timestamps.md"
    clean_markdown = output_dir / f"{stem}.clean.md"
    clean_text = output_dir / f"{stem}.clean.txt"
    timeline_text = output_dir / f"{stem}.timeline.txt"
    write_readable_markdown(
        detailed_markdown,
        title=source.stem,
        result=result,
        segments=segments,
        engine_seconds=engine_seconds,
        speaker_names=speaker_names,
    )
    write_clean_markdown(
        clean_timestamps_markdown,
        title=source.stem,
        segments=segments,
        speaker_names=speaker_names,
        include_timestamps=True,
    )
    write_clean_markdown(
        clean_markdown,
        title=source.stem,
        segments=segments,
        speaker_names=speaker_names,
        include_timestamps=False,
    )
    write_plain_text(
        clean_text,
        segments=segments,
        speaker_names=speaker_names,
        include_timestamps=False,
    )
    write_plain_text(
        timeline_text,
        segments=segments,
        speaker_names=speaker_names,
        include_timestamps=True,
    )
    return {
        "detailed_markdown": detailed_markdown,
        "clean_timestamps_markdown": clean_timestamps_markdown,
        "clean_markdown": clean_markdown,
        "clean_text": clean_text,
        "timeline_text": timeline_text,
    }


def _write_speaker_samples(
    *,
    audio_path: Path,
    output_dir: Path,
    stem: str,
    turns: list,
    max_seconds: float = 8.0,
) -> dict[int, Path]:
    sample_paths: dict[int, Path] = {}
    longest_turns = {}
    for turn in turns:
        duration = max(0.0, turn.end - turn.start)
        if duration < 0.6:
            continue
        existing = longest_turns.get(turn.speaker)
        if existing is None or duration > existing.end - existing.start:
            longest_turns[turn.speaker] = turn
    for speaker, turn in sorted(longest_turns.items()):
        sample_duration = min(max_seconds, max(0.6, turn.end - turn.start))
        target = output_dir / f"{stem}.speaker-{speaker + 1}.sample.wav"
        normalize_audio(audio_path, target, start=max(0.0, turn.start), duration=sample_duration)
        sample_paths[speaker] = target
    return sample_paths


def _write_manifest(
    path: Path,
    *,
    source: Path,
    audio_path: Path,
    asr_json: Path,
    diarization_json: Path,
    outputs: dict[str, Path],
    sample_paths: dict[int, Path],
    speaker_names: dict[int, str],
    duration: float,
    word_count: int,
    speaker_count: int,
    asr_engine: str,
    device: str,
    hotwords_file: Path | None,
    hotwords_default: bool,
    start: float | None,
    clip_duration: float | None,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
    created_at: float,
    completed_at: float,
) -> Path:
    try:
        source_stat = source.stat()
        source_size: int | None = source_stat.st_size
        source_mtime: float | None = source_stat.st_mtime
    except OSError:
        source_size = None
        source_mtime = None
    payload = {
        "manifest_version": 2,
        "status": "done",
        "created_at": created_at,
        "completed_at": completed_at,
        "source": str(source),
        "source_size": source_size,
        "source_mtime": source_mtime,
        "audio": str(audio_path),
        "duration": duration,
        "result_duration": duration,
        "clip_start": start,
        "clip_duration": clip_duration,
        "word_count": word_count,
        "speaker_count": speaker_count,
        "asr_engine": asr_engine,
        "device": device,
        "asr_hotwords_file": str(hotwords_file) if hotwords_file is not None else None,
        "asr_hotwords_default": hotwords_default,
        "speaker_constraints": {
            "num_speakers": num_speakers,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
        },
        "asr_json": str(asr_json),
        "diarization_json": str(diarization_json),
        "outputs": {key: str(value) for key, value in outputs.items()},
        "speaker_samples": {str(speaker + 1): str(path) for speaker, path in sample_paths.items()},
        "speaker_names": {str(speaker + 1): name for speaker, name in speaker_names.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_pipeline_to_outputs(
    *,
    source: Path,
    output_dir: Path,
    cache_dir: Path,
    model_dir: Path,
    punct_model_dir: Path,
    gigastt_bin: Path,
    hotwords_file: Path | None,
    hotwords_default: bool,
    asr_engine: str,
    pyannote_model_id: str,
    hf_token: str,
    device: str,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
    start: float | None = None,
    duration: float | None = None,
    asr_chunk_seconds: float = DEFAULT_ASR_CHUNK_SECONDS,
    max_gap_seconds: float = 1.8,
    speaker_names: dict[int, str] | None = None,
    smooth_speakers: bool = True,
    speaker_island_max_words: int = 2,
    speaker_island_max_seconds: float = 1.2,
    speaker_bridge_gap_seconds: float = 0.8,
    skip_existing: bool = True,
) -> PipelineOutputs:
    asr_engine = normalize_asr_engine(asr_engine)
    created_at = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{safe_stem(source)}{_clip_suffix(start, duration)}"
    audio_path = cache_dir / f"{stem}.wav"
    asr_json = output_dir / f"{stem}.gigastt.json"
    diarization_json = output_dir / f"{stem}.pyannote.json"
    manifest_json = output_dir / f"{stem}.manifest.json"
    speaker_names = speaker_names or {}
    if hotwords_file is not None:
        console.print(f"[cyan]ASR hotwords:[/cyan] {hotwords_file}")
    if hotwords_default:
        console.print("[cyan]ASR hotwords:[/cyan] built-in default lexicon enabled")

    if skip_existing and audio_path.exists():
        console.print(f"[yellow]Using prepared audio:[/yellow] {audio_path}")
    else:
        normalize_audio(source, audio_path, start=start, duration=duration)
        console.print(f"[green]Prepared audio:[/green] {audio_path}")

    engine_seconds: float | None = None
    if skip_existing and asr_json.exists():
        console.print(f"[yellow]Using ASR JSON:[/yellow] {asr_json}")
    else:
        console.print(f"[cyan]ASR engine:[/cyan] {ASR_ENGINE_LABELS[asr_engine]}")
        engine_seconds = _run_asr_to_json(
            audio_path=audio_path,
            asr_json=asr_json,
            cache_dir=cache_dir,
            output_dir=output_dir,
            stem=stem,
            gigastt_bin=gigastt_bin,
            model_dir=model_dir,
            punct_model_dir=punct_model_dir,
            hotwords_file=hotwords_file,
            hotwords_default=hotwords_default,
            chunk_seconds=asr_chunk_seconds,
            skip_existing=skip_existing,
        )
        console.print(f"[green]ASR JSON:[/green] {asr_json}")

    diarization_seconds: float | None = None
    if skip_existing and diarization_json.exists():
        console.print(f"[yellow]Using diarization JSON:[/yellow] {diarization_json}")
        turns = load_diarization_json(diarization_json)
    else:
        run = run_pyannote(
            audio_path=audio_path,
            model_id=pyannote_model_id,
            hf_token=hf_token,
            device=device,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        diarization_seconds = run.elapsed_seconds
        turns = run.turns
        write_diarization_json(
            diarization_json,
            audio_path=audio_path,
            model_id=pyannote_model_id,
            run=run,
        )
        console.print(f"[green]Diarization JSON:[/green] {diarization_json}")

    result = assign_speakers(
        load_result(asr_json),
        turns,
        smooth=smooth_speakers,
        island_max_words=speaker_island_max_words,
        island_max_seconds=speaker_island_max_seconds,
        bridge_gap_seconds=speaker_bridge_gap_seconds,
    )
    segments = segment_words(result.words, max_gap_seconds=max_gap_seconds)
    outputs = _render_transcript_bundle(
        source=source,
        stem=stem,
        output_dir=output_dir,
        result=result,
        segments=segments,
        engine_seconds=engine_seconds,
        speaker_names=speaker_names,
    )
    sample_paths = _write_speaker_samples(
        audio_path=audio_path,
        output_dir=output_dir,
        stem=stem,
        turns=turns,
    )
    speaker_count = len({word.speaker for word in result.words if word.speaker is not None})
    _write_manifest(
        manifest_json,
        source=source,
        audio_path=audio_path,
        asr_json=asr_json,
        diarization_json=diarization_json,
        outputs=outputs,
        sample_paths=sample_paths,
        speaker_names=speaker_names,
        duration=result.duration,
        word_count=len(result.words),
        speaker_count=speaker_count,
        asr_engine=asr_engine,
        device=device,
        hotwords_file=hotwords_file,
        hotwords_default=hotwords_default,
        start=start,
        clip_duration=duration,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        created_at=created_at,
        completed_at=time.time(),
    )
    console.print(f"[green]Markdown:[/green] {outputs['detailed_markdown']}")
    console.print(f"[green]Clean Markdown:[/green] {outputs['clean_markdown']}")
    console.print(f"[green]Clean TXT:[/green] {outputs['clean_text']}")
    console.print(f"[green]Manifest:[/green] {manifest_json}")
    return PipelineOutputs(
        asr_json=asr_json,
        diarization_json=diarization_json,
        detailed_markdown=outputs["detailed_markdown"],
        clean_timestamps_markdown=outputs["clean_timestamps_markdown"],
        clean_markdown=outputs["clean_markdown"],
        clean_text=outputs["clean_text"],
        timeline_text=outputs["timeline_text"],
        manifest_json=manifest_json,
        sample_paths=sample_paths,
        duration=result.duration,
        engine_seconds=engine_seconds,
        diarization_seconds=diarization_seconds,
        word_count=len(result.words),
        speaker_count=speaker_count,
        asr_engine=asr_engine,
    )


@app.command()
def inspect(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Show technical metadata for an audio file."""
    try:
        info = probe_audio(path)
    except AudioToolError as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title=str(path))
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("duration", info.duration_label)
    table.add_row("sample_rate", str(info.sample_rate or "unknown"))
    table.add_row("channels", str(info.channels or "unknown"))
    table.add_row("codec", info.codec or "unknown")
    console.print(table)


@app.command()
def prepare(
    source: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(Path(".cache/audio"), "--output-dir", "-o"),
    start: float | None = typer.Option(None, "--start", help="Start offset in seconds."),
    duration: float | None = typer.Option(None, "--duration", help="Clip duration in seconds."),
) -> Path:
    """Convert audio to mono 16 kHz WAV for ASR and diarization."""
    suffix = ""
    if start is not None or duration is not None:
        start_label = int(start or 0)
        duration_label = int(duration or 0)
        suffix = f"_{start_label}s_{duration_label}s"
    target = output_dir / f"{safe_stem(source)}{suffix}.wav"
    try:
        normalize_audio(source, target, start=start, duration=duration)
    except AudioToolError as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"[green]Prepared:[/green] {target}")
    return target


@app.command()
def demo_export(
    source: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs"), "--output-dir", "-o"),
) -> Path:
    """Create a placeholder Markdown transcript to verify output formatting."""
    info = probe_audio(source)
    segment = TranscriptSegment(
        start=0,
        end=min(info.duration_seconds, 30),
        speaker="Спикер 1",
        text="Здесь появится транскрипт после подключения ASR и диаризации.",
    )
    target = output_dir / f"{safe_stem(source)}.md"
    write_markdown(target, title=source.stem, segments=[segment])
    console.print(f"[green]Exported:[/green] {target}")
    return target


@app.command("transcribe-gigastt")
def transcribe_gigastt(
    source: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs"), "--output-dir", "-o"),
    model_dir: Path = typer.Option(Path(".models/gigastt"), "--model-dir"),
    punct_model_dir: Path = typer.Option(Path(".models/gigastt/punct"), "--punct-model-dir"),
    gigastt_bin: Path = typer.Option(Path("tools/bin/gigastt"), "--gigastt-bin"),
    hotwords_file: Path | None = typer.Option(None, "--hotwords-file"),
    hotwords_default: bool = typer.Option(False, "--hotwords-default"),
    start: float | None = typer.Option(None, "--start", help="Start offset in seconds."),
    duration: float | None = typer.Option(None, "--duration", help="Clip duration in seconds."),
    diarization_json: Path | None = typer.Option(None, "--diarization-json", exists=True, readable=True),
    max_gap_seconds: float = typer.Option(1.8, "--max-gap", help="Pause that starts a new segment."),
) -> None:
    """Run the local GigaSTT baseline and export raw JSON plus readable Markdown."""
    stem = safe_stem(source)
    recognition_source = source
    if start is not None or duration is not None:
        start_label = int(start or 0)
        duration_label = int(duration or 0)
        recognition_source = Path(".cache/audio") / f"{stem}_{start_label}s_{duration_label}s.wav"
        try:
            normalize_audio(source, recognition_source, start=start, duration=duration)
        except AudioToolError as error:
            raise typer.BadParameter(str(error)) from error
        stem = recognition_source.stem
        console.print(f"[green]Prepared clip:[/green] {recognition_source}")

    output_json = output_dir / f"{stem}.gigastt.json"
    resolved_hotwords = _resolve_hotwords_path(hotwords_file)
    try:
        output_json, output_markdown, result_duration, engine_seconds, _, _ = _run_gigastt_to_outputs(
            source=source,
            recognition_source=recognition_source,
            stem=stem,
            output_dir=output_dir,
            model_dir=model_dir,
            punct_model_dir=punct_model_dir,
            gigastt_bin=gigastt_bin,
            hotwords_file=resolved_hotwords,
            hotwords_default=hotwords_default,
            diarization_json=diarization_json,
            max_gap_seconds=max_gap_seconds,
        )
    except (GigasttError, subprocess.CalledProcessError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"[green]Raw JSON:[/green] {output_json}")
    console.print(f"[green]Markdown:[/green] {output_markdown}")
    console.print(
        f"[cyan]Processed {result_duration:.1f}s in {engine_seconds:.2f}s "
        f"(RTF {engine_seconds / result_duration:.3f}).[/cyan]"
    )


@app.command("batch-gigastt")
def batch_gigastt(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output_dir: Path = typer.Option(Path("outputs/batch"), "--output-dir", "-o"),
    model_dir: Path = typer.Option(Path(".models/gigastt"), "--model-dir"),
    punct_model_dir: Path = typer.Option(Path(".models/gigastt/punct"), "--punct-model-dir"),
    gigastt_bin: Path = typer.Option(Path("tools/bin/gigastt"), "--gigastt-bin"),
    hotwords_file: Path | None = typer.Option(None, "--hotwords-file"),
    hotwords_default: bool = typer.Option(False, "--hotwords-default"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    max_gap_seconds: float = typer.Option(1.8, "--max-gap", help="Pause that starts a new segment."),
    skip_existing: bool = typer.Option(True, "--skip-existing/--overwrite"),
) -> None:
    """Transcribe every supported media file in a folder and write a batch index."""
    files = iter_media_files(input_dir, recursive=recursive)
    if not files:
        console.print(f"[yellow]No supported media files found in {input_dir}.[/yellow]")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_hotwords = _resolve_hotwords_path(hotwords_file)
    rows: list[tuple[Path, Path, Path, float, float, int, int, str]] = []
    for index, source in enumerate(files, start=1):
        stem = safe_stem(source)
        output_json = output_dir / f"{stem}.gigastt.json"
        output_markdown = output_dir / f"{stem}.transcript.md"
        console.print(f"[cyan][{index}/{len(files)}][/cyan] {source.name}")
        if skip_existing and output_json.exists() and output_markdown.exists():
            result = load_result(output_json)
            speaker_count = len({word.speaker for word in result.words if word.speaker is not None})
            rows.append((source, output_json, output_markdown, result.duration, 0.0, len(result.words), speaker_count, "skipped"))
            console.print("[yellow]Skipped existing result.[/yellow]")
            continue
        try:
            result_json, result_markdown, duration, engine_seconds, word_count, speaker_count = _run_gigastt_to_outputs(
                source=source,
                recognition_source=source,
                stem=stem,
                output_dir=output_dir,
                model_dir=model_dir,
                punct_model_dir=punct_model_dir,
                gigastt_bin=gigastt_bin,
                hotwords_file=resolved_hotwords,
                hotwords_default=hotwords_default,
                max_gap_seconds=max_gap_seconds,
            )
        except (GigasttError, subprocess.CalledProcessError) as error:
            rows.append((source, output_json, output_markdown, 0.0, 0.0, 0, 0, f"error: {error}"))
            console.print(f"[red]Failed:[/red] {error}")
            continue
        rows.append((source, result_json, result_markdown, duration, engine_seconds, word_count, speaker_count, "ok"))
        console.print(f"[green]Done[/green] {duration:.1f}s audio in {engine_seconds:.2f}s")

    index_path = output_dir / "batch_index.md"
    _write_batch_index(index_path, rows)
    console.print(f"[green]Batch index:[/green] {index_path}")


@app.command("process")
def process_file(
    source: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs/pipeline"), "--output-dir", "-o"),
    cache_dir: Path = typer.Option(Path(".cache/audio"), "--cache-dir"),
    speaker_config_path: Path | None = typer.Option(None, "--speaker-config"),
    model_dir: Path = typer.Option(Path(".models/gigastt"), "--model-dir"),
    punct_model_dir: Path = typer.Option(Path(".models/gigastt/punct"), "--punct-model-dir"),
    gigastt_bin: Path = typer.Option(Path("tools/bin/gigastt"), "--gigastt-bin"),
    hotwords_file: Path | None = typer.Option(None, "--hotwords-file"),
    hotwords_default: bool = typer.Option(False, "--hotwords-default"),
    asr_engine: str = typer.Option(
        DEFAULT_ASR_ENGINE,
        "--asr-engine",
        help="ASR backend. Currently supported: gigastt-gigaam-v3.",
    ),
    pyannote_model_id: str = typer.Option("pyannote/speaker-diarization-community-1", "--pyannote-model-id"),
    hf_token_env: str = typer.Option("HF_TOKEN", "--hf-token-env"),
    device: str = typer.Option("auto", "--device", help="auto, mps, cpu, or cuda. auto uses Apple MPS when available."),
    start: float | None = typer.Option(None, "--start", help="Start offset in seconds."),
    duration: float | None = typer.Option(None, "--duration", help="Clip duration in seconds."),
    num_speakers: int | None = typer.Option(None, "--num-speakers"),
    min_speakers: int | None = typer.Option(None, "--min-speakers"),
    max_speakers: int | None = typer.Option(None, "--max-speakers"),
    speaker_names: str | None = typer.Option(
        None,
        "--speaker-names",
        help="Speaker name mapping, for example: 1=Андрей,2=Ольга",
    ),
    asr_chunk_seconds: float = typer.Option(
        DEFAULT_ASR_CHUNK_SECONDS,
        "--asr-chunk-seconds",
        help="GigaSTT chunk size for files longer than the safe single-file limit. Use 0 to disable.",
    ),
    max_gap_seconds: float = typer.Option(1.8, "--max-gap", help="Pause that starts a new segment."),
    smooth_speakers: bool = typer.Option(True, "--smooth-speakers/--no-smooth-speakers"),
    speaker_island_max_words: int = typer.Option(2, "--speaker-island-max-words"),
    speaker_island_max_seconds: float = typer.Option(1.2, "--speaker-island-max-seconds"),
    speaker_bridge_gap_seconds: float = typer.Option(0.8, "--speaker-bridge-gap"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--overwrite"),
) -> None:
    """Run ASR + pyannote diarization and export a speaker-labelled Markdown transcript."""
    try:
        resolved_asr_engine = normalize_asr_engine(asr_engine)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    speaker_config = _load_speaker_config(speaker_config_path)
    resolved_hotwords = _resolve_hotwords_path(hotwords_file)
    resolved_num, resolved_min, resolved_max = _speaker_settings_for_source(
        source,
        speaker_config,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    resolved_names = _speaker_names_for_source(source, speaker_config, speaker_names)
    console.print(f"[cyan]ASR engine:[/cyan] {ASR_ENGINE_LABELS[resolved_asr_engine]}")
    console.print(f"[cyan]Speaker constraint:[/cyan] {_speaker_constraint_label(resolved_num, resolved_min, resolved_max)}")
    if resolved_names:
        console.print(f"[cyan]Speaker names:[/cyan] {_speaker_names_label(resolved_names)}")
    try:
        outputs = _run_pipeline_to_outputs(
            source=source,
            output_dir=output_dir,
            cache_dir=cache_dir,
            model_dir=model_dir,
            punct_model_dir=punct_model_dir,
            gigastt_bin=gigastt_bin,
            hotwords_file=resolved_hotwords,
            hotwords_default=hotwords_default,
            asr_engine=resolved_asr_engine,
            pyannote_model_id=pyannote_model_id,
            hf_token=resolve_hf_token(hf_token_env),
            device=device,
            num_speakers=resolved_num,
            min_speakers=resolved_min,
            max_speakers=resolved_max,
            start=start,
            duration=duration,
            asr_chunk_seconds=asr_chunk_seconds,
            max_gap_seconds=max_gap_seconds,
            speaker_names=resolved_names,
            smooth_speakers=smooth_speakers,
            speaker_island_max_words=speaker_island_max_words,
            speaker_island_max_seconds=speaker_island_max_seconds,
            speaker_bridge_gap_seconds=speaker_bridge_gap_seconds,
            skip_existing=skip_existing,
        )
    except (AudioToolError, DiarizationError, GigasttError, subprocess.CalledProcessError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print(
        f"[cyan]Done: {outputs.duration:.1f}s audio, {outputs.word_count} words, "
        f"{outputs.speaker_count} speakers. ASR: {_seconds_label(outputs.engine_seconds)}, "
        f"diarization: {_seconds_label(outputs.diarization_seconds)}.[/cyan]"
    )


@app.command("batch-process")
def batch_process(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output_dir: Path = typer.Option(Path("outputs/pipeline-batch"), "--output-dir", "-o"),
    cache_dir: Path = typer.Option(Path(".cache/audio"), "--cache-dir"),
    speaker_config_path: Path | None = typer.Option(None, "--speaker-config"),
    model_dir: Path = typer.Option(Path(".models/gigastt"), "--model-dir"),
    punct_model_dir: Path = typer.Option(Path(".models/gigastt/punct"), "--punct-model-dir"),
    gigastt_bin: Path = typer.Option(Path("tools/bin/gigastt"), "--gigastt-bin"),
    hotwords_file: Path | None = typer.Option(None, "--hotwords-file"),
    hotwords_default: bool = typer.Option(False, "--hotwords-default"),
    asr_engine: str = typer.Option(
        DEFAULT_ASR_ENGINE,
        "--asr-engine",
        help="ASR backend. Currently supported: gigastt-gigaam-v3.",
    ),
    pyannote_model_id: str = typer.Option("pyannote/speaker-diarization-community-1", "--pyannote-model-id"),
    hf_token_env: str = typer.Option("HF_TOKEN", "--hf-token-env"),
    device: str = typer.Option("auto", "--device", help="auto, mps, cpu, or cuda. auto uses Apple MPS when available."),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    start: float | None = typer.Option(None, "--start", help="Start offset in seconds for every file."),
    duration: float | None = typer.Option(None, "--duration", help="Clip duration in seconds for every file."),
    asr_chunk_seconds: float = typer.Option(
        DEFAULT_ASR_CHUNK_SECONDS,
        "--asr-chunk-seconds",
        help="GigaSTT chunk size for files longer than the safe single-file limit. Use 0 to disable.",
    ),
    max_gap_seconds: float = typer.Option(1.8, "--max-gap", help="Pause that starts a new segment."),
    smooth_speakers: bool = typer.Option(True, "--smooth-speakers/--no-smooth-speakers"),
    speaker_island_max_words: int = typer.Option(2, "--speaker-island-max-words"),
    speaker_island_max_seconds: float = typer.Option(1.2, "--speaker-island-max-seconds"),
    speaker_bridge_gap_seconds: float = typer.Option(0.8, "--speaker-bridge-gap"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--overwrite"),
) -> None:
    """Run the full speaker-labelled pipeline for every supported media file in a folder."""
    try:
        resolved_asr_engine = normalize_asr_engine(asr_engine)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    files = iter_media_files(input_dir, recursive=recursive)
    if not files:
        console.print(f"[yellow]No supported media files found in {input_dir}.[/yellow]")
        return

    speaker_config = _load_speaker_config(speaker_config_path)
    resolved_hotwords = _resolve_hotwords_path(hotwords_file)
    try:
        hf_token = resolve_hf_token(hf_token_env)
    except DiarizationError as error:
        raise typer.BadParameter(str(error)) from error

    rows: list[tuple[Path, Path, Path, Path, float, float | None, float | None, int, int, str]] = []
    for index, source in enumerate(files, start=1):
        resolved_num, resolved_min, resolved_max = _speaker_settings_for_source(source, speaker_config)
        resolved_names = _speaker_names_for_source(source, speaker_config)
        console.print(f"[cyan][{index}/{len(files)}][/cyan] {source.name}")
        console.print(f"[cyan]ASR engine:[/cyan] {ASR_ENGINE_LABELS[resolved_asr_engine]}")
        console.print(f"[cyan]Speaker constraint:[/cyan] {_speaker_constraint_label(resolved_num, resolved_min, resolved_max)}")
        if resolved_names:
            console.print(f"[cyan]Speaker names:[/cyan] {_speaker_names_label(resolved_names)}")
        try:
            outputs = _run_pipeline_to_outputs(
                source=source,
                output_dir=output_dir,
                cache_dir=cache_dir,
                model_dir=model_dir,
                punct_model_dir=punct_model_dir,
                gigastt_bin=gigastt_bin,
                hotwords_file=resolved_hotwords,
                hotwords_default=hotwords_default,
                asr_engine=resolved_asr_engine,
                pyannote_model_id=pyannote_model_id,
                hf_token=hf_token,
                device=device,
                num_speakers=resolved_num,
                min_speakers=resolved_min,
                max_speakers=resolved_max,
                start=start,
                duration=duration,
                asr_chunk_seconds=asr_chunk_seconds,
                max_gap_seconds=max_gap_seconds,
                speaker_names=resolved_names,
                smooth_speakers=smooth_speakers,
                speaker_island_max_words=speaker_island_max_words,
                speaker_island_max_seconds=speaker_island_max_seconds,
                speaker_bridge_gap_seconds=speaker_bridge_gap_seconds,
                skip_existing=skip_existing,
            )
        except (AudioToolError, DiarizationError, GigasttError, subprocess.CalledProcessError) as error:
            stem = f"{safe_stem(source)}{_clip_suffix(start, duration)}"
            rows.append(
                (
                    source,
                    output_dir / f"{stem}.gigastt.json",
                    output_dir / f"{stem}.pyannote.json",
                    output_dir / f"{stem}.transcript.md",
                    0.0,
                    None,
                    None,
                    0,
                    0,
                    f"error: {error}",
                )
            )
            console.print(f"[red]Failed:[/red] {error}")
            continue
        rows.append(
            (
                source,
                outputs.asr_json,
                outputs.diarization_json,
                outputs.detailed_markdown,
                outputs.duration,
                outputs.engine_seconds,
                outputs.diarization_seconds,
                outputs.word_count,
                outputs.speaker_count,
                "ok",
            )
        )

    index_path = output_dir / "batch_index.md"
    _write_pipeline_batch_index(index_path, rows)
    console.print(f"[green]Batch index:[/green] {index_path}")


@app.command("diarize-pyannote")
def diarize_pyannote(
    source: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs"), "--output-dir", "-o"),
    model_id: str = typer.Option("pyannote/speaker-diarization-community-1", "--model-id"),
    hf_token_env: str = typer.Option("HF_TOKEN", "--hf-token-env"),
    device: str = typer.Option("auto", "--device", help="auto, mps, cpu, or cuda. auto uses Apple MPS when available."),
    start: float | None = typer.Option(None, "--start", help="Start offset in seconds."),
    duration: float | None = typer.Option(None, "--duration", help="Clip duration in seconds."),
    num_speakers: int | None = typer.Option(None, "--num-speakers"),
    min_speakers: int | None = typer.Option(None, "--min-speakers"),
    max_speakers: int | None = typer.Option(None, "--max-speakers"),
) -> None:
    """Run pyannote speaker diarization and save speaker turns as JSON."""
    stem = safe_stem(source)
    start_label = int(start or 0)
    duration_label = int(duration or 0)
    suffix = f"_{start_label}s_{duration_label}s" if start is not None or duration is not None else ""
    audio_path = Path(".cache/audio") / f"{stem}{suffix}_pyannote.wav"
    try:
        normalize_audio(source, audio_path, start=start, duration=duration)
        hf_token = resolve_hf_token(hf_token_env)
        run = run_pyannote(
            audio_path=audio_path,
            model_id=model_id,
            hf_token=hf_token,
            device=device,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except (AudioToolError, DiarizationError) as error:
        raise typer.BadParameter(str(error)) from error

    output_json = output_dir / f"{stem}{suffix}.pyannote.json"
    write_diarization_json(output_json, audio_path=audio_path, model_id=model_id, run=run)
    console.print(f"[green]Diarization JSON:[/green] {output_json}")
    console.print(
        f"[cyan]Detected {len({turn.speaker for turn in run.turns})} speakers "
        f"across {len(run.turns)} turns in {run.elapsed_seconds:.2f}s.[/cyan]"
    )


@app.command("check-pyannote-access")
def check_pyannote_access(
    model_id: str = typer.Option("pyannote/speaker-diarization-community-1", "--model-id"),
    hf_token_env: str = typer.Option("HF_TOKEN", "--hf-token-env"),
) -> None:
    """Check whether the local Hugging Face token can access a pyannote model."""
    try:
        from huggingface_hub import HfApi
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError
    except ImportError as error:
        raise typer.BadParameter(
            "huggingface_hub is not installed. Run: .venv/bin/python -m pip install -e 'app[diarization]'"
        ) from error

    token = resolve_hf_token(hf_token_env)
    api = HfApi(token=token)
    try:
        whoami = api.whoami()
        hf_hub_download(model_id, "config.yaml", token=token)
    except GatedRepoError as error:
        raise typer.BadParameter(
            f"Token is valid, but access to {model_id} is not enabled. "
            f"Open https://huggingface.co/{model_id} and accept/request access."
        ) from error
    except RepositoryNotFoundError as error:
        raise typer.BadParameter(f"Model not found or not visible: {model_id}") from error
    except Exception as error:
        raise typer.BadParameter(f"Could not check access to {model_id}: {error}") from error

    console.print(f"[green]Token user:[/green] {whoami.get('name', 'unknown')}")
    console.print(f"[green]Access OK:[/green] {model_id}")


@app.command("render-transcript")
def render_transcript(
    gigastt_json: Path = typer.Argument(..., exists=True, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
    diarization_json: Path | None = typer.Option(None, "--diarization-json", exists=True, readable=True),
    title: str | None = typer.Option(None, "--title"),
    max_gap_seconds: float = typer.Option(1.8, "--max-gap", help="Pause that starts a new segment."),
) -> None:
    """Render a readable Markdown transcript from GigaSTT JSON and optional diarization JSON."""
    result = load_result(gigastt_json)
    if diarization_json is not None:
        result = assign_speakers(result, load_diarization_json(diarization_json))
    segments = segment_words(result.words, max_gap_seconds=max_gap_seconds)
    target = output or gigastt_json.with_suffix(".transcript.md")
    write_readable_markdown(
        target,
        title=title or gigastt_json.stem,
        result=result,
        segments=segments,
        engine_seconds=None,
    )
    console.print(f"[green]Markdown:[/green] {target}")


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", "-p"),
    inbox: Path = typer.Option(Path("Inbox"), "--inbox"),
    output_dir: Path = typer.Option(Path("outputs/pipeline"), "--output-dir", "-o"),
) -> None:
    """Start the local browser UI."""
    from voice_recognizer.web import run_web_server

    run_web_server(
        root=Path.cwd(),
        inbox=inbox,
        output_dir=output_dir,
        host=host,
        port=port,
    )


def _write_batch_index(
    path: Path,
    rows: list[tuple[Path, Path, Path, float, float, int, int, str]],
) -> None:
    total_duration = sum(row[3] for row in rows)
    total_engine = sum(row[4] for row in rows)
    lines = [
        "# Batch Transcription",
        "",
        f"- Files: {len(rows)}",
        f"- Total audio: {total_duration:.1f}s",
        f"- Total engine time: {total_engine:.2f}s",
        "",
        "| File | Duration | Engine | RTF | Words | Speakers | Status | Result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for source, _, markdown, duration, engine, words, speakers, status in rows:
        rtf = engine / duration if engine and duration else 0.0
        result_link = markdown.name if markdown.exists() else ""
        lines.append(
            f"| {source.name} | {duration:.1f}s | {engine:.2f}s | {rtf:.3f} | "
            f"{words} | {speakers} | {status} | {result_link} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pipeline_batch_index(
    path: Path,
    rows: list[tuple[Path, Path, Path, Path, float, float | None, float | None, int, int, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_duration = sum(row[4] for row in rows)
    total_asr = sum(row[5] or 0.0 for row in rows)
    total_diarization = sum(row[6] or 0.0 for row in rows)
    lines = [
        "# Batch Speaker Transcription",
        "",
        f"- Files: {len(rows)}",
        f"- Total audio: {total_duration:.1f}s",
        f"- Total ASR time: {_seconds_label(total_asr)}",
        f"- Total diarization time: {_seconds_label(total_diarization)}",
        "",
        "| File | Duration | ASR | Diarization | Words | Speakers | Status | Transcript |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for source, _, _, markdown, duration, asr_time, diarization_time, words, speakers, status in rows:
        result_link = markdown.name if markdown.exists() else ""
        lines.append(
            f"| {source.name} | {duration:.1f}s | {_seconds_label(asr_time)} | "
            f"{_seconds_label(diarization_time)} | {words} | {speakers} | {status} | {result_link} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _speaker_constraint_label(
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> str:
    if num_speakers is not None:
        return f"num_speakers={num_speakers}"
    bounds = []
    if min_speakers is not None:
        bounds.append(f"min={min_speakers}")
    if max_speakers is not None:
        bounds.append(f"max={max_speakers}")
    return ", ".join(bounds) if bounds else "auto"


def _speaker_names_label(names: dict[int, str]) -> str:
    return ", ".join(f"{speaker + 1}={name}" for speaker, name in sorted(names.items()))


def _seconds_label(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}s"


if __name__ == "__main__":
    app()
