"""Unit tests for the dependency-free multipart parser.

Run with pytest, or directly:  python3 tests/test_multipart.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))

from voice_recognizer.multipart import (  # noqa: E402
    MultipartError,
    parse_boundary,
    stream_form_files,
)

BOUNDARY = b"----vrtestboundary"


def _build(parts: list[tuple[str, str | None, str | None, bytes]]) -> bytes:
    out = b""
    for field, filename, ctype, data in parts:
        out += b"--" + BOUNDARY + b"\r\n"
        disp = f'form-data; name="{field}"'
        if filename is not None:
            disp += f'; filename="{filename}"'
        out += b"Content-Disposition: " + disp.encode() + b"\r\n"
        if ctype:
            out += b"Content-Type: " + ctype.encode() + b"\r\n"
        out += b"\r\n" + data + b"\r\n"
    out += b"--" + BOUNDARY + b"--\r\n"
    return out


def _collect(body: bytes, *, field_name="files", max_bytes=10_000_000):
    captured: dict[str, bytes] = {}

    def open_target(part):
        chunks: list[bytes] = []

        class Sink:
            def write(self, data: bytes) -> None:
                chunks.append(data)

            def close(self) -> None:
                pass

        def finalize(size: int):
            captured[part.filename] = b"".join(chunks)
            return {"filename": part.filename, "size": size}

        return Sink(), finalize

    results = stream_form_files(
        io.BytesIO(body),
        content_type=f"multipart/form-data; boundary={BOUNDARY.decode()}",
        content_length=len(body),
        max_bytes=max_bytes,
        field_name=field_name,
        open_target=open_target,
    )
    return results, captured


def test_parse_boundary_plain_and_quoted():
    assert parse_boundary("multipart/form-data; boundary=abc") == b"abc"
    assert parse_boundary('multipart/form-data; boundary="a b c"') == b"a b c"
    assert parse_boundary("multipart/form-data; boundary=xyz; charset=utf-8") == b"xyz"
    try:
        parse_boundary("multipart/form-data")
    except MultipartError:
        pass
    else:
        raise AssertionError("missing boundary should raise")


def test_single_file():
    body = _build([("files", "a.mp3", "audio/mpeg", b"hello-bytes")])
    results, captured = _collect(body)
    assert len(results) == 1
    assert results[0]["filename"] == "a.mp3"
    assert results[0]["size"] == len(b"hello-bytes")
    assert captured["a.mp3"] == b"hello-bytes"


def test_multiple_files_and_binary():
    binary = bytes(range(256)) * 4
    body = _build(
        [
            ("files", "a.wav", "audio/wav", binary),
            ("files", "b.m4a", "audio/mp4", b"second"),
        ]
    )
    results, captured = _collect(body)
    assert [r["filename"] for r in results] == ["a.wav", "b.m4a"]
    assert captured["a.wav"] == binary
    assert captured["b.m4a"] == b"second"


def test_non_file_field_ignored():
    body = _build(
        [
            ("note", None, None, b"not a file"),
            ("files", "ok.mp3", "audio/mpeg", b"data"),
        ]
    )
    results, captured = _collect(body)
    assert list(captured) == ["ok.mp3"]
    assert len(results) == 1


def test_size_cap_enforced():
    body = _build([("files", "big.wav", "audio/wav", b"x" * 5000)])
    try:
        _collect(body, max_bytes=1000)
    except MultipartError:
        pass
    else:
        raise AssertionError("oversized body should raise MultipartError")


def test_boundary_spanning_chunks():
    # A body whose part data is larger than the internal read chunk, to exercise
    # the rolling-buffer boundary search.
    big = b"A" * (200 * 1024)
    body = _build([("files", "long.wav", "audio/wav", big)])
    _results, captured = _collect(body)
    assert captured["long.wav"] == big


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
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
