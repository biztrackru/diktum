from __future__ import annotations

import json
import re
import time
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from voice_recognizer.formatting import format_timestamp
from voice_recognizer.gigastt import GigasttSegment, speaker_label


REPAIR_REPORT_VERSION = 1
QUALITY_BENCHMARK_VERSION = 1

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_PUNCTUATION_RE = re.compile(r"[.!?,:;]")
_ALL_CAPS_RE = re.compile(r"\b[A-ZА-ЯЁ]{2,}\b")
_SPACE_RE = re.compile(r"\s+")
_LOOSE_SOURCE_RE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё]+")
_TIMESTAMP_RE = re.compile(r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)(?!\d)")
_TIMESTAMP_INTERVAL_RE = re.compile(
    r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*(?:-->|[-–—])\s*"
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)(?!\d)"
)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")
_SPEAKER_PREFIX_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:(?:спикер|speaker)\s+\d+\s*[:：-]?|[A-ZА-ЯЁ][0-9A-Za-zА-Яа-яЁё ._-]{0,40}\s*[:：])\s*",
    flags=re.IGNORECASE,
)
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


@dataclass(frozen=True)
class QualityReference:
    id: str
    source: str | None
    start: float | None
    end: float | None
    reference: str
    terms: list[str]
    notes: str | None
    path: str


@dataclass(frozen=True)
class QualityCandidate:
    name: str
    path: str
    segments: list[GigasttSegment]
    timed: bool


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


def load_quality_references(target: Path) -> list[QualityReference]:
    paths = _quality_reference_paths(target)
    references: list[QualityReference] = []
    for path in paths:
        if path.suffix.lower() == ".jsonl":
            references.extend(_load_quality_references_jsonl(path))
        else:
            references.extend(_load_quality_references_json(path))
    return references


def filter_quality_references_for_source(
    references: list[QualityReference],
    source_name: str,
) -> list[QualityReference]:
    return [
        reference
        for reference in references
        if reference.source is None or _source_matches(source_name, reference.source)
    ]


def load_quality_candidates(specs: list[str]) -> list[QualityCandidate]:
    candidates: list[QualityCandidate] = []
    used_names: set[str] = set()
    for spec in specs:
        name, path = _parse_candidate_spec(spec)
        if not path.exists():
            raise ValueError(f"candidate transcript file not found: {path}")
        text = _read_candidate_text(path)
        segments, timed = _candidate_segments_from_text(text)
        candidate_name = _unique_candidate_name(name or path.stem, used_names)
        used_names.add(candidate_name)
        candidates.append(
            QualityCandidate(
                name=candidate_name,
                path=str(path),
                segments=segments,
                timed=timed,
            )
        )
    return candidates


def build_quality_benchmark_report(
    *,
    manifest_path: Path,
    source_name: str,
    references: list[QualityReference],
    raw_segments: list[GigasttSegment],
    edited_segments: list[GigasttSegment],
    candidates: list[QualityCandidate] | None = None,
    include_excerpts: bool = True,
) -> dict[str, object]:
    candidates = candidates or []
    matched_references = filter_quality_references_for_source(references, source_name)
    entries: list[dict[str, object]] = []
    for reference in matched_references:
        raw_text = extract_segments_text(raw_segments, start=reference.start, end=reference.end)
        edited_text = extract_segments_text(edited_segments, start=reference.start, end=reference.end)
        raw_score = score_text_against_reference(raw_text, reference.reference, terms=reference.terms)
        edited_score = score_text_against_reference(edited_text, reference.reference, terms=reference.terms)
        candidate_payloads: dict[str, object] = {}
        candidate_texts: dict[str, str] = {}
        score_map = {"raw": raw_score, "edited": edited_score}
        for candidate in candidates:
            candidate_text = extract_segments_text(candidate.segments, start=reference.start, end=reference.end)
            candidate_score = score_text_against_reference(candidate_text, reference.reference, terms=reference.terms)
            candidate_payloads[candidate.name] = {
                "path": candidate.path,
                "timed": candidate.timed,
                "score": candidate_score,
            }
            candidate_texts[candidate.name] = candidate_text
            score_map[f"candidate:{candidate.name}"] = candidate_score
        entry: dict[str, object] = {
            "id": reference.id,
            "source": reference.source,
            "start": reference.start,
            "end": reference.end,
            "start_label": format_timestamp(reference.start) if reference.start is not None else None,
            "end_label": format_timestamp(reference.end) if reference.end is not None else None,
            "terms": reference.terms,
            "notes": reference.notes,
            "reference_path": reference.path,
            "raw": raw_score,
            "edited": edited_score,
            "candidates": candidate_payloads,
            "winner": _benchmark_winner_from_scores(score_map),
        }
        if include_excerpts:
            entry["texts"] = {
                "reference": reference.reference,
                "raw": raw_text,
                "edited": edited_text,
                "candidates": candidate_texts,
            }
        entries.append(entry)
    return {
        "quality_benchmark_version": QUALITY_BENCHMARK_VERSION,
        "created_at": time.time(),
        "mode": "local-reference",
        "manifest": str(manifest_path),
        "source_name": source_name,
        "summary": summarize_quality_benchmark_entries(entries),
        "references_loaded": len(references),
        "references_matched": len(matched_references),
        "candidates": [
            {
                "name": candidate.name,
                "path": candidate.path,
                "timed": candidate.timed,
            }
            for candidate in candidates
        ],
        "entries": entries,
        "notes": [
            "This report may contain private transcript snippets when include_excerpts is enabled.",
            "Keep reports under ignored .local-quality/ unless you intentionally sanitize them.",
        ],
    }


