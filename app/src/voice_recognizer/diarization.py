from __future__ import annotations

import json
import os
import time
import warnings
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from voice_recognizer.gigastt import GigasttResult, GigasttWord


class DiarizationError(RuntimeError):
    pass


DIARIZATION_JSON_VERSION = 1


@dataclass(frozen=True)
class DiarizationTurn:
    start: float
    end: float
    speaker: int
    label: str


@dataclass(frozen=True)
class DiarizationRun:
    turns: list[DiarizationTurn]
    elapsed_seconds: float


def resolve_hf_token(env_name: str = "HF_TOKEN") -> str:
    token = os.environ.get(env_name) or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise DiarizationError(
            f"Set {env_name} or HUGGING_FACE_HUB_TOKEN before running pyannote diarization"
        )
    return token


def run_pyannote(
    *,
    audio_path: Path,
    model_id: str,
    hf_token: str,
    device: str = "auto",
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> DiarizationRun:
    matplotlib_cache = Path(os.environ.get("MPLCONFIGDIR") or ".cache/matplotlib").resolve()
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.core.io")
    _emit_progress(progress, f"Diarization / pyannote: preparing local cache {matplotlib_cache}")
    _emit_progress(progress, "Diarization / pyannote: importing Python packages")
    try:
        import numpy as np
        import torch
        from pyannote.audio import Pipeline
    except ImportError as error:
        raise DiarizationError(
            "pyannote.audio is not installed. Run: .venv/bin/python -m pip install -e 'app[diarization]'"
        ) from error

    _emit_progress(
        progress,
        f"Diarization / pyannote: loading model {model_id}. First run may download/cache model files.",
    )
    try:
        pipeline = Pipeline.from_pretrained(model_id, token=hf_token)
    except Exception as error:
        message = str(error)
        if "403" in message or "gated" in message.lower() or "authorized" in message.lower():
            raise DiarizationError(
                f"Access to {model_id} is not enabled for this Hugging Face token. "
                f"Open https://huggingface.co/{model_id}, accept/request access, "
                "then rerun the command with the same .env token."
            ) from error
        raise DiarizationError(f"Could not load pyannote model {model_id}: {error}") from error
    if pipeline is None:
        raise DiarizationError(
            f"Could not load {model_id}. Check the Hugging Face token and model access."
        )

    target_device = _choose_device(device, torch)
    if target_device is not None:
        _emit_progress(progress, f"Diarization / pyannote: moving model to device {target_device}")
        pipeline.to(target_device)
    else:
        _emit_progress(progress, "Diarization / pyannote: using default device")

    _emit_progress(progress, f"Diarization / pyannote: loading prepared audio {audio_path}")
    waveform, sample_rate = _load_wav_as_tensor(audio_path, np, torch)
    if target_device is not None:
        waveform = waveform.to(target_device)

    kwargs: dict[str, int] = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers

    started = time.perf_counter()
    _emit_progress(progress, "Diarization / pyannote: running speaker separation")
    try:
        diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **kwargs)
    except Exception as error:
        raise DiarizationError(f"pyannote diarization failed: {error}") from error
    elapsed = time.perf_counter() - started
    _emit_progress(progress, f"Diarization / pyannote: speaker separation finished in {elapsed:.1f}s")

    label_to_id: dict[str, int] = {}
    turns: list[DiarizationTurn] = []
    for turn, _, label in _iter_diarization_tracks(diarization):
        if label not in label_to_id:
            label_to_id[label] = len(label_to_id)
        turns.append(
            DiarizationTurn(
                start=float(turn.start),
                end=float(turn.end),
                speaker=label_to_id[label],
                label=str(label),
            )
        )
    return DiarizationRun(turns=turns, elapsed_seconds=elapsed)


def _emit_progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _iter_diarization_tracks(diarization: Any) -> Any:
    annotation = getattr(
        diarization,
        "exclusive_speaker_diarization",
        getattr(diarization, "speaker_diarization", diarization),
    )
    return annotation.itertracks(yield_label=True)


