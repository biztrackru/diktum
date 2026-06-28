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
from voice_recognizer.transcript_repair import detect_suspicious_spans  # noqa: E402
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