def summarize_quality_benchmark_entries(entries: list[dict[str, object]]) -> dict[str, object]:
    raw_scores = [_score_dict(entry.get("raw")) for entry in entries]
    edited_scores = [_score_dict(entry.get("edited")) for entry in entries]
    winners = [str(entry.get("winner") or "tie") for entry in entries]
    candidate_scores = _candidate_scores_by_name(entries)
    return {
        "reference_count": len(entries),
        "raw_avg_word_similarity": _avg_score(raw_scores, "word_similarity"),
        "edited_avg_word_similarity": _avg_score(edited_scores, "word_similarity"),
        "raw_avg_char_similarity": _avg_score(raw_scores, "char_similarity"),
        "edited_avg_char_similarity": _avg_score(edited_scores, "char_similarity"),
        "raw_avg_token_f1": _avg_score(raw_scores, "token_f1"),
        "edited_avg_token_f1": _avg_score(edited_scores, "token_f1"),
        "raw_avg_punctuation_per_100_words": _avg_score(raw_scores, "punctuation_per_100_words"),
        "edited_avg_punctuation_per_100_words": _avg_score(edited_scores, "punctuation_per_100_words"),
        "raw_missing_window_count": sum(1 for score in raw_scores if not score.get("candidate_word_count")),
        "edited_missing_window_count": sum(1 for score in edited_scores if not score.get("candidate_word_count")),
        "edited_better_count": winners.count("edited"),
        "raw_better_count": winners.count("raw"),
        "candidate_better_count": sum(1 for winner in winners if winner.startswith("candidate:")),
        "candidate_summaries": {
            name: _candidate_summary(scores, winners=winners, winner_name=f"candidate:{name}")
            for name, scores in sorted(candidate_scores.items())
        },
        "tie_count": winners.count("tie"),
    }


def score_text_against_reference(
    candidate: str,
    reference: str,
    *,
    terms: list[str] | None = None,
) -> dict[str, object]:
    reference_tokens = _normalized_words(reference)
    candidate_tokens = _normalized_words(candidate)
    word_distance = _levenshtein(reference_tokens, candidate_tokens)
    word_error_rate = word_distance / max(1, len(reference_tokens))

    reference_chars = list(_normalized_text_for_distance(reference))
    candidate_chars = list(_normalized_text_for_distance(candidate))
    char_distance = _levenshtein(reference_chars, candidate_chars)
    char_error_rate = char_distance / max(1, len(reference_chars))

    token_overlap = _token_overlap(candidate_tokens, reference_tokens)
    term_list = terms or []
    found_terms = _found_terms(candidate, term_list)
    readability = _readability_metrics(candidate)
    return {
        "reference_word_count": len(reference_tokens),
        "candidate_word_count": len(candidate_tokens),
        "word_error_rate": round(word_error_rate, 3),
        "word_similarity": round(max(0.0, 1.0 - word_error_rate), 3),
        "char_error_rate": round(char_error_rate, 3),
        "char_similarity": round(max(0.0, 1.0 - char_error_rate), 3),
        "length_ratio": round(len(candidate_tokens) / max(1, len(reference_tokens)), 3),
        **token_overlap,
        "term_coverage": round(len(found_terms) / max(1, len(term_list)), 3) if term_list else None,
        "found_terms": found_terms,
        "missing_terms": [term for term in term_list if term not in found_terms],
        **readability,
    }


