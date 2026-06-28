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
_SPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?:;])")
_NO_SPACE_AFTER_PUNCT_RE = re.compile(r"([,.!?:;])(?=[^\s,.!?:;\d])")
_REPEATED_SHORT_TOKEN_RE = re.compile(
    r"\b(?P<token>по|пу|публ|пуб|пубе|публи|пуби|пуберт|пуберта|не|ну)\b"
    r"(?:\s+(?P=token)\b){1,}",
    flags=re.IGNORECASE,
)
_JUNK_TOKEN_RE = re.compile(r"\b(?:пуб|публ|публа|пубе|публи|пуби|пуберт|пуберта|пубер)\b", flags=re.IGNORECASE)
_EMAIL_REPLACEMENTS = (
    (re.compile(r"\b[еe]\s*[.\-]?\s*м[еэ]йл\b", flags=re.IGNORECASE), "email"),
    (re.compile(r"\bим[еэ]йл\b", flags=re.IGNORECASE), "email"),
    (re.compile(r"\bем[еэ]йл\b", flags=re.IGNORECASE), "email"),
)
_PHRASE_REPLACEMENTS = (
    (re.compile(r"\bс\s+генер", flags=re.IGNORECASE), "сгенер"),
    (re.compile(r"\bиз\s+за\b", flags=re.IGNORECASE), "из-за"),
    (re.compile(r"\bпо\s+моему\b", flags=re.IGNORECASE), "по-моему"),
    (re.compile(r"\bкуда\s+то\b", flags=re.IGNORECASE), "куда-то"),
    (re.compile(r"\bчто\s+то\b", flags=re.IGNORECASE), "что-то"),
    (re.compile(r"\bч[её]\s+то\b", flags=re.IGNORECASE), "что-то"),
    (re.compile(r"\bкак\s+то\b", flags=re.IGNORECASE), "как-то"),
    (re.compile(r"\bгде\s+то\b", flags=re.IGNORECASE), "где-то"),
    (re.compile(r"\bкто\s+то\b", flags=re.IGNORECASE), "кто-то"),
    (re.compile(r"\bпочему\s+то\b", flags=re.IGNORECASE), "почему-то"),
    (re.compile(r"\bзачем\s+то\b", flags=re.IGNORECASE), "зачем-то"),
    (re.compile(r"\bкакой\s+нибудь\b", flags=re.IGNORECASE), "какой-нибудь"),
    (re.compile(r"\bкакая\s+нибудь\b", flags=re.IGNORECASE), "какая-нибудь"),
    (re.compile(r"\bкакое\s+нибудь\b", flags=re.IGNORECASE), "какое-нибудь"),
    (re.compile(r"\bкакие\s+нибудь\b", flags=re.IGNORECASE), "какие-нибудь"),
    (re.compile(r"\bкакую\s+то\b", flags=re.IGNORECASE), "какую-то"),
    (re.compile(r"\bкакого\s+то\b", flags=re.IGNORECASE), "какого-то"),
    (re.compile(r"\bкаком\s+то\b", flags=re.IGNORECASE), "каком-то"),
    (re.compile(r"\bкаким\s+то\b", flags=re.IGNORECASE), "каким-то"),
    (re.compile(r"\bкакими\s+то\b", flags=re.IGNORECASE), "какими-то"),
    (re.compile(r"\bкаких\s+то\b", flags=re.IGNORECASE), "каких-то"),
    (re.compile(r"\bни\s+ч[её]\b", flags=re.IGNORECASE), "ниче"),
)
_CONTINUATION_WORDS = {
    "а",
    "в",
    "и",
    "к",
    "на",
    "но",
    "по",
    "при",
    "про",
    "с",
    "у",
    "что",
    "чтобы",
    "этот",
    "эта",
    "это",
    "эти",
    "который",
    "которая",
    "которое",
    "которые",
}


@dataclass(frozen=True)
class EditedExportResult:
    markdown_path: Path
    text_path: Path
    segment_count: int


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


def render_edited_segments(segments: list[GigasttSegment]) -> list[GigasttSegment]:
    reassigned = _reassign_speaker_islands(segments)
    merged_raw = _merge_adjacent_segments(reassigned)
    normalized: list[GigasttSegment] = []
    for segment in merged_raw:
        text = normalize_text(segment.text)
        if text:
            normalized.append(GigasttSegment(segment.start, segment.end, segment.speaker, text))
    return normalized


