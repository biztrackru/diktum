"""Fast local smoke fixtures that avoid private audio, models and sockets.

Run directly:
    PYTHONPATH=app/src python3 tests/test_local_smoke.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))

from voice_recognizer.gigastt import (  # noqa: E402
    GigasttResult,
    GigasttSegment,
    GigasttWord,
    analyze_asr_quality,
    analyze_speaker_quality,
)
import voice_recognizer.web as web  # noqa: E402


def _words(text: str, *, speaker: int | None = 0) -> list[GigasttWord]:
    words = text.split()
    return [
        GigasttWord(
            start=index * 0.5,
            end=index * 0.5 + 0.35,
            word=word,
            confidence=0.98,
            speaker=speaker,
        )
        for index, word in enumerate(words)
    ]


def test_asr_quality_warning_fixture() -> None:
    text = " ".join(["пример"] * 70)
    result = GigasttResult(duration=42.0, text=text, words=_words(text))
    quality = analyze_asr_quality(result)
    assert quality["status"] == "warning"
    assert "low_punctuation" in quality["warnings"]


def test_speaker_quality_island_fixture() -> None:
    segments: list[GigasttSegment] = []
    cursor = 0.0
    for index in range(10):
        speaker = index % 2
        other = 1 - speaker
        segments.extend(
            [
                GigasttSegment(cursor, cursor + 3.0, speaker, "длинная реплика основного спикера"),
                GigasttSegment(cursor + 3.05, cursor + 3.45, other, "да"),
                GigasttSegment(cursor + 3.50, cursor + 6.50, speaker, "продолжение той же мысли"),
            ]
        )
        cursor += 7.0
    quality = analyze_speaker_quality(segments)
    assert quality["status"] == "warning"
    assert quality["speaker_island_count"] >= 5
    assert "short_speaker_islands" in quality["warnings"]


def test_manifest_result_payload_quality_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "outputs" / "pipeline"
        output_dir.mkdir(parents=True)
        transcript = output_dir / "synthetic.transcript.md"
        transcript.write_text("# Synthetic\n\nText\n", encoding="utf-8")
        manifest_path = output_dir / "synthetic.manifest.json"
        repair_path = output_dir / "synthetic.repair.json"
        repair_path.write_text('{"repair_report_version":1}', encoding="utf-8")
        edited_markdown = output_dir / "synthetic.edited.md"
        edited_text = output_dir / "synthetic.edited.txt"
        edited_markdown.write_text("# Edited\n", encoding="utf-8")
        edited_text.write_text("Edited\n", encoding="utf-8")
        asr_quality = {
            "version": 1,
            "status": "warning",
            "warnings": ["low_punctuation"],
            "word_count": 70,
            "punctuation_count": 0,
            "punctuation_per_100_words": 0.0,
            "upper_word_percent": 0.0,
            "sentence_start_count": 0,
            "sentence_capitalized_percent": 0.0,
        }
        speaker_quality = {
            "version": 1,
            "status": "warning",
            "warnings": ["short_speaker_islands"],
            "speaker_count": 2,
            "segment_count": 30,
            "speaker_switch_count": 20,
            "switches_per_minute": 8.0,
            "short_turn_count": 10,
            "short_turn_percent": 33.3,
            "speaker_island_count": 10,
            "median_turn_seconds": 3.0,
            "median_turn_words": 4.0,
        }
        manifest_path.write_text(
            json.dumps(
                {
                    "manifest_version": 2,
                    "status": "done",
                    "created_at": time.time(),
                    "completed_at": time.time(),
                    "source": "Inbox/synthetic.m4a",
                    "duration": 42.0,
                    "result_duration": 42.0,
                    "word_count": 70,
                    "speaker_count": 2,
                    "asr_engine": "gigastt-gigaam-v3",
                    "device": "cpu",
                    "asr_quality": asr_quality,
                    "speaker_quality": speaker_quality,
                    "speaker_constraints": {"num_speakers": None, "min_speakers": None, "max_speakers": None},
                    "outputs": {"detailed_markdown": str(transcript.relative_to(root))},
                    "speaker_samples": {},
                    "speaker_names": {"1": "Спикер 1", "2": "Спикер 2"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        payload = web._result_payload(manifest_path, root)
        assert payload is not None
        assert payload["status"] == "done"
        assert payload["asr_quality"] == asr_quality
        assert payload["speaker_quality"] == speaker_quality
        assert payload["files"][0]["key"] == "detailed_markdown"
        assert any(file["key"] == "edited_markdown" for file in payload["files"])
        assert any(file["key"] == "edited_text" for file in payload["files"])
        assert any(file["key"] == "repair_json" and file["url"].endswith("synthetic.repair.json") for file in payload["files"])


def test_web_render_js_syntax() -> None:
    node = shutil.which("node")
    assert node, "node is required for web render JS syntax smoke"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inbox = root / "Inbox"
        output_dir = root / "outputs" / "pipeline"
        inbox.mkdir()
        output_dir.mkdir(parents=True)
        config = web.WebConfig(root=root, inbox=inbox, output_dir=output_dir, host="127.0.0.1", port=0)

        class Handler(web.VoiceRecognizerHandler):
            web_config = config

        handler = object.__new__(Handler)
        html = Handler._render_index(handler)
        assert "<title>Voice Recognizer</title>" in html
        scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
        assert scripts, "rendered page should contain inline JS"
        script_path = root / "rendered-index.js"
        script_path.write_text("\n\n".join(scripts), encoding="utf-8")
        result = subprocess.run([node, "--check", str(script_path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout


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