def extract_segments_text(
    segments: list[GigasttSegment],
    *,
    start: float | None,
    end: float | None,
) -> str:
    if start is None and end is None:
        selected = segments
    else:
        selected = [
            segment
            for segment in segments
            if _segment_overlaps(segment, start=start, end=end)
        ]
    return _SPACE_RE.sub(" ", " ".join(segment.text for segment in selected)).strip()


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


def _parse_candidate_spec(spec: str) -> tuple[str | None, Path]:
    value = spec.strip()
    if not value:
        raise ValueError("candidate spec is empty")
    if "=" in value:
        name, raw_path = value.split("=", 1)
        name = name.strip()
        path = Path(raw_path.strip())
        return name or None, path
    path = Path(value)
    return None, path


def _read_candidate_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx_text(path)
    if suffix in {".srt", ".vtt"}:
        return _read_subtitle_text(path)
    return path.read_text(encoding="utf-8")


def _read_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"could not read DOCX candidate {path}: {error}") from error
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as error:
        raise ValueError(f"could not parse DOCX candidate {path}: {error}") from error

    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append(" ")
            elif tag in {"br", "cr"}:
                parts.append("\n")
        text = _SPACE_RE.sub(" ", "".join(parts)).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _read_subtitle_text(path: Path) -> str:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    flattened: list[str] = []
    block: list[str] = []

    def flush_block() -> None:
        if not block:
            return
        timing_index = next((index for index, line in enumerate(block) if "-->" in line), None)
        if timing_index is None:
            return
        text_lines = [
            line
            for line in block[timing_index + 1 :]
            if line and not line.isdigit()
        ]
        text = _strip_candidate_text("\n".join(text_lines))
        if text:
            flattened.append(f"{block[timing_index]} {text}")

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_block()
            block = []
            continue
        if line.upper() == "WEBVTT" or line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        block.append(line)
    flush_block()
    return "\n".join(flattened)


def _unique_candidate_name(base: str, used_names: set[str]) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_.-]+", "-", base.strip()).strip("-._")
    name = cleaned or "candidate"
    if name not in used_names:
        return name
    suffix = 2
    while f"{name}-{suffix}" in used_names:
        suffix += 1
    return f"{name}-{suffix}"


def _candidate_segments_from_text(text: str) -> tuple[list[GigasttSegment], bool]:
    timestamped_lines: list[tuple[float, float | None, str]] = []
    fallback_lines: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_candidate_line(raw_line)
        if not line:
            continue
        parsed = _parse_timestamped_candidate_line(line)
        if parsed is None:
            fallback_lines.append(line)
            continue
        timestamped_lines.append(parsed)
    if timestamped_lines:
        segments: list[GigasttSegment] = []
        for index, (start, explicit_end, line_text) in enumerate(timestamped_lines):
            next_start = timestamped_lines[index + 1][0] if index + 1 < len(timestamped_lines) else None
            end = explicit_end if explicit_end is not None else next_start
            if end is None or end <= start:
                end = start + 30.0
            segments.append(GigasttSegment(start, end, None, line_text))
        return segments, True

    body = _strip_candidate_text("\n".join(fallback_lines) if fallback_lines else text)
    return [GigasttSegment(0.0, 1_000_000_000.0, None, body)] if body else [], False


def _strip_candidate_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = _MARKDOWN_HEADING_RE.sub("", cleaned)
    cleaned = cleaned.strip("`*_> \t")
    return _SPACE_RE.sub(" ", cleaned).strip()


def _strip_candidate_text(text: str) -> str:
    cleaned_lines = []
    for line in text.splitlines():
        cleaned = _strip_candidate_line(line)
        if cleaned:
            cleaned_lines.append(cleaned)
    return _SPACE_RE.sub(" ", " ".join(cleaned_lines)).strip()


def _parse_timestamped_candidate_line(line: str) -> tuple[float, float | None, str] | None:
    interval = _TIMESTAMP_INTERVAL_RE.search(line)
    if interval is not None:
        start = _seconds_from_reference_value(interval.group(1))
        end = _seconds_from_reference_value(interval.group(2))
        text = line[interval.end():].strip(" `:-–—")
        if not text:
            text = line[: interval.start()].strip(" `:-–—")
        return float(start or 0.0), float(end) if end is not None else None, _strip_candidate_transcript_text(text)

    timestamp = _TIMESTAMP_RE.search(line)
    if timestamp is None:
        return None
    start = _seconds_from_reference_value(timestamp.group(1))
    text = f"{line[:timestamp.start()]} {line[timestamp.end():]}".strip(" `:-–—")
    return float(start or 0.0), None, _strip_candidate_transcript_text(text)