def write_edited_exports(
    *,
    markdown_path: Path,
    text_path: Path,
    title: str,
    segments: list[GigasttSegment],
    speaker_names: dict[int, str] | None = None,
) -> EditedExportResult:
    edited_segments = render_edited_segments(segments)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_lines = [
        f"# {title}",
        "",
        "> Edited transcript generated by deterministic local cleanup. Raw ASR artifacts are unchanged.",
        "",
    ]
    text_lines: list[str] = []
    current_speaker: int | None | object = object()
    for segment in edited_segments:
        label = speaker_label(segment.speaker, speaker_names)
        interval = f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}"
        if segment.speaker != current_speaker:
            markdown_lines.append(f"## {label}")
            markdown_lines.append("")
            current_speaker = segment.speaker
        markdown_lines.append(f"`{interval}` {segment.text}")
        markdown_lines.append("")
        text_lines.append(f"{label}: {segment.text}")
    markdown_path.write_text("\n".join(markdown_lines).rstrip() + "\n", encoding="utf-8")
    text_path.write_text("\n".join(text_lines).rstrip() + "\n", encoding="utf-8")
    return EditedExportResult(markdown_path=markdown_path, text_path=text_path, segment_count=len(edited_segments))


def normalize_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("—", " — ")
    cleaned = _SPACE_RE.sub(" ", cleaned)
    for pattern, replacement in _EMAIL_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    for pattern, replacement in _PHRASE_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = _REPEATED_SHORT_TOKEN_RE.sub(lambda match: match.group("token"), cleaned)
    cleaned = _JUNK_TOKEN_RE.sub("", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = _NO_SPACE_AFTER_PUNCT_RE.sub(r"\1 ", cleaned)
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
    cleaned = cleaned.strip(" ,")
    cleaned = _capitalize_sentences(cleaned)
    if cleaned and not re.search(r"[.!?…:]$", cleaned) and len(_WORD_RE.findall(cleaned)) >= 4:
        cleaned += "."
    return cleaned


def _span_payload(span: SuspiciousSpan) -> dict[str, Any]:
    payload = asdict(span)
    payload["start_label"] = span.start_label
    payload["end_label"] = span.end_label
    return payload


def _reassign_speaker_islands(segments: list[GigasttSegment]) -> list[GigasttSegment]:
    repaired: list[GigasttSegment] = []
    for index, segment in enumerate(segments):
        speaker = segment.speaker
        if _is_speaker_island(segments, index):
            speaker = segments[index - 1].speaker
        repaired.append(GigasttSegment(segment.start, segment.end, speaker, segment.text))
    return repaired


def _merge_adjacent_segments(segments: list[GigasttSegment]) -> list[GigasttSegment]:
    merged: list[GigasttSegment] = []
    for segment in segments:
        if not merged:
            merged.append(segment)
            continue
        previous = merged[-1]
        gap = max(0.0, segment.start - previous.end)
        previous_words = len(_WORD_RE.findall(previous.text))
        segment_words = len(_WORD_RE.findall(segment.text))
        if previous.speaker == segment.speaker and gap <= 2.5 and previous_words + segment_words <= 90:
            joined = _join_sentences(previous.text, segment.text, gap_seconds=gap)
            merged[-1] = GigasttSegment(previous.start, segment.end, previous.speaker, joined)
        else:
            merged.append(segment)
    return merged


def _join_sentences(left: str, right: str, *, gap_seconds: float) -> str:
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right:
        return left
    if re.search(r"[.!?…:]$", left):
        return f"{left} {right}"
    if gap_seconds >= 1.2 and _last_word_key(left) not in _CONTINUATION_WORDS:
        return f"{left.rstrip(',;')} . {right}"
    return f"{left.rstrip(',;')} {right}"


def _last_word_key(text: str) -> str:
    words = _WORD_RE.findall(text)
    return words[-1].lower().replace("ё", "е") if words else ""


def _capitalize_sentences(text: str) -> str:
    chars = list(text)
    capitalize_next = True
    for index, char in enumerate(chars):
        if char.isalpha():
            if capitalize_next:
                chars[index] = char.upper()
            capitalize_next = False
        elif char in ".!?…":
            capitalize_next = True
    return "".join(chars)


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
