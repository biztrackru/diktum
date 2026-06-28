from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from voice_recognizer.formatting import format_timestamp
from voice_recognizer.gigastt import GigasttSegment, speaker_label


REPAIR_REPORT_VERSION = 1

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_PUNCTUATION_RE = re.compile(r"[.!?,:;]")
_ALL_CAPS_RE = re.compile(r"\b[A-ZА-ЯЁ]{2,}\b")


@dataclass(frozen=True)
class SuspiciousSpan:
    index: int
    start: float
    end: float
    speaker: int | None
    speaker_label: str
    text: str
    reasons: list[str]
    severity: str

    @property
    def start_label(self) -> str:
        return format_timestamp(self.start)

    @property
    def end_label(self) -> str:
        return format_timestamp(self.end)


def detect_suspicious_spans(
    segments: list[GigasttSegment],
    *,
    asr_quality: dict[str, object] | None = None,
    speaker_quality: dict[str, object] | None = None,
    speaker_names: dict[int, str] | None = None,
    max_spans: int = 200,
) -> list[SuspiciousSpan]:
    asr_warnings = _warnings(asr_quality)
    speaker_warnings = _warnings(speaker_quality)
    suspicious: list[SuspiciousSpan] = []
    for index, segment in enumerate(segments):
        reasons = _segment_reasons(
            segments,
            index,
            asr_warnings=asr_warnings,
            speaker_warnings=speaker_warnings,
        )
        if not reasons:
            continue
        suspicious.append(
            SuspiciousSpan(
                index=index,
                start=round(segment.start, 3),
                end=round(segment.end, 3),
                speaker=segment.speaker,
                speaker_label=speaker_label(segment.speaker, speaker_names),
                text=segment.text,
                reasons=reasons,
                severity=_severity(reasons),
            )
        )
    return suspicious[:max_spans]


def build_repair_report(
    *,
    manifest_path: Path,
    source_name: str,
    asr_engine: str,
    segments: list[GigasttSegment],
    asr_quality: dict[str, object] | None,
    speaker_quality: dict[str, object] | None,
    speaker_names: dict[int, str] | None = None,
) -> dict[str, object]:
    spans = detect_suspicious_spans(
        segments,
        asr_quality=asr_quality,
        speaker_quality=speaker_quality,
        speaker_names=speaker_names,
    )
    return {
        "repair_report_version": REPAIR_REPORT_VERSION,
        "created_at": time.time(),
        "mode": "diagnostic-only",
        "source_name": source_name,
        "manifest": str(manifest_path),
        "asr_engine": asr_engine,
        "summary": {
            "segment_count": len(segments),
            "suspicious_span_count": len(spans),
            "high_severity_count": sum(1 for span in spans if span.severity == "high"),
            "medium_severity_count": sum(1 for span in spans if span.severity == "medium"),
            "low_severity_count": sum(1 for span in spans if span.severity == "low"),
        },
        "asr_quality": asr_quality,
        "speaker_quality": speaker_quality,
        "spans": [_span_payload(span) for span in spans],
        "notes": [
            "Raw ASR and transcript artifacts are not modified by this report.",
            "Use these spans as candidates for local LLM repair or targeted re-ASR.",
        ],
    }


def write_repair_report(path: Path, report: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _span_payload(span: SuspiciousSpan) -> dict[str, Any]:
    payload = asdict(span)
    payload["start_label"] = span.start_label
    payload["end_label"] = span.end_label
    return payload


def _segment_reasons(
    segments: list[GigasttSegment],
    index: int,
    *,
    asr_warnings: set[str],
    speaker_warnings: set[str],
) -> list[str]:
    segment = segments[index]
    words = _WORD_RE.findall(segment.text)
    word_count = len(words)
    reasons: list[str] = []
    text = segment.text.strip()
    duration = max(0.0, segment.end - segment.start)

    if not text:
        reasons.append("empty_text")
    if word_count >= 10 and not _PUNCTUATION_RE.search(text) and "low_punctuation" in asr_warnings:
        reasons.append("missing_punctuation")
    first_alpha = next((char for char in text if char.isalpha()), "")
    if word_count >= 4 and first_alpha and first_alpha.islower() and (
        "low_sentence_casing" in asr_warnings or "low_casing" in asr_warnings
    ):
        reasons.append("missing_sentence_casing")
    if _ALL_CAPS_RE.search(text):
        reasons.append("all_caps_token")
    if word_count >= 55:
        reasons.append("long_segment")
    if _is_speaker_island(segments, index):
        reasons.append("speaker_island")
    elif (duration <= 1.2 or word_count <= 2) and (
        "many_short_turns" in speaker_warnings or "short_speaker_islands" in speaker_warnings
    ):
        reasons.append("short_turn")

    return reasons


def _is_speaker_island(segments: list[GigasttSegment], index: int) -> bool:
    if index <= 0 or index >= len(segments) - 1:
        return False
    previous = segments[index - 1]
    current = segments[index]
    following = segments[index + 1]
    if current.speaker is None or previous.speaker is None or following.speaker is None:
        return False
    if previous.speaker != following.speaker or current.speaker == previous.speaker:
        return False
    words = _WORD_RE.findall(current.text)
    duration = max(0.0, current.end - current.start)
    return duration <= 1.2 or len(words) <= 2


def _warnings(value: dict[str, object] | None) -> set[str]:
    if not value:
        return set()
    raw = value.get("warnings")
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw}


def _severity(reasons: list[str]) -> str:
    if {"speaker_island", "all_caps_token", "empty_text"} & set(reasons):
        return "high"
    if {"missing_punctuation", "missing_sentence_casing", "long_segment"} & set(reasons):
        return "medium"
    return "low"