def _strip_candidate_transcript_text(text: str) -> str:
    cleaned = _SPEAKER_PREFIX_RE.sub("", text).strip()
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\b", " ", cleaned)
    cleaned = cleaned.strip(" `:-–—")
    return _SPACE_RE.sub(" ", cleaned).strip()


def _quality_reference_paths(target: Path) -> list[Path]:
    if not target.exists():
        raise ValueError(f"quality reference path not found: {target}")
    if target.is_file():
        return [target]
    paths = sorted(
        path
        for path in target.glob("**/*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}
    )
    return paths


def _load_quality_references_json(path: Path) -> list[QualityReference]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read quality references {path}: {error}") from error
    if isinstance(payload, dict):
        records = payload.get("references")
    else:
        records = payload
    if not isinstance(records, list):
        raise ValueError(f"quality references must be a JSON list or object with references: {path}")
    return [
        _quality_reference_from_record(record, path=path, fallback_index=index + 1)
        for index, record in enumerate(records)
    ]


def _load_quality_references_jsonl(path: Path) -> list[QualityReference]:
    references: list[QualityReference] = []
    for line_index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"could not read quality reference {path}:{line_index}: {error}") from error
        references.append(_quality_reference_from_record(record, path=path, fallback_index=line_index))
    return references


def _quality_reference_from_record(record: object, *, path: Path, fallback_index: int) -> QualityReference:
    if not isinstance(record, dict):
        raise ValueError(f"quality reference entry must be an object: {path}")
    reference = _first_present(record, "reference", "reference_text", "text")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError(f"quality reference entry is missing reference text: {path}")
    source = _first_present(record, "source", "source_name", "file", "audio")
    terms = _terms_list(_first_present(record, "terms", "keywords", "glossary"))
    reference_id = _first_present(record, "id", "name")
    notes = _first_present(record, "notes", "comment")
    return QualityReference(
        id=str(reference_id).strip() if reference_id is not None and str(reference_id).strip() else f"{path.stem}-{fallback_index}",
        source=str(source).strip() if source is not None and str(source).strip() else None,
        start=_seconds_from_reference_value(_first_present(record, "start", "start_seconds", "start_time")),
        end=_seconds_from_reference_value(_first_present(record, "end", "end_seconds", "end_time")),
        reference=_SPACE_RE.sub(" ", reference).strip(),
        terms=terms,
        notes=str(notes).strip() if notes is not None and str(notes).strip() else None,
        path=str(path),
    )


