from __future__ import annotations

import json
import math
import re
import subprocess
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from voice_recognizer.formatting import format_timestamp


class GigasttError(RuntimeError):
    pass


ASR_JSON_VERSION = 2


@dataclass(frozen=True)
class GigasttWord:
    start: float
    end: float
    word: str
    confidence: float | None
    speaker: int | None


@dataclass(frozen=True)
class GigasttResult:
    duration: float
    text: str
    words: list[GigasttWord]


@dataclass(frozen=True)
class GigasttSegment:
    start: float
    end: float
    speaker: int | None
    text: str

    @property
    def speaker_label(self) -> str:
        return speaker_label(self.speaker)


def speaker_label(speaker: int | None, speaker_names: dict[int, str] | None = None) -> str:
    if speaker is None:
        return "Спикер ?"
    if speaker_names and speaker in speaker_names and speaker_names[speaker].strip():
        return speaker_names[speaker].strip()
    return f"Спикер {speaker + 1}"


def ensure_prequantized_compat(model_dir: Path) -> None:
    """Work around gigastt 2.5.0 transcribe preflight expecting the FP32 encoder."""
    int8_encoder = model_dir / "v3_rnnt_encoder_int8.onnx"
    fp32_encoder = model_dir / "v3_rnnt_encoder.onnx"
    if int8_encoder.exists() and not fp32_encoder.exists():
        try:
            fp32_encoder.symlink_to(int8_encoder.name)
        except OSError:
            fp32_encoder.write_bytes(int8_encoder.read_bytes())


def run_gigastt(
    *,
    gigastt_bin: Path,
    source: Path,
    output_json: Path,
    model_dir: Path,
    punct_model_dir: Path,
    hotwords_file: Path | None = None,
    hotwords_default: bool = False,
    chunk_seconds: float | None = None,
    chunk_start: float | None = None,
    chunk_duration: float | None = None,
    log_level: str = "error",
) -> float:
    if not gigastt_bin.exists():
        raise GigasttError(f"gigastt binary not found: {gigastt_bin}")
    if not model_dir.exists():
        raise GigasttError(f"gigastt model directory not found: {model_dir}")

    ensure_prequantized_compat(model_dir)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(gigastt_bin),
        "--log-level",
        log_level,
        "transcribe",
        "--model-dir",
        str(model_dir),
        "--punct-model-dir",
        str(punct_model_dir),
        "--punctuation",
        "on",
        "--itn",
        "auto",
    ]
    if hotwords_file is not None:
        if not hotwords_file.exists():
            raise GigasttError(f"hotwords file not found: {hotwords_file}")
        command.extend(["--hotwords-file", str(hotwords_file)])
    if hotwords_default:
        command.append("--hotwords-default")
    command.extend([
        "--format",
        "json",
        "--output",
        str(output_json),
        str(source),
    ])
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        suffix = f": {details}" if details else ""
        raise GigasttError(f"gigastt failed with exit code {result.returncode}{suffix}")
    annotate_gigastt_json(
        output_json,
        asr_json_metadata(
            hotwords_file=hotwords_file,
            hotwords_default=hotwords_default,
            chunk_seconds=chunk_seconds,
            chunk_start=chunk_start,
            chunk_duration=chunk_duration,
        ),
    )
    return time.perf_counter() - started


def asr_json_metadata(
    *,
    hotwords_file: Path | None,
    hotwords_default: bool,
    chunk_seconds: float | None = None,
    chunk_start: float | None = None,
    chunk_duration: float | None = None,
) -> dict[str, Any]:
    return {
        "asr_json_version": ASR_JSON_VERSION,
        "gigastt": {
            "punctuation": "on",
            "itn": "auto",
            "hotwords_file": str(hotwords_file) if hotwords_file is not None else None,
            "hotwords_sha256": _file_sha256(hotwords_file) if hotwords_file is not None else None,
            "hotwords_default": hotwords_default,
        },
        "chunking": {
            "chunk_seconds": _metadata_float(chunk_seconds),
            "chunk_start": _metadata_float(chunk_start),
            "chunk_duration": _metadata_float(chunk_duration),
        },
    }


def annotate_gigastt_json(path: Path, metadata: dict[str, Any]) -> None:
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GigasttError(f"could not annotate gigastt JSON {path}: {error}") from error
    payload["voice_recognizer"] = metadata
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def gigastt_json_matches_options(
    path: Path,
    *,
    hotwords_file: Path | None,
    hotwords_default: bool,
    chunk_seconds: float | None = None,
    chunk_start: float | None = None,
    chunk_duration: float | None = None,
) -> bool:
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("voice_recognizer") == asr_json_metadata(
        hotwords_file=hotwords_file,
        hotwords_default=hotwords_default,
        chunk_seconds=chunk_seconds,
        chunk_start=chunk_start,
        chunk_duration=chunk_duration,
    )


