"""Tests for diagnostic transcript repair reports.

Run directly:
    PYTHONPATH=app/src python3 tests/test_transcript_repair.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))

from voice_recognizer.gigastt import GigasttSegment  # noqa: E402
from voice_recognizer.transcript_repair import (  # noqa: E402
    build_quality_benchmark_report,
    detect_suspicious_spans,
    load_quality_references,
    normalize_text,
    render_edited_segments,
    score_text_against_reference,
)
import voice_recognizer.cli as cli  # noqa: E402


def test_detect_suspicious_spans_from_quality_and_speaker_island() -> None:
    segments = [
        GigasttSegment(0.0, 5.0, 0, "это длинная реплика без всякой пунктуации и с маленькой буквы"),
        GigasttSegment(5.1, 5.6, 1, "СМО"),
        GigasttSegment(5.7, 8.0, 0, "продолжение той же мысли"),
    ]
    spans = detect_suspicious_spans(
        segments,
        asr_quality={"warnings": ["low_punctuation", "low_sentence_casing"]},
        speaker_quality={"warnings": ["short_speaker_islands"]},
    )
    reasons = {reason for span in spans for reason in span.reasons}
    assert "missing_punctuation" in reasons
    assert "missing_sentence_casing" in reasons
    assert "all_caps_token" in reasons
    assert "speaker_island" in reasons
    assert any(span.severity == "high" for span in spans)


def test_normalize_text_portable_cleanup() -> None:
    text = "е. мейл нужен для того, чтоб по по пуберт туда прислать отчет который с генерится из за формы"
    assert normalize_text(text) == "Email нужен для того, чтоб по туда прислать отчет который сгенерится из-за формы."


def test_render_edited_segments_reassigns_short_speaker_island() -> None:
    segments = [
        GigasttSegment(0.0, 3.0, 0, "это длинная мысль"),
        GigasttSegment(3.1, 3.5, 1, "да"),
        GigasttSegment(3.6, 6.0, 0, "которая продолжается"),
    ]
    edited = render_edited_segments(segments)
    assert len(edited) == 1
    assert edited[0].speaker == 0
    assert "да которая" in edited[0].text


def test_score_text_against_reference_rewards_readable_candidate() -> None:
    reference = "Что там заполняешь? Email нужен, чтобы прислать отчет."
    raw = "че там заполняешь емейл нужен чтобы прислать отчет"
    edited = "Что там заполняешь? Email нужен, чтобы прислать отчет."

    raw_score = score_text_against_reference(raw, reference, terms=["email", "отчет"])
    edited_score = score_text_against_reference(edited, reference, terms=["email", "отчет"])

    assert edited_score["word_similarity"] > raw_score["word_similarity"]
    assert edited_score["char_similarity"] > raw_score["char_similarity"]
    assert edited_score["token_f1"] > raw_score["token_f1"]
    assert edited_score["punctuation_per_100_words"] > raw_score["punctuation_per_100_words"]
    assert edited_score["missing_terms"] == []


def test_quality_benchmark_report_uses_local_reference_windows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reference_dir = root / ".local-quality" / "references"
        reference_dir.mkdir(parents=True)
        reference_path = reference_dir / "synthetic.json"
        reference_path.write_text(
            json.dumps(
                {
                    "references": [
                        {
                            "id": "synthetic-000",
                            "source": "synthetic interview.m4a",
                            "start": "00:00:08",
                            "end": "00:00:15",
                            "reference": "Что там заполняешь? Email нужен, чтобы прислать отчет.",
                            "terms": ["email", "отчет"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        references = load_quality_references(reference_dir)
        raw_segments = [
            GigasttSegment(8.0, 11.0, 0, "че там заполняешь"),
            GigasttSegment(11.1, 15.0, 0, "емейл нужен чтобы прислать отчет"),
            GigasttSegment(30.0, 35.0, 0, "лишний текст вне окна"),
        ]
        edited_segments = [
            GigasttSegment(8.0, 15.0, 0, "Что там заполняешь? Email нужен, чтобы прислать отчет."),
        ]

        report = build_quality_benchmark_report(
            manifest_path=root / "synthetic.manifest.json",
            source_name="synthetic interview.m4a",
            references=references,
            raw_segments=raw_segments,
            edited_segments=edited_segments,
        )

        summary = report["summary"]
        entry = report["entries"][0]
        assert summary["reference_count"] == 1
        assert summary["edited_better_count"] == 1
        assert summary["edited_avg_token_f1"] > summary["raw_avg_token_f1"]
        assert entry["winner"] == "edited"
        assert "лишний текст" not in entry["texts"]["raw"]
        assert entry["edited"]["missing_terms"] == []


def test_rewrite_manifest_exports_updates_edited_speaker_names_without_rerun() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "outputs" / "pipeline"
        output_dir.mkdir(parents=True)
        asr_json = output_dir / "synthetic.gigastt.json"
        manifest_path = output_dir / "synthetic.manifest.json"
        words = [
            {"start": 0.0, "end": 0.4, "word": "е.", "confidence": 0.99, "speaker": 0},
            {"start": 0.5, "end": 0.9, "word": "мейл", "confidence": 0.99, "speaker": 0},
            {"start": 1.0, "end": 1.4, "word": "с", "confidence": 0.99, "speaker": 1},
            {"start": 1.5, "end": 1.9, "word": "генерится", "confidence": 0.99, "speaker": 1},
        ]
        asr_json.write_text(
            json.dumps({"duration": 2.0, "text": "е. мейл с генерится", "words": words}, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "manifest_version": 2,
                    "status": "done",
                    "source": "Inbox/synthetic.m4a",
                    "created_at": 100.0,
                    "completed_at": 123.0,
                    "duration": 2.0,
                    "word_count": len(words),
                    "speaker_count": 2,
                    "asr_engine": "gigastt-gigaam-v3",
                    "asr_json": str(asr_json),
                    "outputs": {},
                    "speaker_names": {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        outputs = cli.rewrite_manifest_exports(manifest_path, speaker_names={0: "Андрей", 1: "Артем"})
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        edited_markdown = outputs["edited_markdown"].read_text(encoding="utf-8")
        edited_text = outputs["edited_text"].read_text(encoding="utf-8")

        assert manifest["completed_at"] == 123.0
        assert manifest["speaker_names"] == {"1": "Андрей", "2": "Артем"}
        assert manifest["outputs"]["edited_markdown"].endswith("synthetic.edited.md")
        assert "## Андрей" in edited_markdown
        assert "Андрей:" in edited_text
        assert "Email" in edited_text
        assert "[00:" not in edited_text


def test_write_manifest_repair_report_does_not_mutate_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "outputs" / "pipeline"
        output_dir.mkdir(parents=True)
        asr_json = output_dir / "synthetic.gigastt.json"
        manifest_path = output_dir / "synthetic.manifest.json"
        words = [
            {"start": 0.0, "end": 0.5, "word": "это", "confidence": 0.99, "speaker": 0},
            {"start": 0.6, "end": 1.0, "word": "длинная", "confidence": 0.99, "speaker": 0},
            {"start": 1.1, "end": 1.5, "word": "реплика", "confidence": 0.99, "speaker": 0},
            {"start": 1.6, "end": 2.0, "word": "без", "confidence": 0.99, "speaker": 0},
            {"start": 2.1, "end": 2.5, "word": "пунктуации", "confidence": 0.99, "speaker": 0},
            {"start": 2.6, "end": 3.0, "word": "которая", "confidence": 0.99, "speaker": 0},
            {"start": 3.1, "end": 3.5, "word": "должна", "confidence": 0.99, "speaker": 0},
            {"start": 3.6, "end": 4.0, "word": "попасть", "confidence": 0.99, "speaker": 0},
            {"start": 4.1, "end": 4.5, "word": "в", "confidence": 0.99, "speaker": 0},
            {"start": 4.6, "end": 5.0, "word": "отчет", "confidence": 0.99, "speaker": 0},
            {"start": 5.1, "end": 5.4, "word": "СМО", "confidence": 0.70, "speaker": 1},
            {"start": 5.5, "end": 6.0, "word": "продолжение", "confidence": 0.99, "speaker": 0},
            {"start": 6.1, "end": 6.6, "word": "мысли", "confidence": 0.99, "speaker": 0},
        ]
        asr_json.write_text(
            json.dumps(
                {
                    "duration": 7.0,
                    "text": " ".join(str(item["word"]) for item in words),
                    "words": words,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        manifest_payload = {
            "manifest_version": 2,
            "status": "done",
            "source": "Inbox/synthetic.m4a",
            "duration": 7.0,
            "word_count": len(words),
            "speaker_count": 2,
            "asr_engine": "gigastt-gigaam-v3",
            "asr_json": str(asr_json),
            "outputs": {},
            "speaker_names": {"1": "Эксперт", "2": "Участник"},
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        before = manifest_path.read_text(encoding="utf-8")

        status, repair_path, span_count = cli._write_manifest_repair_report(manifest_path, force=True)

        assert status == "updated"
        assert span_count >= 1
        assert repair_path == output_dir / "synthetic.repair.json"
        assert manifest_path.read_text(encoding="utf-8") == before
        assert (output_dir / "synthetic.edited.md").exists()
        assert (output_dir / "synthetic.edited.txt").exists()
        edited_markdown = (output_dir / "synthetic.edited.md").read_text(encoding="utf-8")
        edited_text = (output_dir / "synthetic.edited.txt").read_text(encoding="utf-8")
        assert "## Эксперт" in edited_markdown
        assert "Эксперт:" in edited_text
        assert "[00:" not in edited_text
        report = json.loads(repair_path.read_text(encoding="utf-8"))
        assert report["mode"] == "diagnostic-only"
        assert report["summary"]["suspicious_span_count"] == span_count
        assert report["spans"]

        status, skipped_path, skipped_count = cli._write_manifest_repair_report(manifest_path)
        assert status == "skipped"
        assert skipped_path == repair_path
        assert skipped_count == 0


def _run() -> int:
    tests = [value for key, value in sorted(globals().items()) if key.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {error!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