def _first_present(record: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _terms_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.replace(";", ",").split(",")
    elif isinstance(raw, list):
        items = [str(item) for item in raw]
    else:
        return []
    return [item.strip() for item in items if item.strip()]


def _seconds_from_reference_value(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    parts = text.split(":")
    if not 2 <= len(parts) <= 3:
        raise ValueError(f"invalid timestamp value: {value}")
    numbers = [float(part.replace(",", ".")) for part in parts]
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    hours, minutes, seconds = numbers
    return hours * 3600 + minutes * 60 + seconds


def _source_matches(source_name: str, reference_source: str) -> bool:
    source_key = _loose_source_key(source_name)
    reference_key = _loose_source_key(reference_source)
    if not source_key or not reference_key:
        return False
    return (
        source_key == reference_key
        or source_key in reference_key
        or reference_key in source_key
    )


def _loose_source_key(value: str) -> str:
    name = Path(str(value).replace("\\", "/")).stem
    return _LOOSE_SOURCE_RE.sub("", name).lower().replace("ё", "е")


def _segment_overlaps(segment: GigasttSegment, *, start: float | None, end: float | None) -> bool:
    if start is not None and segment.end < start:
        return False
    if end is not None and segment.start > end:
        return False
    return True


def _normalized_words(text: str) -> list[str]:
    return [word.lower().replace("ё", "е") for word in _WORD_RE.findall(text)]


def _normalized_text_for_distance(text: str) -> str:
    return " ".join(_normalized_words(text))


def _levenshtein(left: list[str], right: list[str]) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_value in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (0 if left_value == right_value else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _readability_metrics(text: str) -> dict[str, object]:
    words = _WORD_RE.findall(text)
    word_count = len(words)
    letters = [char for char in text if char.isalpha()]
    upper_letters = [char for char in letters if char.isupper()]
    punctuation_count = sum(text.count(char) for char in ".,?!:;")
    sentences = [sentence.strip() for sentence in re.split(r"[.!?]+", text) if sentence.strip()]
    sentence_caps = 0
    for sentence in sentences:
        first_alpha = next((char for char in sentence if char.isalpha()), "")
        if first_alpha and first_alpha.isupper():
            sentence_caps += 1
    return {
        "punctuation_count": punctuation_count,
        "punctuation_per_100_words": round(punctuation_count / max(1, word_count) * 100, 1),
        "upper_letter_percent": round(len(upper_letters) / max(1, len(letters)) * 100, 1),
        "sentence_count": len(sentences),
        "sentence_capitalized_percent": round(sentence_caps / max(1, len(sentences)) * 100, 1),
    }


def _token_overlap(candidate_tokens: list[str], reference_tokens: list[str]) -> dict[str, object]:
    if not reference_tokens and not candidate_tokens:
        return {"token_precision": 1.0, "token_recall": 1.0, "token_f1": 1.0}
    if not reference_tokens or not candidate_tokens:
        return {"token_precision": 0.0, "token_recall": 0.0, "token_f1": 0.0}
    candidate_counts = Counter(candidate_tokens)
    reference_counts = Counter(reference_tokens)
    overlap = sum((candidate_counts & reference_counts).values())
    precision = overlap / max(1, len(candidate_tokens))
    recall = overlap / max(1, len(reference_tokens))
    f1 = 2 * precision * recall / max(0.000001, precision + recall)
    return {
        "token_precision": round(precision, 3),
        "token_recall": round(recall, 3),
        "token_f1": round(f1, 3),
    }


def _found_terms(text: str, terms: list[str]) -> list[str]:
    text_key = _normalized_text_for_term_search(text)
    found: list[str] = []
    for term in terms:
        term_key = _normalized_text_for_term_search(term)
        if term_key and term_key in text_key:
            found.append(term)
    return found


def _normalized_text_for_term_search(text: str) -> str:
    return " ".join(_normalized_words(text))


def _score_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _avg_score(scores: list[dict[str, object]], key: str) -> float | None:
    values: list[float] = []
    for score in scores:
        value = score.get(key)
        if isinstance(value, int | float):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _candidate_scores_by_name(entries: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    scores_by_name: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        candidates = entry.get("candidates")
        if not isinstance(candidates, dict):
            continue
        for name, payload in candidates.items():
            if not isinstance(payload, dict):
                continue
            score = _score_dict(payload.get("score"))
            scores_by_name.setdefault(str(name), []).append(score)
    return scores_by_name


def _candidate_summary(scores: list[dict[str, object]], *, winners: list[str], winner_name: str) -> dict[str, object]:
    return {
        "avg_word_similarity": _avg_score(scores, "word_similarity"),
        "avg_char_similarity": _avg_score(scores, "char_similarity"),
        "avg_token_f1": _avg_score(scores, "token_f1"),
        "avg_punctuation_per_100_words": _avg_score(scores, "punctuation_per_100_words"),
        "missing_window_count": sum(1 for score in scores if not score.get("candidate_word_count")),
        "better_count": winners.count(winner_name),
    }


def _benchmark_winner(raw_score: dict[str, object], edited_score: dict[str, object]) -> str:
    return _benchmark_winner_from_scores({"raw": raw_score, "edited": edited_score})


def _benchmark_winner_from_scores(scores_by_name: dict[str, dict[str, object]]) -> str:
    if not scores_by_name:
        return "tie"
    ranked = sorted(
        scores_by_name.items(),
        key=lambda item: _score_rank(item[1]),
        reverse=True,
    )
    if len(ranked) == 1:
        return ranked[0][0]
    best_name, best_score = ranked[0]
    second_score = ranked[1][1]
    if _scores_tied(best_score, second_score):
        return "tie"
    return best_name


def _score_rank(score: dict[str, object]) -> tuple[float, float, float, float, float]:
    return (
        float(score.get("token_f1") or 0.0),
        float(score.get("word_similarity") or 0.0),
        float(score.get("char_similarity") or 0.0),
        float(score.get("term_coverage") or 0.0),
        float(score.get("punctuation_per_100_words") or 0.0),
    )


def _scores_tied(best: dict[str, object], second: dict[str, object]) -> bool:
    best_rank = _score_rank(best)
    second_rank = _score_rank(second)
    return (
        abs(best_rank[0] - second_rank[0]) <= 0.015
        and abs(best_rank[1] - second_rank[1]) <= 0.015
        and abs(best_rank[2] - second_rank[2]) <= 0.015
    )


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