def _file_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _metadata_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def load_result(path: Path) -> GigasttResult:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    text = str(payload.get("text", "")).strip()
    words = [
        GigasttWord(
            start=float(item.get("start", 0)),
            end=float(item.get("end", 0)),
            word=str(item.get("word", "")).strip(),
            confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
            speaker=int(item["speaker"]) if item.get("speaker") is not None else None,
        )
        for item in payload.get("words", [])
        if str(item.get("word", "")).strip()
    ]
    return GigasttResult(
        duration=float(payload.get("duration", 0)),
        text=text,
        words=_apply_display_text_to_words(text, words),
    )


_WORD_KEY_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")


def _apply_display_text_to_words(text: str, words: list[GigasttWord]) -> list[GigasttWord]:
    """Transfer punctuation/casing from GigaSTT text onto timestamped word tokens."""
    if not text or not words:
        return words
    display_tokens = [token for token in text.split() if _word_key(token)]
    if not display_tokens:
        return words

    mapped: list[GigasttWord] = []
    token_index = 0
    matched = 0
    for word in words:
        display = word.word
        raw_key = _word_key(word.word)
        if raw_key:
            match_index = _next_matching_token(display_tokens, token_index, raw_key)
            if match_index is not None:
                display = display_tokens[match_index]
                token_index = match_index + 1
                matched += 1
        mapped.append(
            GigasttWord(
                start=word.start,
                end=word.end,
                word=display,
                confidence=word.confidence,
                speaker=word.speaker,
            )
        )

    if matched / max(1, len(words)) < 0.65:
        return words
    return mapped


def _next_matching_token(tokens: list[str], start_index: int, raw_key: str, lookahead: int = 6) -> int | None:
    end_index = min(len(tokens), start_index + lookahead)
    for index in range(start_index, end_index):
        if _word_key(tokens[index]) == raw_key:
            return index
    return None


def _word_key(value: str) -> str:
    return "".join(_WORD_KEY_RE.findall(value)).lower().replace("ё", "е")


def segment_words(
    words: list[GigasttWord],
    *,
    max_gap_seconds: float = 1.8,
    max_segment_seconds: float = 35.0,
    max_words: int = 55,
) -> list[GigasttSegment]:
    valid_words = [
        word
        for word in words
        if math.isfinite(word.start)
        and math.isfinite(word.end)
        and word.end >= word.start
        and word.end - word.start <= max_segment_seconds
    ]
    if not valid_words:
        return []

    segments: list[GigasttSegment] = []
    current: list[GigasttWord] = [valid_words[0]]
    current_speaker = valid_words[0].speaker

    for word in valid_words[1:]:
        previous = current[-1]
        gap = max(0.0, word.start - previous.end)
        segment_duration = word.end - current[0].start
        should_break = (
            word.speaker != current_speaker
            or gap >= max_gap_seconds
            or segment_duration >= max_segment_seconds
            or len(current) >= max_words
        )
        if should_break:
            segments.append(_segment_from_words(current, current_speaker))
            current = [word]
            current_speaker = word.speaker
        else:
            current.append(word)

    if current:
        segments.append(_segment_from_words(current, current_speaker))
    return segments


def write_readable_markdown(
    path: Path,
    *,
    title: str,
    result: GigasttResult,
    segments: list[GigasttSegment],
    engine_seconds: float | None,
    speaker_names: dict[int, str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    speaker_count = len({word.speaker for word in result.words if word.speaker is not None})
    realtime_factor = engine_seconds / result.duration if engine_seconds and result.duration else None
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Duration: {format_timestamp(result.duration)}",
        f"- Words: {len(result.words)}",
        f"- Speakers detected: {speaker_count}",
    ]
    if engine_seconds is not None and realtime_factor is not None:
        lines.insert(5, f"- Engine time: {engine_seconds:.2f}s")
        lines.insert(6, f"- RTF: {realtime_factor:.3f}")
    lines += [
        "",
        "## Full Transcript",
        "",
        result.text or "_No text recognized._",
        "",
        "## Segments",
        "",
    ]
    for segment in segments:
        interval = f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"
        lines.append(f"**{speaker_label(segment.speaker, speaker_names)}** `{interval}`")
        lines.append("")
        lines.append(segment.text)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_clean_markdown(
    path: Path,
    *,
    title: str,
    segments: list[GigasttSegment],
    speaker_names: dict[int, str] | None = None,
    include_timestamps: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    current_speaker: int | None | object = object()
    for segment in segments:
        if segment.speaker != current_speaker:
            lines.append(f"## {speaker_label(segment.speaker, speaker_names)}")
            lines.append("")
            current_speaker = segment.speaker
        if include_timestamps:
            interval = f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"
            lines.append(f"`{interval}` {segment.text}")
        else:
            lines.append(segment.text)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_plain_text(
    path: Path,
    *,
    segments: list[GigasttSegment],
    speaker_names: dict[int, str] | None = None,
    include_timestamps: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for segment in segments:
        label = speaker_label(segment.speaker, speaker_names)
        if include_timestamps:
            interval = f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"
            lines.append(f"{label} [{interval}]: {segment.text}")
        else:
            lines.append(f"{label}: {segment.text}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _segment_from_words(words: list[GigasttWord], speaker: int | None) -> GigasttSegment:
    return GigasttSegment(
        start=words[0].start,
        end=words[-1].end,
        speaker=speaker,
        text=" ".join(word.word for word in words),
    )
