"""Local GigaAM e2e CTC with Handy 0.9.6's transcribe-rs 0.3.8 features.

Reference: cjpais/transcribe-rs commit 49356e1359f1725adac9d491aeb892be37b15d89,
src/onnx/gigaam/mod.rs and src/features/mel.rs. No Handy history is accessed.
CTC emission times are approximate alignment, not forced word alignment.
"""
from __future__ import annotations

import json
import os
import time
import wave
from hashlib import sha256
from pathlib import Path
from typing import Callable

from voice_recognizer.gigastt import GigasttError

ENGINE = "handy-gigaam-v3-e2e-ctc"
VERSION = 2
RATE = 16000
MAX_SECONDS = 22
CONTEXT_SECONDS = 0.4


def model_paths() -> tuple[Path, Path, Path]:
    directory = Path(os.environ.get("VOICE_RECOGNIZER_CTC_MODEL_DIR") or
                     Path.home() / "Library/Application Support/com.pais.handy/models/giga-am-v3-int8")
    vad = Path(os.environ.get("VOICE_RECOGNIZER_CTC_VAD_PATH") or
               "/Applications/Handy.app/Contents/Resources/resources/models/silero_vad_v4.onnx")
    return directory / "model.int8.onnx", directory / "vocab.txt", vad


def availability() -> tuple[bool, str]:
    import importlib.util
    missing = [str(p) for p in model_paths() if not p.is_file()]
    if missing:
        return False, "Не найдены локальные файлы GigaAM CTC/Silero. Установите модель GigaAM v3 в Handy или задайте VOICE_RECOGNIZER_CTC_MODEL_DIR и VOICE_RECOGNIZER_CTC_VAD_PATH."
    if any(importlib.util.find_spec(name) is None for name in ("numpy", "onnxruntime")):
        return False, "Установите зависимости: .venv/bin/python -m pip install -e 'app[ctc]'"
    return True, "GigaAM e2e CTC и Silero найдены локально"


def file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name, suffix=".tmp", delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def mel_features(samples):
    """Handy's periodic Hann, 320 FFT, 160 hop, 64 HTK mel bins, no centering."""
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if len(samples) < 320:
        return np.empty((1, 64, 0), dtype=np.float32)
    edges = 700 * np.expm1(np.linspace(0, np.log1p(8000 / 700), 66)) * 320 / RATE
    bins = np.arange(161)[None, :]
    rising = (bins - edges[:-2, None]) / (edges[1:-1, None] - edges[:-2, None])
    falling = (edges[2:, None] - bins) / (edges[2:, None] - edges[1:-1, None])
    bank = np.maximum(0, np.minimum(rising, falling)).astype(np.float32)
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(320) / 320)).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(samples, 320)[::160]
    power = (abs(np.fft.rfft(frames * window, axis=-1)) ** 2).astype(np.float32)
    return np.log(np.clip(bank @ power.T, 1e-9, 1e9)).astype(np.float32)[None, :, :]


def decode_words(ids, vocab: dict[int, str], *, offset: float, duration: float) -> list[dict]:
    """Collapse CTC repeats, retain emission frames, assemble SentencePiece words."""
    words: list[dict] = []
    current = ""
    start = end = offset
    previous = None

    def flush():
        nonlocal current
        if any(c.isalnum() for c in current):
            words.append({"word": current.strip(), "start": round(start, 3),
                          "end": round(max(start, end), 3), "confidence": None})
        elif words and current.strip() and all(c in ".,!?;:»\"'" for c in current.strip()):
            words[-1]["word"] += current.strip()
        # Standalone dialogue dashes are layout, not spoken timestamped words.
        current = ""

    for frame, token_id in enumerate(ids):
        token_id = int(token_id)
        repeated = token_id == previous
        previous = token_id
        token = vocab.get(token_id, "")
        if repeated or token in {"", "<blk>", "<unk>", "<pad>", "<s>", "</s>"}:
            continue
        at = offset + min(duration, frame * 0.04)
        for character in token.replace("▁", " "):
            if character.isspace():
                flush()
            else:
                if not current:
                    start = at
                current += character
                end = offset + min(duration, frame * 0.04 + 0.04)
    flush()
    return words


def stitch_words(previous: list[dict], incoming: list[dict]) -> list[dict]:
    """Resolve the same acoustic word seen twice across overlapping windows.

    Only overlapping timestamps and matching text/prefixes permit replacement;
    repeated words spoken at different times are retained.
    """
    import re
    key = lambda w: re.sub(r"[^\w]", "", w["word"].casefold().replace("ё", "е"))
    result = list(previous)
    for word in incoming:
        matched = None
        for index in range(len(result) - 1, max(-1, len(result) - 5), -1):
            other = result[index]
            if other["end"] < word["start"]:
                break
            left, right = key(other), key(word)
            overlap = min(other["end"], word["end"]) - max(other["start"], word["start"])
            same = left == right or (min(len(left), len(right)) >= 2 and
                                     (left.startswith(right) or right.startswith(left)))
            if overlap > 0 and left and right and same:
                matched = index
                break
        if matched is None:
            result.append(word)
        elif len(key(word)) >= len(key(result[matched])):
            result[matched] = word
    # Chronological order at the boundary also handles overlapping vocalizations.
    return sorted(result, key=lambda w: (w["start"], w["end"]))