def _load_wav_as_tensor(audio_path: Path, np: Any, torch: Any) -> tuple[Any, int]:
    """Load normalized PCM WAV without torchaudio/torchcodec ffmpeg dependencies."""
    try:
        with wave.open(str(audio_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except wave.Error as error:
        raise DiarizationError(f"Could not read WAV file {audio_path}: {error}") from error

    if sample_width != 2:
        raise DiarizationError(
            f"Unsupported WAV sample width in {audio_path}: {sample_width} bytes. "
            "Run the audio through prepare/normalize_audio first."
        )

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    waveform = torch.from_numpy(samples.copy()).unsqueeze(0)
    return waveform, sample_rate


def write_diarization_json(
    path: Path,
    *,
    audio_path: Path,
    model_id: str,
    run: DiarizationRun,
    device: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "audio": str(audio_path),
        "model": model_id,
        "elapsed_seconds": run.elapsed_seconds,
        "voice_recognizer": diarization_json_metadata(
            model_id=model_id,
            device=device,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        ),
        "turns": [
            {
                "start": turn.start,
                "end": turn.end,
                "speaker": turn.speaker,
                "label": turn.label,
            }
            for turn in run.turns
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def diarization_json_metadata(
    *,
    model_id: str,
    device: str | None,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> dict[str, Any]:
    return {
        "diarization_json_version": DIARIZATION_JSON_VERSION,
        "pyannote": {
            "model_id": model_id,
            "device": device,
            "speaker_constraints": {
                "num_speakers": num_speakers,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
            },
        },
    }


def diarization_json_matches_options(
    path: Path,
    *,
    model_id: str,
    device: str | None,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> bool:
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("voice_recognizer") == diarization_json_metadata(
        model_id=model_id,
        device=device,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )


def load_diarization_json(path: Path) -> list[DiarizationTurn]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return [
        DiarizationTurn(
            start=float(item["start"]),
            end=float(item["end"]),
            speaker=int(item["speaker"]),
            label=str(item.get("label", f"SPEAKER_{item['speaker']}")),
        )
        for item in payload.get("turns", [])
    ]


def assign_speakers(
    result: GigasttResult,
    turns: list[DiarizationTurn],
    *,
    smooth: bool = True,
    island_max_words: int = 2,
    island_max_seconds: float = 1.2,
    bridge_gap_seconds: float = 0.8,
) -> GigasttResult:
    if not turns:
        return result

    assigned_words: list[GigasttWord] = []
    for word in result.words:
        speaker = _speaker_for_word(word.start, word.end, turns)
        assigned_words.append(
            GigasttWord(
                start=word.start,
                end=word.end,
                word=word.word,
                confidence=word.confidence,
                speaker=speaker,
            )
        )
    if smooth:
        assigned_words = smooth_speaker_islands(
            assigned_words,
            island_max_words=island_max_words,
            island_max_seconds=island_max_seconds,
            bridge_gap_seconds=bridge_gap_seconds,
        )
    return GigasttResult(duration=result.duration, text=result.text, words=assigned_words)


def smooth_speaker_islands(
    words: list[GigasttWord],
    *,
    island_max_words: int = 2,
    island_max_seconds: float = 1.2,
    bridge_gap_seconds: float = 0.8,
) -> list[GigasttWord]:
    runs = _speaker_runs(words)
    if len(runs) < 3:
        return words

    replacement: dict[int, int | None] = {}
    for index in range(1, len(runs) - 1):
        previous_run = runs[index - 1]
        current_run = runs[index]
        next_run = runs[index + 1]
        current_speaker = current_run["speaker"]
        surrounding_speaker = previous_run["speaker"]
        if (
            current_speaker is None
            or surrounding_speaker is None
            or current_speaker == surrounding_speaker
            or next_run["speaker"] != surrounding_speaker
        ):
            continue

        run_words = words[current_run["start_index"] : current_run["end_index"]]
        previous_words = words[previous_run["start_index"] : previous_run["end_index"]]
        next_words = words[next_run["start_index"] : next_run["end_index"]]
        run_duration = max(0.0, run_words[-1].end - run_words[0].start)
        left_gap = max(0.0, run_words[0].start - previous_words[-1].end)
        right_gap = max(0.0, next_words[0].start - run_words[-1].end)

        is_short_island = len(run_words) <= island_max_words or run_duration <= island_max_seconds
        is_inside_phrase = left_gap <= bridge_gap_seconds and right_gap <= bridge_gap_seconds
        if is_short_island and is_inside_phrase:
            for word_index in range(current_run["start_index"], current_run["end_index"]):
                replacement[word_index] = surrounding_speaker

    if not replacement:
        return words

    smoothed: list[GigasttWord] = []
    for index, word in enumerate(words):
        speaker = replacement.get(index, word.speaker)
        smoothed.append(
            GigasttWord(
                start=word.start,
                end=word.end,
                word=word.word,
                confidence=word.confidence,
                speaker=speaker,
            )
        )
    return smoothed


def _speaker_runs(words: list[GigasttWord]) -> list[dict[str, int | None]]:
    if not words:
        return []
    runs: list[dict[str, int | None]] = []
    start_index = 0
    current_speaker = words[0].speaker
    for index, word in enumerate(words[1:], start=1):
        if word.speaker != current_speaker:
            runs.append(
                {
                    "start_index": start_index,
                    "end_index": index,
                    "speaker": current_speaker,
                }
            )
            start_index = index
            current_speaker = word.speaker
    runs.append(
        {
            "start_index": start_index,
            "end_index": len(words),
            "speaker": current_speaker,
        }
    )
    return runs


def _speaker_for_word(
    start: float,
    end: float,
    turns: list[DiarizationTurn],
    *,
    nearest_tolerance_seconds: float = 0.75,
) -> int | None:
    best_speaker: int | None = None
    best_overlap = 0.0
    for turn in turns:
        overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = turn.speaker
    if best_speaker is not None:
        return best_speaker

    midpoint = (start + end) / 2.0
    speaker = _speaker_at(midpoint, turns)
    if speaker is not None:
        return speaker

    nearest_speaker: int | None = None
    nearest_distance = float("inf")
    for turn in turns:
        if midpoint < turn.start:
            distance = turn.start - midpoint
        elif midpoint > turn.end:
            distance = midpoint - turn.end
        else:
            distance = 0.0
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_speaker = turn.speaker
    if nearest_distance <= nearest_tolerance_seconds:
        return nearest_speaker
    return None


def _speaker_at(timestamp: float, turns: list[DiarizationTurn]) -> int | None:
    for turn in turns:
        if turn.start <= timestamp <= turn.end:
            return turn.speaker
    return None


def _choose_device(device: str, torch: Any) -> Any:
    if device == "cpu":
        return torch.device("cpu")
    if device == "mps":
        return torch.device("mps")
    if device == "cuda":
        return torch.device("cuda")
    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    raise DiarizationError(f"Unsupported device: {device}")
