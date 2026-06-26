from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    speaker: str
    text: str


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def write_markdown(path: Path, *, title: str, segments: list[TranscriptSegment]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    current_speaker = None
    for segment in segments:
        timestamp = f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"
        speaker = segment.speaker or "Спикер"
        if speaker != current_speaker:
            lines.append(f"## {speaker}")
            lines.append("")
            current_speaker = speaker
        lines.append(f"[{timestamp}] {segment.text.strip()}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
