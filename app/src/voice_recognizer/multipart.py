"""Dependency-free streaming parser for multipart/form-data uploads.

This module replaces the deprecated standard-library ``cgi`` module (removed in
Python 3.13). It is intentionally minimal: it only supports what the upload
endpoint needs - extracting file parts from a ``multipart/form-data`` body - and
it streams part bodies straight to a caller-provided sink so large audio uploads
never have to be buffered fully in memory.

Security properties:
- Enforces a hard cap on the total number of bytes read from the socket.
- Enforces a cap on header-line length to avoid unbounded header buffering.
- Never trusts the client-supplied filename for filesystem paths; that
  responsibility stays with the caller (see ``web._safe_upload_name``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional


class MultipartError(ValueError):
    """Raised when the multipart stream is malformed or exceeds limits."""


_CHUNK = 64 * 1024
_MAX_HEADER_LINE = 16 * 1024
_MAX_PART_HEADERS = 64


@dataclass
class FilePart:
    field_name: str
    filename: str
    content_type: Optional[str]


def parse_boundary(content_type: str) -> bytes:
    """Extract and validate the boundary token from a Content-Type header."""
    marker = "boundary="
    index = content_type.find(marker)
    if index == -1:
        raise MultipartError("multipart content-type is missing a boundary")
    boundary = content_type[index + len(marker):].strip()
    # A boundary may be quoted and may be followed by other parameters.
    if boundary.startswith('"'):
        end = boundary.find('"', 1)
        if end == -1:
            raise MultipartError("multipart boundary quoting is malformed")
        boundary = boundary[1:end]
    else:
        boundary = boundary.split(";", 1)[0].strip()
    if not boundary or len(boundary) > 200:
        raise MultipartError("multipart boundary is invalid")
    return boundary.encode("latin-1", "ignore")


class _BoundedReader:
    """Buffered reader over a socket stream with a hard total-byte cap."""

    def __init__(self, stream: BinaryIO, *, content_length: int, max_bytes: int) -> None:
        self._stream = stream
        self._remaining = max(0, content_length)
        self._max_bytes = max_bytes
        self._read_total = 0
        self._buf = bytearray()

    def _pull(self) -> bool:
        if self._remaining <= 0:
            return False
        want = min(_CHUNK, self._remaining)
        data = self._stream.read(want)
        if not data:
            self._remaining = 0
            return False
        self._remaining -= len(data)
        self._read_total += len(data)
        if self._read_total > self._max_bytes:
            raise MultipartError("upload exceeds the maximum allowed size")
        self._buf.extend(data)
        return True

    def read_line(self) -> bytes:
        """Return one line without the trailing CRLF."""
        while True:
            index = self._buf.find(b"\r\n")
            if index != -1:
                line = bytes(self._buf[:index])
                del self._buf[: index + 2]
                return line
            if len(self._buf) > _MAX_HEADER_LINE:
                raise MultipartError("multipart header line is too long")
            if not self._pull():
                # No CRLF and no more data: return whatever is buffered.
                line = bytes(self._buf)
                self._buf.clear()
                return line

    def consume(self, token: bytes) -> bool:
        """If the buffer starts with ``token``, drop it and return True."""
        while len(self._buf) < len(token):
            if not self._pull():
                break
        if self._buf[: len(token)] == token:
            del self._buf[: len(token)]
            return True
        return False

    def stream_until(self, delimiter: bytes, sink: Optional[Callable[[bytes], None]]) -> None:
        """Write bytes to ``sink`` until ``delimiter`` is found and consumed."""
        keep = len(delimiter) - 1
        while True:
            index = self._buf.find(delimiter)
            if index != -1:
                if sink is not None and index:
                    sink(bytes(self._buf[:index]))
                del self._buf[: index + len(delimiter)]
                return
            if len(self._buf) > keep:
                flush_to = len(self._buf) - keep
                if sink is not None:
                    sink(bytes(self._buf[:flush_to]))
                del self._buf[:flush_to]
            if not self._pull():
                raise MultipartError("unexpected end of multipart stream")


def _parse_disposition(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for chunk in value.split(";"):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        key, _, raw = chunk.partition("=")
        key = key.strip().lower()
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = raw[1:-1]
        params[key] = raw
    return params


def stream_form_files(
    stream: BinaryIO,
    *,
    content_type: str,
    content_length: int,
    max_bytes: int,
    field_name: str,
    open_target: Callable[[FilePart], Optional[tuple[BinaryIO, Callable[[int], object]]]],
) -> list[object]:
    """Stream-parse multipart/form-data, saving file parts named ``field_name``.

    ``open_target`` receives a :class:`FilePart` and returns either ``None`` (to
    skip the part) or a tuple ``(writable, finalize)``. ``writable`` is written
    to in chunks; ``finalize(size)`` is invoked once the part body is complete
    and its return value is appended to the result list.
    """
    boundary = parse_boundary(content_type)
    reader = _BoundedReader(stream, content_length=content_length, max_bytes=max_bytes)
    dash_boundary = b"--" + boundary
    body_delimiter = b"\r\n" + dash_boundary

    # Skip any preamble up to (and including) the first boundary.
    reader.stream_until(dash_boundary, None)

    results: list[object] = []
    while True:
        # After a boundary we expect either "--" (final) or CRLF then a part.
        if reader.consume(b"--"):
            break
        if not reader.consume(b"\r\n"):
            # Tolerate trailing whitespace/transport noise before CRLF.
            reader.read_line()

        field: Optional[str] = None
        filename: Optional[str] = None
        part_ctype: Optional[str] = None
        for _ in range(_MAX_PART_HEADERS):
            line = reader.read_line()
            if line == b"":
                break
            decoded = line.decode("utf-8", "replace")
            name, _, raw = decoded.partition(":")
            header = name.strip().lower()
            if header == "content-disposition":
                params = _parse_disposition(raw)
                field = params.get("name")
                filename = params.get("filename")
            elif header == "content-type":
                part_ctype = raw.strip()
        else:
            raise MultipartError("multipart part has too many headers")

        target = None
        if field == field_name and filename:
            target = open_target(FilePart(field_name=field, filename=filename, content_type=part_ctype))

        if target is None:
            reader.stream_until(body_delimiter, None)
            continue

        writable, finalize = target
        written = 0

        def _sink(data: bytes) -> None:
            nonlocal written
            written += len(data)
            writable.write(data)

        try:
            reader.stream_until(body_delimiter, _sink)
        finally:
            writable.close()
        results.append(finalize(written))

    return results