def choose_boundary(probabilities, frames: int, *, final: bool) -> int:
    """Prefer a quiet cut in the final 8 seconds; never exceed the model window."""
    if final:
        return frames
    import numpy as np
    lo = 12 * RATE
    hi = min(frames, 21 * RATE)
    candidates = [(float(p), i * 512) for i, p in enumerate(probabilities)
                  if lo <= i * 512 <= hi]
    quiet = [position for probability, position in candidates if probability < 0.35]
    if quiet:
        return quiet[-1]
    if candidates:
        # Even continuous speech gets bounded context. Keep every audio sample.
        smooth = np.convolve([p for p, _ in candidates], np.ones(5) / 5, mode="same")
        return candidates[int(np.argmin(smooth))][1]
    return hi


class LocalCtc:
    def __init__(self):
        import numpy as np
        import onnxruntime as ort
        ready, message = availability()
        if not ready:
            raise GigasttError(message)
        model, vocab, vad = model_paths()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.asr = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.vad = ort.InferenceSession(str(vad), options, providers=["CPUExecutionProvider"])
        if {item.name for item in self.vad.get_inputs()} != {"input", "sr", "h", "c"}:
            raise GigasttError("Нужна модель Silero v4 из Handy (входы input/sr/h/c).")
        self.vocab = {int(line.rsplit(" ", 1)[1]): line.rsplit(" ", 1)[0]
                      for line in vocab.read_text(encoding="utf-8").splitlines() if line.strip()}
        self.np = np

    def probabilities(self, samples):
        np = self.np
        h = np.zeros((2, 1, 64), dtype=np.float32)
        c = np.zeros_like(h)
        probabilities = []
        for i in range(0, len(samples), 512):
            block = samples[i:i + 512]
            if len(block) < 512:
                block = np.pad(block, (0, 512 - len(block)))
            output, h, c = self.vad.run(None, {"input": block[None], "sr": np.array(RATE, dtype=np.int64), "h": h, "c": c})
            probabilities.append(float(output[0, 0]))
        return probabilities

    def words(self, samples, *, offset: float):
        np = self.np
        features = mel_features(samples)
        if features.shape[-1] == 0:
            return []
        logits = self.asr.run(None, {"features": features,
                                   "feature_lengths": np.array([features.shape[-1]], dtype=np.int64)})[0][0]
        return decode_words(logits.argmax(-1), self.vocab, offset=offset, duration=len(samples) / RATE)


def transcribe(audio: Path, output: Path, cache_dir: Path, *, skip_existing: bool = True,
               progress: Callable[[str], None] = print) -> float:
    """Bounded RAM, local-only inference, independently cached short audio windows."""
    import numpy as np
    ready, message = availability()
    if not ready:
        raise GigasttError(message)
    started = time.perf_counter()
    metadata = {"engine": ENGINE, "version": VERSION,
                "audio_sha256": file_digest(audio),
                "asset_sha256": [file_digest(p) for p in model_paths()],
                "max_seconds": MAX_SECONDS, "context_seconds": CONTEXT_SECONDS,
                "word_timestamps": "ctc_emissions_40ms_approximate"}
    if skip_existing and output.exists():
        try:
            if json.loads(output.read_text()).get("voice_recognizer") == metadata:
                progress(f"Using ASR JSON: {output}")
                return 0.0
        except (OSError, ValueError):
            pass
    key = sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    cache = cache_dir / "ctc" / key
    runtime = None
    combined: list[dict] = []
    with wave.open(str(audio), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, RATE):
            raise GigasttError("GigaAM CTC expects prepared mono PCM16 WAV at 16000 Hz.")
        total = stream.getnframes()
        cursor = 0
        index = 0
        while cursor < total:
            index += 1
            part = cache / f"{cursor:012d}.json"
            cached = None
            if skip_existing and part.exists():
                try:
                    candidate = json.loads(part.read_text())
                    if (isinstance(candidate.get("end_frame"), int) and
                            cursor < candidate["end_frame"] <= min(total, cursor + MAX_SECONDS * RATE) and
                            isinstance(candidate.get("words"), list)):
                        cached = candidate
                except (OSError, ValueError, TypeError):
                    pass
            if cached is None:
                if runtime is None:
                    runtime = LocalCtc()
                context_start = max(0, cursor - int(CONTEXT_SECONDS * RATE))
                stream.setpos(context_start)
                samples = np.frombuffer(stream.readframes(MAX_SECONDS * RATE), dtype="<i2").astype(np.float32) / 32768
                final = context_start + len(samples) >= total
                probabilities = runtime.probabilities(samples)
                boundary = choose_boundary(probabilities, len(samples), final=final)
                end_frame = context_start + boundary
                # Right context protects words at cuts. No speech is discarded by VAD.
                recognition_end = min(len(samples), boundary + int(CONTEXT_SECONDS * RATE))
                words = runtime.words(samples[:recognition_end], offset=context_start / RATE)
                words = [w for w in words if cursor / RATE <= (w["start"] + w["end"]) / 2 < end_frame / RATE]
                cached = {"end_frame": end_frame, "words": words}
                atomic_json(part, cached)
            cursor = cached["end_frame"]
            combined = stitch_words(combined, cached["words"])
            progress(f"ASR CTC chunk {index}: {cursor / RATE:.1f}/{total / RATE:.1f}s")
    atomic_json(output, {"duration": total / RATE, "text": " ".join(w["word"] for w in combined),
                         "words": combined, "voice_recognizer": metadata})
    return time.perf_counter() - started
