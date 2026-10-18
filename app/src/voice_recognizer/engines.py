from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_ASR_ENGINE = "gigastt-gigaam-v3"
CTC_ENGINE = "handy-gigaam-v3-e2e-ctc"
E2E_RNNT_ENGINE = "gigastt-gigaam-v3-e2e-rnnt"


def configured_default(root: Path | None = None) -> str:
    """Local preference, never inferred from the presence of another app."""
    try:
        value = json.loads(((root or Path.cwd()) / ".cache/asr-engine.json").read_text())["engine"]
        if value in {DEFAULT_ASR_ENGINE, CTC_ENGINE, E2E_RNNT_ENGINE}:
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return DEFAULT_ASR_ENGINE


def artifact_suffix(engine: str) -> str:
    return {CTC_ENGINE: ".gigaam-e2e-ctc", E2E_RNNT_ENGINE: ".gigaam-e2e-rnnt"}.get(engine, "")


@dataclass(frozen=True)
class AsrEngineChoice:
    value: str
    label: str
    available: bool


ASR_ENGINE_CHOICES: tuple[AsrEngineChoice, ...] = (
    AsrEngineChoice(
        value=DEFAULT_ASR_ENGINE,
        label="GigaSTT / GigaAM v3 RNNT",
        available=True,
    ),
    AsrEngineChoice(
        value=CTC_ENGINE,
        label="GigaAM v3 e2e CTC",
        available=True,
    ),
    AsrEngineChoice(
        value=E2E_RNNT_ENGINE,
        label="GigaAM v3 e2e RNNT",
        available=True,
    ),
    AsrEngineChoice(
        value="handy-whisper-large-v3",
        label="Handy Whisper Large v3",
        available=False,
    ),
)

ASR_ENGINE_LABELS = {choice.value: choice.label for choice in ASR_ENGINE_CHOICES if choice.available}

ASR_ENGINE_ALIASES = {
    "gigastt": DEFAULT_ASR_ENGINE,
    "gigaam": DEFAULT_ASR_ENGINE,
    "gigaam-v3": DEFAULT_ASR_ENGINE,
    DEFAULT_ASR_ENGINE: DEFAULT_ASR_ENGINE,
    CTC_ENGINE: CTC_ENGINE,
    "handy-gigaam-v3": CTC_ENGINE,
    "e2e-rnnt": E2E_RNNT_ENGINE,
}


def normalize_asr_engine(value: str | None) -> str:
    requested = (value or "auto").strip().lower()
    if requested == "auto":
        requested = configured_default()
    engine = ASR_ENGINE_ALIASES.get(requested, requested)
    if engine in ASR_ENGINE_LABELS:
        return engine
    available = ", ".join(sorted(ASR_ENGINE_LABELS))
    raise ValueError(
        f"Unsupported ASR engine: {value!r}. Available now: {available}. "
        "Whisper runtime is not integrated."
    )
