"""Integration tests for the web server's security guards.

Spins up the real handler on an ephemeral localhost port and exercises the
HTTP surface. Run with pytest, or directly:  python3 tests/test_web_security.py
"""

from __future__ import annotations

import http.client
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))

import voice_recognizer.web as web  # noqa: E402

BOUNDARY = "----vrwebtestboundary"


class _Server:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "Inbox").mkdir()
        (root / "outputs").mkdir()
        self.root = root
        config = web.WebConfig(
            root=root.resolve(),
            inbox=(root / "Inbox").resolve(),
            output_dir=(root / "outputs").resolve(),
            host="127.0.0.1",
            port=0,
        )

        class Handler(web.VoiceRecognizerHandler):
            web_config = config

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method, path, *, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        sent = {"Host": f"127.0.0.1:{self.port}"}
        if headers:
            sent.update(headers)
        conn.request(method, path, body=body, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()


def _multipart(parts):
    body = b""
    for field, filename, ctype, data in parts:
        body += f"--{BOUNDARY}\r\n".encode()
        disp = f'form-data; name="{field}"'
        if filename is not None:
            disp += f'; filename="{filename}"'
        body += f"Content-Disposition: {disp}\r\n".encode()
        if ctype:
            body += f"Content-Type: {ctype}\r\n".encode()
        body += b"\r\n" + data + b"\r\n"
    body += f"--{BOUNDARY}--\r\n".encode()
    return body


# --- H-1: Host allowlist (anti DNS-rebinding) ---------------------------

def test_local_host_allowed():
    srv = _Server()
    try:
        status, _ = srv.request("GET", "/")
        assert status == 200, status
    finally:
        srv.close()


def test_rebinding_host_blocked_on_index():
    srv = _Server()
    try:
        status, _ = srv.request("GET", "/", headers={"Host": "evil.example.com"})
        assert status == 403, status
    finally:
        srv.close()


def test_rebinding_host_blocked_on_api():
    srv = _Server()
    try:
        status, _ = srv.request("GET", "/api/results", headers={"Host": "attacker.test"})
        assert status == 403, status
    finally:
        srv.close()


# --- H-1/M-1: CSRF (Origin / Sec-Fetch-Site / Content-Type) -------------

def test_cross_origin_post_blocked():
    srv = _Server()
    try:
        status, _ = srv.request(
            "POST", "/api/jobs",
            headers={"Origin": "http://evil.example.com", "Content-Type": "application/json"},
            body=b"{}",
        )
        assert status == 403, status
    finally:
        srv.close()


def test_cross_site_secfetch_blocked():
    srv = _Server()
    try:
        status, _ = srv.request(
            "POST", "/api/jobs",
            headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
            body=b"{}",
        )
        assert status == 403, status
    finally:
        srv.close()


def test_non_json_content_type_rejected():
    srv = _Server()
    try:
        # Simple-request CSRF vector: text/plain to skip preflight.
        status, _ = srv.request(
            "POST", "/api/jobs",
            headers={"Content-Type": "text/plain"},
            body=b"{}",
        )
        assert status == 400, status
    finally:
        srv.close()


def test_missing_json_content_type_rejected():
    srv = _Server()
    try:
        status, _ = srv.request("POST", "/api/jobs", body=b"{}")
        assert status == 400, status
    finally:
        srv.close()


def test_same_origin_delete_allowed_through_guard():
    # DELETE carries no body/Content-Type; guard must allow same-origin and the
    # handler then reports the missing job (not a 403).
    srv = _Server()
    try:
        status, _ = srv.request(
            "DELETE", "/api/jobs/does-not-exist",
            headers={"Origin": f"http://127.0.0.1:{srv.port}"},
        )
        assert status == 400, status  # "job not found" -> ValueError -> 400
    finally:
        srv.close()


# --- M-2: body / upload size limits -------------------------------------

def test_json_body_too_large():
    srv = _Server()
    original = web.MAX_JSON_BODY_BYTES
    web.MAX_JSON_BODY_BYTES = 8
    try:
        status, _ = srv.request(
            "POST", "/api/jobs",
            headers={"Content-Type": "application/json"},
            body=b'{"source":"a-long-value"}',
        )
        assert status == 400, status
    finally:
        web.MAX_JSON_BODY_BYTES = original
        srv.close()


def test_upload_too_large():
    srv = _Server()
    original = web.MAX_UPLOAD_BYTES
    web.MAX_UPLOAD_BYTES = 16
    try:
        body = _multipart([("files", "a.mp3", "audio/mpeg", b"x" * 4096)])
        status, _ = srv.request(
            "POST", "/api/uploads",
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
            body=body,
        )
        assert status == 400, status
    finally:
        web.MAX_UPLOAD_BYTES = original
        srv.close()


def test_malformed_upload_removes_partial_file():
    srv = _Server()
    try:
        body = (
            f"--{BOUNDARY}\r\n"
            'Content-Disposition: form-data; name="files"; filename="partial.mp3"\r\n'
            "Content-Type: audio/mpeg\r\n"
            "\r\n"
            "partial-bytes-without-final-boundary"
        ).encode()
        status, _ = srv.request(
            "POST",
            "/api/uploads",
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
            body=body,
        )
        assert status == 400, status
        assert not list((srv.root / "Inbox").glob("partial*.mp3"))
    finally:
        srv.close()


def test_invalid_later_upload_rolls_back_earlier_file():
    srv = _Server()
    try:
        body = _multipart(
            [
                ("files", "ok.mp3", "audio/mpeg", b"audio"),
                ("files", "bad.exe", "application/octet-stream", b"MZ..."),
            ]
        )
        status, _ = srv.request(
            "POST",
            "/api/uploads",
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
            body=body,
        )
        assert status == 400, status
        assert not list((srv.root / "Inbox").glob("*"))
    finally:
        srv.close()


# --- path traversal (regression) ----------------------------------------

def test_path_traversal_blocked():
    srv = _Server()
    try:
        for path in ("/outputs/../../etc/passwd", "/outputs/..%2f..%2f.env"):
            status, _ = srv.request("GET", path)
            assert status in (403, 404), (path, status)
    finally:
        srv.close()


def test_output_range_response_streams_valid_bytes():
    srv = _Server()
    original = web.RESPONSE_STREAM_CHUNK_BYTES
    web.RESPONSE_STREAM_CHUNK_BYTES = 3
    try:
        payload = b"0123456789abcdef"
        target = srv.root / "outputs" / "range.bin"
        target.write_bytes(payload)
        status, data = srv.request("GET", "/outputs/range.bin", headers={"Range": "bytes=0-"})
        assert status == 206, status
        assert data == payload
        status, data = srv.request("GET", "/outputs/range.bin", headers={"Range": "bytes=2-5"})
        assert status == 206, status
        assert data == b"2345"
    finally:
        web.RESPONSE_STREAM_CHUNK_BYTES = original
        srv.close()


# --- upload happy path & validation -------------------------------------

def test_upload_happy_path():
    srv = _Server()
    try:
        body = _multipart([("files", "memo.mp3", "audio/mpeg", b"ID3audio-bytes")])
        status, _ = srv.request(
            "POST", "/api/uploads",
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
            body=body,
        )
        assert status == 201, status
        saved = list((srv.root / "Inbox").glob("*.mp3"))
        assert saved, "uploaded file should be saved in Inbox"
        assert saved[0].read_bytes() == b"ID3audio-bytes"
    finally:
        srv.close()


def test_upload_unsupported_extension_rejected():
    srv = _Server()
    try:
        body = _multipart([("files", "evil.exe", "application/octet-stream", b"MZ...")])
        status, _ = srv.request(
            "POST", "/api/uploads",
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
            body=body,
        )
        assert status == 400, status
        assert not list((srv.root / "Inbox").glob("*.exe"))
    finally:
        srv.close()


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
