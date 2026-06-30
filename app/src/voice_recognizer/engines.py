from __future__ import annotations

from dataclasses import dataclass


DEFAULT_ASR_ENGINE = "gigastt-gigaam-v3"


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
        value="handy-gigaam-v3",
        label="Handy GigaAM V3",
        available=False,
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
}


def normalize_asr_engine(value: str | None) -> str:
    requested = (value or DEFAULT_ASR_ENGINE).strip().lower()
    engine = ASR_ENGINE_ALIASES.get(requested, requested)
    if engine in ASR_ENGINE_LABELS:
        return engine
    available = ", ".join(sorted(ASR_ENGINE_LABELS))
    raise ValueError(
        f"Unsupported ASR engine: {value!r}. Available now: {available}. "
        "Handy model files are detected, but their runtime backend is not integrated yet."
    )
