from __future__ import annotations

import hashlib
import html
import json
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from voice_recognizer.audio import SUPPORTED_MEDIA_EXTENSIONS, iter_media_files, safe_stem
from voice_recognizer.engines import ASR_ENGINE_CHOICES, DEFAULT_ASR_ENGINE, normalize_asr_engine
from voice_recognizer.multipart import FilePart, MultipartError, stream_form_files


MAX_LOG_LINES = 500
SOURCE_FRESHNESS_TOLERANCE_SECONDS = 2.0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value > 0 else default


# Security limits (overridable via environment variables).
# JSON request bodies are tiny control messages; cap them hard.
MAX_JSON_BODY_BYTES = _env_int("VOICE_RECOGNIZER_MAX_JSON_KB", 1024) * 1024
# Uploaded media can be large, but must still be bounded to avoid filling the disk.
MAX_UPLOAD_BYTES = _env_int("VOICE_RECOGNIZER_MAX_UPLOAD_MB", 4096) * 1024 * 1024
# Chunk size for streaming large result files/ranges to the browser.
RESPONSE_STREAM_CHUNK_BYTES = 1024 * 1024
JOB_STORE_VERSION = 1
# Hostnames that are always considered local. The configured bind host is added
# at request time. Used to block DNS-rebinding and cross-origin (CSRF) requests.
LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
JOBS: dict[str, "Job"] = {}
JOB_QUEUE: list[str] = []
RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
JOBS_LOCK = threading.Lock()
WORKER_THREAD: threading.Thread | None = None
MEDIA_METADATA_CACHE: dict[tuple[str, int, int], dict[str, object]] = {}


@dataclass(frozen=True)
class WebConfig:
    root: Path
    inbox: Path
    output_dir: Path
    host: str
    port: int


@dataclass
class Job:
    id: str
    source_path: Path
    source_name: str
    command: list[str]
    output_dir: Path
    markdown_path: Path
    manifest_path: Path
    start: float | None
    duration: float | None
    device: str
    asr_engine: str
    speaker_mode: str
    num_speakers: int | None
    min_speakers: int | None
    max_speakers: int | None
    speaker_names: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "queued"
    returncode: int | None = None
    completed_at: float | None = None
    log: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    process_pid: int | None = None


def run_web_server(
    *,
    root: Path,
    inbox: Path,
    output_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    config = WebConfig(
        root=root.resolve(),
        inbox=(root / inbox).resolve() if not inbox.is_absolute() else inbox.resolve(),
        output_dir=(root / output_dir).resolve() if not output_dir.is_absolute() else output_dir.resolve(),
        host=host,
        port=port,
    )
    _initialize_job_store(config.root)

    class Handler(VoiceRecognizerHandler):
        web_config = config

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Диктум web UI: http://{host}:{port}", flush=True)
    if str(host).strip().lower() not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "[WARNING] The server is bound to a non-local address "
            f"({host}). It has no authentication and is intended for local "
            "single-user use only. Anyone who can reach this address on the "
            "network can read and submit transcriptions. Bind to 127.0.0.1 "
            "unless you fully trust the network.",
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class VoiceRecognizerHandler(BaseHTTPRequestHandler):
    web_config: WebConfig

    def log_message(self, format: str, *args: object) -> None:
        return

    # --- Security guards -------------------------------------------------
    # The server is designed for local single-user use and has no auth, so we
    # defend the browser threat surface explicitly:
    #   * Host allowlist  -> blocks DNS-rebinding (a malicious site rebinding
    #     its domain to 127.0.0.1 to read local transcripts).
    #   * Origin/Sec-Fetch-Site checks on mutating methods -> block CSRF.
    def _local_hostnames(self) -> set[str]:
        allowed = set(LOCAL_HOSTNAMES)
        allowed.add(str(self.web_config.host).strip().strip("[]").lower())
        return allowed

    def _host_allowed(self) -> bool:
        host_header = self.headers.get("Host")
        if not host_header:
            return True  # Non-browser clients (curl/HTTP1.0) may omit Host.
        hostname = host_header.rsplit(":", 1)[0].strip().strip("[]").lower()
        return hostname in self._local_hostnames()

    def _origin_allowed(self) -> bool:
        if (self.headers.get("Sec-Fetch-Site") or "").strip().lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True  # Same-origin requests and non-browser clients send none.
        try:
            hostname = (urlparse(origin).hostname or "").strip().strip("[]").lower()
        except ValueError:
            return False
        return hostname in self._local_hostnames()

    def _guard(self, *, mutating: bool) -> bool:
        if not self._host_allowed():
            self._send_json({"error": "host not allowed"}, status=HTTPStatus.FORBIDDEN)
            return False
        if mutating and not self._origin_allowed():
            self._send_json(
                {"error": "cross-origin request blocked"}, status=HTTPStatus.FORBIDDEN
            )
            return False
        return True

    def do_GET(self) -> None:
        self._handle_get_or_head(head_only=False)

    def do_HEAD(self) -> None:
        self._handle_get_or_head(head_only=True)

    def _handle_get_or_head(self, *, head_only: bool) -> None:
        if not self._guard(mutating=False):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if parsed.path == "/":
            self._send_html(self._render_index(), head_only=head_only)
            return
        if parsed.path == "/api/inbox":
            results = _result_list(self.web_config.root)
            self._send_json({"files": _inbox_files_payload(self.web_config.inbox, results)}, head_only=head_only)
            return
        if parsed.path == "/api/results":
            self._send_json({"results": _result_list(self.web_config.root)}, head_only=head_only)
            return
        if parsed.path == "/api/jobs":
            self._send_json({"jobs": _job_list(self.web_config.root)}, head_only=head_only)
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.removeprefix("/api/jobs/").split("/", 1)[0]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if job is None:
                self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            self._send_json(_job_payload(job, self.web_config.root), head_only=head_only)
            return
        if parsed.path.startswith("/outputs/"):
            self._serve_output(parsed.path, head_only=head_only)
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)

    def do_POST(self) -> None:
        if not self._guard(mutating=True):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/uploads":
            try:
                files = self._save_uploads()
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"files": files}, status=HTTPStatus.CREATED)
            return

        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
            job_id = parsed.path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
            try:
                job = _cancel_job(job_id, self.web_config.root)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(_job_payload(job, self.web_config.root))
            return

        if parsed.path.startswith("/api/results/") and parsed.path.endswith("/speaker-names"):
            result_id = parsed.path.removeprefix("/api/results/").removesuffix("/speaker-names").strip("/")
            try:
                payload = self._read_json_body()
                speaker_names = _speaker_names_payload_to_cli(payload.get("speaker_names"))
                result = _apply_result_speaker_names(result_id, speaker_names, self.web_config.root)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return

        if parsed.path.startswith("/api/results/") and parsed.path.endswith("/rerun"):
            result_id = parsed.path.removeprefix("/api/results/").removesuffix("/rerun").strip("/")
            try:
                job = _create_result_rerun_job(result_id, self.web_config.root)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            with JOBS_LOCK:
                JOBS[job.id] = job
            _enqueue_job(job.id, self.web_config.root)
            self._send_json(_job_payload(job, self.web_config.root), status=HTTPStatus.CREATED)
            return

        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/speaker-names"):
            job_id = parsed.path.removeprefix("/api/jobs/").removesuffix("/speaker-names").strip("/")
            try:
                payload = self._read_json_body()
                speaker_names = _speaker_names_payload_to_cli(payload.get("speaker_names"))
                job = _apply_speaker_names(job_id, speaker_names, self.web_config.root)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(_job_payload(job, self.web_config.root))
            return

        if parsed.path != "/api/jobs":
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
            source = _resolve_source(self.web_config.inbox, str(payload.get("source", "")))
            start = _optional_float(payload.get("start"))
            duration = _optional_float(payload.get("duration"))
            device = str(payload.get("device") or "auto")
            asr_engine = normalize_asr_engine(str(payload.get("asr_engine") or DEFAULT_ASR_ENGINE))
            speaker_mode, num_speakers, min_speakers, max_speakers = _speaker_constraints_from_payload(payload)
            output_dir = _resolve_output_dir(self.web_config.root, str(payload.get("output_dir") or self.web_config.output_dir))
            overwrite = bool(payload.get("overwrite"))
            speaker_names = str(payload.get("speaker_names") or "")
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        job = _create_job(
            source=source,
            output_dir=output_dir,
            start=start,
            duration=duration,
            device=device,
            asr_engine=asr_engine,
            speaker_mode=speaker_mode,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            speaker_names=speaker_names,
            overwrite=overwrite,
            root=self.web_config.root,
        )
        with JOBS_LOCK:
            JOBS[job.id] = job
        _enqueue_job(job.id, self.web_config.root)
        self._send_json(_job_payload(job, self.web_config.root), status=HTTPStatus.CREATED)

    def do_DELETE(self) -> None:
        if not self._guard(mutating=True):
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.removeprefix("/api/jobs/").split("/", 1)[0].strip("/")
            try:
                _delete_job(job_id, self.web_config.root)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"deleted": True, "id": job_id})
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def _render_index(self) -> str:
        files = iter_media_files(self.web_config.inbox)
        file_count = len(files)
        rows = "\n".join(
            f"""
            <button class="file-row" type="button" data-file="{html.escape(path.name)}">
              <span class="file-main">
                <span class="file-title">
                  <span class="file-name">{html.escape(path.name)}</span>
                </span>
                <span class="file-subline">
                  <span>{html.escape(path.suffix.upper().lstrip('.') or 'AUDIO')}</span>
                  <span>{html.escape(_modified_label(path))}</span>
                </span>
              </span>
              <span class="file-size">{_file_size_label(path)}</span>
            </button>
            """
            for path in files
        )
        options = "\n".join(
            f'<option value="{html.escape(path.name)}">{html.escape(path.name)}</option>'
            for path in files
        )
        asr_options = "\n".join(
            _render_asr_engine_option(choice.value, choice.label, choice.available)
            for choice in ASR_ENGINE_CHOICES
        )
        engine_status = _asr_runtime_status(self.web_config.root)
        output_dir = _relative_display(self.web_config.root, self.web_config.output_dir)
        return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Диктум</title>
  <style>
    :root {{
      --bg: #f4f6f7;
      --surface: #ffffff;
      --surface-2: #f8faf9;
      --surface-3: #eef3f1;
      --text: #111719;
      --muted: #647078;
      --soft: #8b969e;
      --border: #d9e0e3;
      --border-strong: #bcc8ce;
      --accent: #0b7f72;
      --accent-dark: #08685d;
      --accent-soft: rgba(11, 127, 114, 0.1);
      --done: #b66a20;
      --running: #0b7f72;
      --danger: #b42318;
      --radius: 8px;
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    [hidden] {{ display: none !important; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background: var(--bg);
    }}
    button, input, select, textarea {{
      font: inherit;
    }}
    button {{
      color: inherit;
    }}
    @media (prefers-reduced-motion: no-preference) {{
      .btn,
      .segment,
      .preset-button,
      .file-row,
      .job-row,
      .result-row,
      .link-chip,
      .badge {{
        transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
      }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      * {{
        transition: none !important;
        scroll-behavior: auto !important;
      }}
    }}
    .shell {{
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto auto 1fr;
    }}
    .topbar {{
      min-height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 20px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }}
    .brand-mark {{
      width: 30px;
      height: 30px;
      display: inline-grid;
      place-items: center;
      border-radius: 7px;
      background: var(--accent);
      color: white;
      font-size: 14px;
      font-weight: 800;
    }}
    h1 {{
      margin: 0;
      font-size: 17px;
      line-height: 1.2;
      font-weight: 760;
      letter-spacing: 0;
    }}
    .brand-subtitle {{
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
      font-weight: 560;
    }}
    .topbar-status {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-align: right;
    }}
    .local-status-text {{
      min-width: 0;
      display: grid;
      gap: 2px;
      line-height: 1.2;
    }}
    .local-address {{
      color: var(--text);
      font-weight: 820;
    }}
    .local-privacy {{
      color: var(--muted);
      font-weight: 650;
    }}
    .status-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 3px rgba(11, 127, 114, 0.14);
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(330px, 390px) minmax(360px, 1fr) minmax(380px, 470px);
      gap: 14px;
      min-height: calc(100vh - 74px);
      padding: 14px;
    }}
    .sidebar, .workbench, .review {{
      min-width: 0;
    }}
    .sidebar, .workbench, .review {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      min-width: 0;
      overflow: hidden;
    }}
    .panel-head {{
      min-height: 42px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .panel-title {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }}
    h2 {{
      margin: 0;
      font-size: 13px;
      line-height: 1.2;
      font-weight: 760;
      letter-spacing: 0;
    }}
    .section-body {{
      display: grid;
      gap: 12px;
      padding: 12px;
    }}
    form {{
      display: grid;
      gap: 12px;
    }}
    label, .field {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.3;
      font-weight: 680;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0 10px;
      color: var(--text);
      background: #fff;
      outline: none;
      font-size: 13px;
      font-weight: 600;
    }}
    input:focus, select:focus, textarea:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(11, 127, 114, 0.12);
    }}
    .btn:focus-visible,
    .segment:focus-visible,
    .preset-button:focus-visible,
    .batch-select:focus-within,
    .result-tab:focus-visible,
    .file-row:focus-visible,
    .job-row:focus-visible,
    .result-row:focus-visible,
    .link-chip:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}
    input:disabled {{
      color: var(--soft);
      background: var(--surface-2);
      cursor: not-allowed;
    }}
    input, select {{
      height: 38px;
    }}
    textarea {{
      min-height: 74px;
      padding: 9px 10px;
      resize: vertical;
      line-height: 1.35;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}
    .setting-line {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
    }}
    .engine-status {{
      min-height: 34px;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }}
    .engine-help {{
      display: block;
      width: 100%;
      color: var(--soft);
      line-height: 1.35;
    }}
    .speaker-controls {{
      display: grid;
      gap: 8px;
    }}
    .speaker-fields[hidden] {{
      display: none;
    }}
    .conditional-controls {{
      display: grid;
      gap: 8px;
    }}
    .conditional-controls[hidden] {{
      display: none;
    }}
    .advanced-settings {{
      border: 1px solid var(--border);
      border-radius: 7px;
      background: var(--surface-2);
      overflow: hidden;
    }}
    .advanced-settings summary {{
      min-height: 38px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 0 10px;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 800;
      list-style: none;
    }}
    .advanced-settings summary::-webkit-details-marker {{
      display: none;
    }}
    .advanced-settings summary::after {{
      content: "v";
      color: var(--soft);
    }}
    .advanced-settings[open] summary::after {{
      content: "^";
    }}
    .advanced-body {{
      display: grid;
      gap: 10px;
      padding: 0 10px 10px;
    }}
    .segmented {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: var(--surface-2);
    }}
    .segment {{
      height: 32px;
      border: 0;
      border-radius: 5px;
      background: transparent;
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
    }}
    .segment.active {{
      color: var(--text);
      background: var(--surface);
      box-shadow: 0 1px 2px rgba(17, 23, 25, 0.08);
    }}
    .speaker-segmented {{
      grid-template-columns: 1.25fr 0.8fr 1fr;
    }}
    .run-segmented {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .center-switch {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      min-width: 176px;
      flex: 0 0 176px;
    }}
    .clip-tools {{
      display: grid;
      gap: 8px;
    }}
    .clip-tools[hidden] {{
      display: none;
    }}
    .preset-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .preset-button {{
      min-height: 30px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      color: var(--accent);
      padding: 0 9px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 780;
    }}
    .preset-button.active {{
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--accent-dark);
    }}
    .batch-tools {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
    }}
    .batch-tools[hidden] {{
      display: none;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .btn {{
      min-height: 38px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface-3);
      color: var(--text);
      padding: 0 12px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 740;
    }}
    .btn.primary {{
      border-color: var(--accent);
      background: var(--accent);
      color: white;
    }}
    .btn.primary:hover {{
      background: var(--accent-dark);
    }}
    .btn.ghost {{
      background: #fff;
    }}
    .btn.danger {{
      border-color: rgba(180, 35, 24, 0.28);
      background: rgba(180, 35, 24, 0.08);
      color: var(--danger);
    }}
    .btn.small {{
      min-height: 30px;
      padding: 0 10px;
      font-size: 12px;
    }}
    .btn.full {{
      flex: 1 1 160px;
    }}
    .btn:disabled {{
      opacity: 0.55;
      cursor: wait;
    }}
    .check-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 620;
    }}
    .check-row input {{
      width: 16px;
      height: 16px;
      padding: 0;
    }}
    .file-list {{
      display: grid;
      gap: 6px;
      max-height: 240px;
      overflow: auto;
    }}
    .file-item {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
      align-items: stretch;
    }}
    .batch-select {{
      display: none;
      align-items: center;
      justify-content: center;
      width: 34px;
      min-height: 42px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
    }}
    .batch-select input {{
      width: 16px;
      height: 16px;
      padding: 0;
    }}
    .file-list.batch-mode .file-item {{
      grid-template-columns: auto minmax(0, 1fr);
    }}
    .file-list.batch-mode .batch-select {{
      display: inline-grid;
    }}
    .file-row {{
      width: 100%;
      min-height: 42px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 8px 10px;
      text-align: left;
      cursor: pointer;
    }}
    .file-row.processed {{
      border-color: rgba(11, 127, 114, 0.28);
    }}
    .file-main {{
      min-width: 0;
      display: grid;
      gap: 4px;
    }}
    .file-title {{
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .file-name {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 660;
    }}
    .file-size {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }}
    .file-subline {{
      min-width: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
    }}
    .file-subline span:not(:last-child)::after {{
      content: "·";
      margin-left: 5px;
      color: var(--border-strong);
    }}
    .processed-tag {{
      flex: 0 0 auto;
      min-height: 22px;
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 0 7px;
      background: rgba(11, 127, 114, 0.11);
      color: var(--accent);
      font-size: 11px;
      font-weight: 800;
    }}
    .processed-tag.changed {{
      background: rgba(182, 106, 32, 0.14);
      color: var(--done);
    }}
    .processed-tag.missing {{
      background: rgba(180, 35, 24, 0.1);
      color: var(--danger);
    }}
    .file-row.active {{
      border-color: var(--accent);
      background: var(--accent-soft);
    }}
    .file-row:hover,
    .job-row:hover,
    .result-row:hover,
    .link-chip:hover {{
      background: var(--surface-2);
    }}
    .queue-summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .work-panel .panel-head {{
      flex-wrap: wrap;
    }}
    .work-panel .job-list,
    .work-panel .result-list {{
      min-height: 300px;
      max-height: 52vh;
    }}
    .job-list {{
      display: grid;
      gap: 8px;
      padding: 12px;
      min-height: 180px;
      max-height: 39vh;
      overflow: auto;
    }}
    .job-row {{
      width: 100%;
      display: grid;
      grid-template-columns: 84px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      min-height: 46px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
      text-align: left;
    }}
    .job-row.active {{
      border-color: var(--accent);
      box-shadow: inset 3px 0 0 var(--accent);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      background: var(--surface-3);
      color: var(--muted);
      font-size: 12px;
      font-weight: 780;
      white-space: nowrap;
    }}
    .badge.queued {{ background: #edf1f2; color: #5c6870; }}
    .badge.running {{ background: rgba(11, 127, 114, 0.12); color: var(--running); }}
    .badge.failed {{ background: rgba(180, 35, 24, 0.1); color: var(--danger); }}
    .badge.done {{ background: rgba(182, 106, 32, 0.13); color: var(--done); }}
    .badge.canceling {{ background: rgba(11, 127, 114, 0.12); color: var(--running); }}
    .badge.canceled {{ background: rgba(180, 35, 24, 0.08); color: var(--danger); }}
    .job-main {{
      min-width: 0;
      display: grid;
      gap: 2px;
    }}
    .job-name {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 720;
    }}
    .job-meta {{
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .job-link {{
      color: var(--accent);
      font-size: 12px;
      font-weight: 780;
      text-decoration: none;
    }}
    .result-list {{
      display: grid;
      gap: 8px;
      padding: 12px;
      min-height: 120px;
      max-height: 28vh;
      overflow: auto;
    }}
    .result-row {{
      width: 100%;
      min-height: 48px;
      display: grid;
      grid-template-columns: 78px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
      text-align: left;
    }}
    .result-row.active {{
      border-color: var(--accent);
      box-shadow: inset 3px 0 0 var(--accent);
    }}
    .result-main {{
      min-width: 0;
      display: grid;
      gap: 2px;
    }}
    .result-name {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 720;
    }}
    .result-meta-line {{
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .result-body {{
      display: grid;
      gap: 12px;
      padding: 12px;
    }}
    .result-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .job-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-left: auto;
    }}
    .result-tabs {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: var(--surface-2);
    }}
    .result-tab {{
      min-height: 32px;
      border: 0;
      border-radius: 5px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 780;
    }}
    .result-tab.active {{
      color: var(--text);
      background: var(--surface);
      box-shadow: 0 1px 2px rgba(17, 23, 25, 0.08);
    }}
    .result-panel {{
      display: grid;
      gap: 12px;
    }}
    .result-panel[hidden] {{
      display: none;
    }}
    .overview-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .overview-item {{
      display: grid;
      gap: 3px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 9px 10px;
      background: #fff;
    }}
    .overview-item span:first-child {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 760;
    }}
    .overview-item span:last-child {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--text);
      font-size: 13px;
      font-weight: 720;
    }}
    .transcript-toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .transcript-preview {{
      max-width: 72ch;
      display: grid;
      gap: 10px;
      color: var(--text);
      font-size: 13px;
      line-height: 1.55;
    }}
    .transcript-turn {{
      display: grid;
      gap: 5px;
      border-left: 3px solid var(--accent);
      padding: 8px 0 8px 10px;
    }}
    .transcript-turn:nth-child(3n + 1) {{
      border-left-color: var(--accent);
    }}
    .transcript-turn:nth-child(3n + 2) {{
      border-left-color: var(--done);
    }}
    .transcript-turn:nth-child(3n + 3) {{
      border-left-color: #476c9b;
    }}
    .transcript-speaker {{
      color: var(--text);
      font-size: 12px;
      font-weight: 820;
    }}
    .transcript-line {{
      margin: 0;
      color: var(--text);
      font-weight: 600;
      overflow-wrap: anywhere;
    }}
    .timecode {{
      display: inline-flex;
      margin-right: 6px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      font-weight: 740;
    }}
    .progress-block,
    .diagnostic-block {{
      display: grid;
      gap: 10px;
      border: 1px solid var(--border);
      border-left-width: 4px;
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .progress-block {{
      border-left-color: var(--accent);
      background: rgba(11, 127, 114, 0.04);
    }}
    .diagnostic-block {{
      border-left-color: var(--danger);
      background: rgba(180, 35, 24, 0.04);
    }}
    .diagnostic-block h3 {{
      margin: 0;
      color: var(--danger);
      font-size: 13px;
      line-height: 1.3;
      font-weight: 780;
    }}
    .diagnostic-block p,
    .progress-block p {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      font-weight: 600;
    }}
    .stage-top {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .stage-list {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 7px;
    }}
    .stage-step {{
      display: grid;
      gap: 5px;
      min-width: 0;
      color: var(--muted);
      font-size: 10px;
      line-height: 1.2;
      font-weight: 760;
      text-align: center;
    }}
    .stage-bar {{
      height: 5px;
      overflow: hidden;
      border-radius: 999px;
      background: var(--surface-2);
    }}
    .stage-bar span {{
      display: block;
      width: 0;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
    }}
    .stage-step.done,
    .stage-step.active {{
      color: var(--accent);
    }}
    .stage-step.done .stage-bar span {{
      width: 100%;
    }}
    .stage-step.active .stage-bar span {{
      width: 64%;
    }}
    .heartbeat {{
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      word-break: break-word;
    }}
    .next-actions {{
      display: grid;
      gap: 5px;
      margin: 0;
      padding-left: 18px;
      color: var(--text);
      font-size: 12px;
      line-height: 1.45;
      font-weight: 620;
    }}
    .link-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .export-groups {{
      display: grid;
      gap: 12px;
    }}
    .export-group {{
      display: grid;
      gap: 7px;
    }}
    .export-group-title {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
      font-weight: 800;
    }}
    .link-chip {{
      display: inline-flex;
      flex-direction: column;
      align-items: flex-start;
      justify-content: center;
      gap: 2px;
      min-height: 32px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 10px;
      color: var(--accent);
      background: #fff;
      text-decoration: none;
      font-size: 13px;
      font-weight: 760;
    }}
    .link-chip small {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
    }}
    .speaker-editor {{
      display: grid;
      gap: 10px;
    }}
    .speaker-row {{
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 8px 10px;
      align-items: center;
    }}
    .speaker-row audio {{
      width: 100%;
      height: 34px;
    }}
    .speaker-row input {{
      grid-column: 1 / -1;
    }}
    .log-summary {{
      display: grid;
      gap: 10px;
      padding: 12px;
      border-top: 1px solid var(--border);
      background: rgba(11, 127, 114, 0.035);
    }}
    .log-summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .log-summary-item {{
      min-width: 0;
      display: grid;
      gap: 3px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 9px;
      background: #fff;
    }}
    .log-summary-item span {{
      color: var(--muted);
      font-size: 10px;
      font-weight: 780;
      text-transform: uppercase;
    }}
    .log-summary-item strong {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--text);
      font-size: 13px;
      font-weight: 780;
    }}
    .log-events {{
      display: grid;
      gap: 5px;
    }}
    .log-event-line {{
      min-width: 0;
      overflow-wrap: anywhere;
      color: #1d2428;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.45;
    }}
    .raw-log {{
      border-top: 1px solid var(--border);
      background: #fbfbfa;
    }}
    .raw-log summary {{
      min-height: 38px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 12px;
      color: var(--text);
      cursor: pointer;
      font-size: 12px;
      font-weight: 780;
    }}
    .raw-log[open] summary {{
      border-bottom: 1px solid var(--border);
    }}
    pre {{
      margin: 0;
      height: 100%;
      min-height: 180px;
      max-height: 32vh;
      padding: 12px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      color: #1d2428;
      background: #fbfbfa;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    .empty {{
      padding: 18px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}
    @media (max-width: 1180px) {{
      main {{
        grid-template-columns: minmax(320px, 380px) 1fr;
      }}
      .review {{
        grid-column: 1 / -1;
      }}
    }}
    @media (max-width: 820px) {{
      .topbar {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .topbar-status {{
        justify-content: flex-start;
        text-align: left;
      }}
      main {{
        grid-template-columns: 1fr;
        padding: 10px;
      }}
      .speaker-row {{
        grid-template-columns: 1fr;
      }}
      .job-row {{
        grid-template-columns: 78px 1fr;
      }}
      .result-row {{
        grid-template-columns: 76px 1fr;
      }}
      .job-link {{
        grid-column: 2;
      }}
      .result-tabs,
      .overview-grid,
      .log-summary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">VR</span>
        <div>
          <h1>Диктум</h1>
          <p class="brand-subtitle">Локальный рабочий стол транскрибации</p>
        </div>
      </div>
      <div class="topbar-status">
        <span class="status-dot" aria-hidden="true"></span>
        <span class="local-status-text">
          <span class="local-address">Локально · 127.0.0.1:{self.web_config.port}</span>
          <span class="local-privacy">Аудио и тексты остаются на этом Mac</span>
        </span>
      </div>
    </header>
    <main>
      <aside class="sidebar">
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">
              <h2>Inbox</h2>
            </div>
            <span class="badge" id="file-count">{file_count} файлов</span>
          </div>
          <div class="section-body">
            <form id="upload-form" enctype="multipart/form-data">
              <label>Загрузить аудио
                <input id="upload-input" name="files" type="file" multiple accept="audio/*,video/mp4,.m4a,.mp3,.wav,.flac,.ogg,.mp4,.mov,.mkv,.webm">
              </label>
              <div class="actions">
                <button class="btn full" id="upload-button" type="submit">Добавить в Inbox</button>
                <span class="badge" id="upload-status" aria-live="polite">готово</span>
              </div>
            </form>
            <label>Источник
              <select name="source" id="source-select" form="job-form" required>
                {options}
              </select>
            </label>
            <div class="file-list" id="file-list">
              {rows or '<div class="empty">Inbox пуст</div>'}
            </div>
          </div>
        </section>

        <form id="job-form">
          <section class="panel">
            <div class="panel-head">
              <h2>Настройки запуска</h2>
              <span class="badge" id="run-mode-label">один файл</span>
            </div>
            <div class="section-body">
              <div class="segmented run-segmented" role="group" aria-label="Режим обработки">
                <button class="segment active" id="mode-single" type="button" data-mode="single">Один файл</button>
                <button class="segment" id="mode-clip" type="button" data-mode="clip">Тест-фрагмент</button>
                <button class="segment" id="mode-batch" type="button" data-mode="batch">Весь Inbox</button>
              </div>
              <div class="batch-tools" id="batch-tools" hidden>
                <span class="badge" id="batch-selection-count">0 выбрано</span>
                <button class="preset-button" type="button" data-batch-action="all">Все</button>
                <button class="preset-button" type="button" data-batch-action="none">Ни одного</button>
              </div>
              <div class="conditional-controls" id="clip-fields" hidden>
                <div class="grid-2">
                  <label>Старт
                    <input name="start" inputmode="decimal" placeholder="0 или 1:20">
                  </label>
                  <label>Длительность
                    <input name="duration" inputmode="decimal" placeholder="2:00">
                  </label>
                </div>
                <div class="clip-tools" id="clip-tools">
                <div class="preset-row" aria-label="Пресеты тестового фрагмента">
                  <button class="preset-button" type="button" data-start="0" data-duration="30">0:30</button>
                  <button class="preset-button" type="button" data-start="0" data-duration="120">2:00</button>
                  <button class="preset-button" type="button" data-start="0" data-duration="300">5:00</button>
                  <span class="badge" id="clip-readout" aria-live="polite">0:00-2:00</span>
                </div>
                </div>
              </div>
              <label>ASR-движок
                <select name="asr_engine">
                  {asr_options}
                </select>
                <span class="engine-status" title="{html.escape(engine_status['title'])}">
                  <span class="badge {html.escape(engine_status['class'])}">{html.escape(engine_status['label'])}</span>
                  <span>{html.escape(engine_status['detail'])}</span>
                  <span class="engine-help">{html.escape(engine_status['help'])}</span>
                </span>
              </label>
              <div class="speaker-controls">
                <div class="setting-line">
                  <span>Определение спикеров</span>
                  <span class="badge" id="speaker-mode-label">auto по файлу</span>
                </div>
                <div class="segmented speaker-segmented" role="group" aria-label="Режим определения спикеров">
                  <button class="segment active" type="button" data-speaker-mode="auto">Auto по файлу</button>
                  <button class="segment" type="button" data-speaker-mode="exact">Точно</button>
                  <button class="segment" type="button" data-speaker-mode="range">Диапазон</button>
                </div>
                <div class="grid-3 speaker-fields" data-speaker-fields="exact" hidden>
                  <label>Спикеров
                    <input name="num_speakers" inputmode="numeric">
                  </label>
                </div>
                <div class="grid-2 speaker-fields" data-speaker-fields="range" hidden>
                  <label>Мин.
                    <input name="min_speakers" inputmode="numeric">
                  </label>
                  <label>Макс.
                    <input name="max_speakers" inputmode="numeric">
                  </label>
                </div>
              </div>
              <details class="advanced-settings" id="advanced-settings">
                <summary>Подробнее</summary>
                <div class="advanced-body">
                  <label>Устройство
                    <select name="device">
                      <option value="auto">auto</option>
                      <option value="mps">mps</option>
                      <option value="cpu">cpu</option>
                    </select>
                  </label>
                  <label>Результаты
                    <input name="output_dir" value="{html.escape(output_dir)}">
                  </label>
                  <label class="check-row">
                    <input name="overwrite" type="checkbox">
                    <span>Пересчитать существующие артефакты</span>
                  </label>
                </div>
              </details>
              <div class="actions">
                <button class="btn primary full" id="run-button" type="submit">Запустить выбранный</button>
                <button class="btn full" id="queue-all-button" type="button">Поставить весь Inbox</button>
                <button class="btn ghost" id="refresh-button" type="button">Обновить</button>
              </div>
            </div>
          </section>
        </form>
      </aside>

      <section class="workbench">
        <section class="panel work-panel">
          <div class="panel-head">
            <div class="panel-title">
              <h2>Работа</h2>
            </div>
            <div class="segmented center-switch" role="group" aria-label="Центральный список">
              <button class="segment active" type="button" data-center-view="queue">Очередь</button>
              <button class="segment" type="button" data-center-view="results">Готовые</button>
            </div>
            <div class="queue-summary" aria-live="polite">
              <span class="badge" id="job-count" data-center-summary="queue">0</span>
              <span class="badge queued" id="queued-count" data-center-summary="queue">0 ожидает</span>
              <span class="badge running" id="running-count" data-center-summary="queue">0 выполняется</span>
              <span class="badge done" id="done-count" data-center-summary="queue">0 готово</span>
              <span class="badge" id="result-count" data-center-summary="results" hidden>0 готово</span>
            </div>
          </div>
          <div class="job-list center-list" id="jobs" data-center-list="queue"><div class="empty">Нет задач</div></div>
          <div class="result-list center-list" id="results-list" data-center-list="results" hidden><div class="empty">Готовые результаты появятся здесь после обработки</div></div>
        </section>
        <section class="panel">
          <div class="panel-head">
            <h2>Журнал</h2>
            <span class="badge" id="active-job" aria-live="polite">-</span>
          </div>
          <div class="log-summary" id="log-summary" aria-live="polite">
            <div class="empty">Журнал появится после запуска задачи</div>
          </div>
          <details class="raw-log" id="raw-log-details">
            <summary>
              <span>Полный технический журнал</span>
              <span class="badge" id="log-line-count">0 строк</span>
            </summary>
            <pre id="log"></pre>
          </details>
        </section>
      </section>

      <section class="review">
        <section class="panel">
          <div class="panel-head">
            <h2>Проверка и экспорт</h2>
            <span class="badge" id="result-state" aria-live="polite">-</span>
          </div>
          <div class="result-body" id="result-details" aria-live="polite"><div class="empty">Нет выбранной задачи</div></div>
        </section>
      </section>
    </main>
  </div>
  <script>
    const form = document.querySelector("#job-form");
    const runButton = document.querySelector("#run-button");
    const queueAllButton = document.querySelector("#queue-all-button");
    const uploadForm = document.querySelector("#upload-form");
    const uploadInput = document.querySelector("#upload-input");
    const uploadButton = document.querySelector("#upload-button");
    const uploadStatus = document.querySelector("#upload-status");
    const fileCountNode = document.querySelector("#file-count");
    const sourceSelect = document.querySelector("#source-select");
    const fileList = document.querySelector("#file-list");
    const jobsNode = document.querySelector("#jobs");
    const resultsList = document.querySelector("#results-list");
    const logNode = document.querySelector("#log");
    const logSummaryNode = document.querySelector("#log-summary");
    const rawLogDetails = document.querySelector("#raw-log-details");
    const logLineCount = document.querySelector("#log-line-count");
    const jobCount = document.querySelector("#job-count");
    const resultCount = document.querySelector("#result-count");
    const queuedCount = document.querySelector("#queued-count");
    const runningCount = document.querySelector("#running-count");
    const doneCount = document.querySelector("#done-count");
    const activeJobNode = document.querySelector("#active-job");
    const resultDetails = document.querySelector("#result-details");
    const resultState = document.querySelector("#result-state");
    const runModeLabel = document.querySelector("#run-mode-label");
    const modeButtons = document.querySelectorAll(".segment[data-mode]");
    const centerButtons = document.querySelectorAll(".segment[data-center-view]");
    const clipFields = document.querySelector("#clip-fields");
    const clipTools = document.querySelector("#clip-tools");
    const clipReadout = document.querySelector("#clip-readout");
    const batchTools = document.querySelector("#batch-tools");
    const batchSelectionCount = document.querySelector("#batch-selection-count");
    const batchActionButtons = document.querySelectorAll("[data-batch-action]");
    const presetButtons = document.querySelectorAll(".preset-button[data-duration]");
    const speakerModeLabel = document.querySelector("#speaker-mode-label");
    const speakerModeButtons = document.querySelectorAll(".segment[data-speaker-mode]");
    const speakerFieldGroups = document.querySelectorAll("[data-speaker-fields]");
    const speakerInputs = {{
      exact: document.querySelector('input[name="num_speakers"]'),
      min: document.querySelector('input[name="min_speakers"]'),
      max: document.querySelector('input[name="max_speakers"]'),
    }};
    let activeJobId = null;
    let activeResultId = null;
    let activeView = "job";
    let renderedResultKey = null;
    let renderedJobsListHtml = "";
    let renderedResultsListHtml = "";
    let runMode = "single";
    let centerView = "queue";
    let speakerMode = "auto";
    let diskResults = [];
    let inboxFiles = [];
    let batchSelectedFiles = new Set();
    let batchKnownFiles = new Set();
    let batchSelectionReady = false;
    let clipValidationOk = true;
    const speakerNameDrafts = new Map();
    const resultTabDrafts = new Map();
    const previewModeDrafts = new Map();
    const transcriptCache = new Map();
    const pipelineStages = [
      {{ key: "audio", label: "Аудио" }},
      {{ key: "asr", label: "ASR" }},
      {{ key: "diarization", label: "Диаризация" }},
      {{ key: "merge", label: "Склейка" }},
      {{ key: "export", label: "Экспорт" }},
    ];

    function syncFileSelection() {{
      document.querySelectorAll(".file-row").forEach((row) => {{
        row.classList.toggle("active", row.dataset.file === sourceSelect.value);
      }});
    }}

    function setRunMode(mode) {{
      runMode = ["single", "clip", "batch"].includes(mode) ? mode : "single";
      modeButtons.forEach((button) => {{
        button.classList.toggle("active", button.dataset.mode === runMode);
      }});
      runModeLabel.textContent = runMode === "batch" ? "весь Inbox" : runMode === "clip" ? "тест-фрагмент" : "полный файл";
      runButton.textContent = runMode === "batch" ? "Поставить весь Inbox" : runMode === "clip" ? "Запустить фрагмент" : "Запустить полный файл";
      queueAllButton.hidden = runMode === "batch";
      clipFields.hidden = runMode !== "clip";
      clipTools.hidden = runMode !== "clip";
      batchTools.hidden = runMode !== "batch";
      fileList.classList.toggle("batch-mode", runMode === "batch");
      sourceSelect.disabled = runMode === "batch" || !sourceSelect.options.length;
      if (runMode === "clip" && !speakerInputs.exact.form.elements.duration.value.trim()) {{
        speakerInputs.exact.form.elements.start.value = "0";
        speakerInputs.exact.form.elements.duration.value = "2:00";
      }}
      if (runMode !== "clip") {{
        speakerInputs.exact.form.elements.start.value = "";
        speakerInputs.exact.form.elements.duration.value = "";
      }}
      if (runMode === "batch") setSpeakerMode("auto");
      updateClipReadout();
      updateBatchSelectionSummary();
    }}

    function setCenterView(view) {{
      centerView = view === "results" ? "results" : "queue";
      centerButtons.forEach((button) => {{
        const active = button.dataset.centerView === centerView;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      }});
      document.querySelectorAll("[data-center-list]").forEach((list) => {{
        list.hidden = list.dataset.centerList !== centerView;
      }});
      document.querySelectorAll("[data-center-summary]").forEach((badge) => {{
        badge.hidden = badge.dataset.centerSummary !== centerView;
      }});
    }}

    function setSpeakerMode(mode) {{
      speakerMode = ["auto", "exact", "range"].includes(mode) ? mode : "auto";
      speakerModeButtons.forEach((button) => {{
        button.classList.toggle("active", button.dataset.speakerMode === speakerMode);
      }});
      const isExact = speakerMode === "exact";
      const isRange = speakerMode === "range";
      speakerFieldGroups.forEach((group) => {{
        group.hidden = group.dataset.speakerFields !== speakerMode;
      }});
      speakerInputs.exact.disabled = !isExact;
      speakerInputs.min.disabled = !isRange;
      speakerInputs.max.disabled = !isRange;
      if (!isExact) speakerInputs.exact.value = "";
      if (!isRange) {{
        speakerInputs.min.value = "";
        speakerInputs.max.value = "";
      }}
      speakerModeLabel.textContent = speakerMode === "exact"
        ? "точное число"
        : speakerMode === "range"
          ? "диапазон"
          : "auto по файлу";
    }}

    function applySpeakerModeToPayload(data) {{
      data.speaker_mode = speakerMode;
      if (speakerMode === "auto") {{
        delete data.num_speakers;
        delete data.min_speakers;
        delete data.max_speakers;
        return;
      }}
      if (speakerMode === "exact") {{
        delete data.min_speakers;
        delete data.max_speakers;
        return;
      }}
      delete data.num_speakers;
    }}

    function normalizeTimeFields(data) {{
      data.start = parseFlexibleTime(data.start);
      data.duration = parseFlexibleTime(data.duration);
      if (runMode === "clip" && !data.duration) data.duration = "120";
    }}

    function parseFlexibleTime(value) {{
      const text = String(value || "").trim();
      if (!text) return "";
      if (!text.includes(":")) return text.replace(",", ".");
      const parts = text.split(":").map((part) => part.trim());
      if (parts.length < 2 || parts.length > 3 || parts.some((part) => part === "" || Number.isNaN(Number(part)))) {{
        throw new Error(`Некорректное время: ${{text}}`);
      }}
      const numbers = parts.map(Number);
      const seconds = numbers.length === 2
        ? numbers[0] * 60 + numbers[1]
        : numbers[0] * 3600 + numbers[1] * 60 + numbers[2];
      return String(seconds);
    }}

    function formatPresetDuration(value) {{
      const seconds = Number(value || 0);
      if (!Number.isFinite(seconds) || seconds <= 0) return "2:00";
      const minutes = Math.floor(seconds / 60);
      const rest = seconds % 60;
      return `${{minutes}}:${{String(rest).padStart(2, "0")}}`;
    }}

    function selectedInboxFile() {{
      return inboxFiles.find((file) => file.name === sourceSelect.value) || null;
    }}

    function updateClipReadout() {{
      if (!clipReadout) return;
      if (runMode !== "clip") {{
        clipValidationOk = true;
        clipReadout.className = "badge";
        clipReadout.textContent = "полный файл";
        updateRunAvailability();
        return;
      }}
      try {{
        const start = Number(parseFlexibleTime(form.elements.start.value) || 0);
        const duration = Number(parseFlexibleTime(form.elements.duration.value) || 120);
        if (!Number.isFinite(start) || !Number.isFinite(duration) || start < 0 || duration <= 0) {{
          throw new Error("Некорректное время");
        }}
        const end = start + duration;
        const file = selectedInboxFile();
        const fileDuration = Number(file?.duration || 0);
        const outsideFile = fileDuration > 0 && end > fileDuration + 0.5;
        clipValidationOk = !outsideFile;
        clipReadout.className = `badge ${{outsideFile ? "failed" : "running"}}`;
        clipReadout.textContent = outsideFile
          ? `фрагмент за пределами файла · файл ${{formatDuration(fileDuration)}}`
          : `${{formatDuration(start)}}-${{formatDuration(end)}}`;
      }} catch (error) {{
        clipValidationOk = false;
        clipReadout.className = "badge failed";
        clipReadout.textContent = String(error.message || error);
      }}
      updateRunAvailability();
    }}

    function updateRunAvailability() {{
      const hasFiles = sourceSelect.options.length > 0;
      const selected = batchSelectedSources().length || batchSelectedFiles.size;
      runButton.disabled = !hasFiles || (runMode === "batch" && selected === 0) || (runMode === "clip" && !clipValidationOk);
      queueAllButton.disabled = !hasFiles;
    }}

    fileList.addEventListener("click", async (event) => {{
      const resultTag = event.target.closest(".processed-tag");
      if (resultTag && resultTag.dataset.resultId) {{
        event.preventDefault();
        await openDiskResult(resultTag.dataset.resultId);
        return;
      }}
      const row = event.target.closest(".file-row");
      if (!row) return;
      if (runMode === "batch") {{
        const checkbox = row.closest(".file-item")?.querySelector(".batch-file-checkbox");
        if (checkbox) {{
          checkbox.checked = !checkbox.checked;
          updateBatchSelectionFromInput(checkbox);
        }}
        return;
      }}
      sourceSelect.value = row.dataset.file;
      setRunMode("single");
      syncFileSelection();
      updateClipReadout();
    }});
    fileList.addEventListener("change", (event) => {{
      const checkbox = event.target.closest(".batch-file-checkbox");
      if (!checkbox) return;
      updateBatchSelectionFromInput(checkbox);
    }});

    sourceSelect.addEventListener("change", () => {{
      setRunMode("single");
      syncFileSelection();
      updateClipReadout();
    }});
    form.elements.start.addEventListener("input", updateClipReadout);
    form.elements.duration.addEventListener("input", updateClipReadout);
    modeButtons.forEach((button) => {{
      button.addEventListener("click", () => setRunMode(button.dataset.mode));
    }});
    centerButtons.forEach((button) => {{
      button.addEventListener("click", () => setCenterView(button.dataset.centerView));
    }});
    presetButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        form.elements.start.value = button.dataset.start || "0";
        form.elements.duration.value = formatPresetDuration(button.dataset.duration);
        setRunMode("clip");
      }});
    }});
    batchActionButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const names = Array.from(sourceSelect.options).map((option) => option.value).filter(Boolean);
        batchSelectedFiles = button.dataset.batchAction === "all" ? new Set(names) : new Set();
        batchSelectionReady = true;
        renderBatchChecks();
        updateBatchSelectionSummary();
      }});
    }});
    speakerModeButtons.forEach((button) => {{
      button.addEventListener("click", () => setSpeakerMode(button.dataset.speakerMode));
    }});
    jobsNode.addEventListener("click", (event) => {{
      if (event.target.closest("a")) return;
      const row = event.target.closest(".job-row");
      if (!row || !jobsNode.contains(row)) return;
      setCenterView("queue");
      activeView = "job";
      activeJobId = row.dataset.job;
      activeResultId = null;
      renderResultList();
      loadJobs();
    }});
    resultsList.addEventListener("click", (event) => {{
      const row = event.target.closest(".result-row");
      if (!row || !resultsList.contains(row)) return;
      openDiskResult(row.dataset.resultId);
    }});
    document.querySelector("#refresh-button").addEventListener("click", async () => {{
      if (activeView === "problem") {{
        activeView = "job";
        renderedResultKey = null;
      }}
      await loadResults();
      await loadInbox();
      await loadJobs();
    }});
    queueAllButton.addEventListener("click", () => queueAllJobs());
    uploadForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      await uploadFiles();
    }});

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      if (runMode === "batch") {{
        await queueAllJobs();
        return;
      }}
      await createSingleJob();
    }});

    async function createSingleJob() {{
      runButton.disabled = true;
      queueAllButton.disabled = true;
      try {{
        const payload = await createJobForSource(sourceSelect.value);
        activeJobId = payload.id;
        activeResultId = null;
        activeView = "job";
        setCenterView("queue");
        await loadJobs();
      }} catch (error) {{
        showForegroundProblem(error, {{ context: "launch", statusLabel: "не поставлено" }});
      }} finally {{
        updateRunAvailability();
      }}
    }}

    async function queueAllJobs() {{
      const sources = runMode === "batch"
        ? batchSelectedSources()
        : Array.from(sourceSelect.options).map((option) => option.value).filter(Boolean);
      if (!sources.length) {{
        setLogText(runMode === "batch" ? "Выберите хотя бы один файл для пакетной обработки" : "Inbox пуст");
        return;
      }}
      runButton.disabled = true;
      queueAllButton.disabled = true;
      let firstJobId = null;
      try {{
        for (const source of sources) {{
          const payload = await createJobForSource(source);
          if (!firstJobId) firstJobId = payload.id;
        }}
        if (firstJobId) activeJobId = firstJobId;
        activeResultId = null;
        activeView = "job";
        setCenterView("queue");
        setRunMode("batch");
        await loadJobs();
      }} catch (error) {{
        showForegroundProblem(error, {{ context: "batch", statusLabel: "ошибка пакета" }});
      }} finally {{
        updateRunAvailability();
      }}
    }}

    async function createJobForSource(source) {{
      const data = Object.fromEntries(new FormData(form).entries());
      applySpeakerModeToPayload(data);
      normalizeTimeFields(data);
      data.source = source;
      data.overwrite = form.elements.overwrite.checked;
      const response = await fetch("/api/jobs", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(data),
      }});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "request failed");
      return payload;
    }}

    async function uploadFiles() {{
      const files = Array.from(uploadInput.files || []);
      if (!files.length) {{
        setStatusBadge(uploadStatus, "failed", "выберите файл");
        return;
      }}
      uploadButton.disabled = true;
      setStatusBadge(uploadStatus, "running", "загрузка");
      try {{
        const data = new FormData(uploadForm);
        const response = await fetch("/api/uploads", {{
          method: "POST",
          body: data,
        }});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "upload failed");
        const uploaded = payload.files || [];
        const firstUploaded = uploaded.length ? uploaded[0].name : null;
        uploadInput.value = "";
        setStatusBadge(uploadStatus, "done", `${{uploaded.length}} добавлено`);
        await loadInbox(firstUploaded);
      }} catch (error) {{
        setStatusBadge(uploadStatus, "failed", "ошибка");
        showForegroundProblem(error, {{ context: "upload", statusLabel: "загрузка не удалась" }});
      }} finally {{
        uploadButton.disabled = false;
      }}
    }}

    async function loadInbox(preferredSource = null) {{
      let payload;
      try {{
        const response = await fetch("/api/inbox");
        payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "request failed");
      }} catch (error) {{
        showForegroundProblem(error, {{ context: "inbox", statusLabel: "Inbox недоступен" }});
        return;
      }}
      const files = payload.files || [];
      inboxFiles = files;
      syncBatchSelectionWithFiles(files);
      const previous = preferredSource || sourceSelect.value;
      sourceSelect.innerHTML = files.map((file) => (
        `<option value="${{escapeAttribute(file.name)}}">${{escapeHtml(file.name)}}</option>`
      )).join("");
      fileList.innerHTML = files.length
        ? files.map((file) => (
          renderInboxFile(file)
        )).join("")
        : '<div class="empty">Inbox пуст</div>';
      fileCountNode.textContent = `${{files.length}} файлов`;
      if (files.some((file) => file.name === previous)) {{
        sourceSelect.value = previous;
      }}
      const hasFiles = files.length > 0;
      sourceSelect.disabled = !hasFiles || runMode === "batch";
      syncFileSelection();
      renderBatchChecks();
      updateClipReadout();
      updateBatchSelectionSummary();
      updateRunAvailability();
    }}

    function renderInboxFile(file) {{
      const results = file.results || [];
      const latest = results.length ? results[0] : null;
      const processed = latest
        ? `<span class="processed-tag ${{sourceFreshnessTagClass(latest)}}" data-result-id="${{escapeAttribute(latest.id)}}" title="${{escapeAttribute(sourceFreshnessTitle(latest))}}">${{escapeHtml(inboxResultLabel(results))}}</span>`
        : "";
      const meta = [
        file.duration_label,
        file.format_label,
        file.modified_label,
      ].filter(Boolean);
      const checked = batchSelectedFiles.has(file.name) ? " checked" : "";
      return `<div class="file-item">
        <label class="batch-select" title="Включить в пакет">
          <input class="batch-file-checkbox" type="checkbox" value="${{escapeAttribute(file.name)}}"${{checked}}>
        </label>
        <button class="file-row ${{latest ? "processed" : ""}}" type="button" data-file="${{escapeAttribute(file.name)}}">
          <span class="file-main">
            <span class="file-title">
              <span class="file-name">${{escapeHtml(file.name)}}</span>
              ${{processed}}
            </span>
            <span class="file-subline">${{meta.map((item) => `<span>${{escapeHtml(item)}}</span>`).join("")}}</span>
          </span>
          <span class="file-size">${{escapeHtml(file.size_label)}}</span>
        </button>
      </div>`;
    }}

    function inboxResultLabel(results) {{
      if (!results || !results.length) return "";
      const latest = results[0];
      if (sourceFreshnessStatus(latest) === "changed") return "обновить →";
      if (sourceFreshnessStatus(latest) === "missing") return "нет исходника";
      if (results.length > 1) return `обработан · ${{results.length}} готово →`;
      return latest.kind === "clip" ? "фрагмент готов →" : "обработан · готово →";
    }}

    function syncBatchSelectionWithFiles(files) {{
      const names = files.map((file) => file.name);
      const currentNames = new Set(names);
      if (!batchSelectionReady) {{
        batchSelectedFiles = new Set(names);
        batchKnownFiles = currentNames;
        batchSelectionReady = true;
        return;
      }}
      batchSelectedFiles = new Set(Array.from(batchSelectedFiles).filter((name) => currentNames.has(name)));
      names.forEach((name) => {{
        if (!batchKnownFiles.has(name)) batchSelectedFiles.add(name);
      }});
      batchKnownFiles = currentNames;
    }}

    function updateBatchSelectionFromInput(input) {{
      if (input.checked) {{
        batchSelectedFiles.add(input.value);
      }} else {{
        batchSelectedFiles.delete(input.value);
      }}
      batchSelectionReady = true;
      updateBatchSelectionSummary();
    }}

    function renderBatchChecks() {{
      document.querySelectorAll(".batch-file-checkbox").forEach((input) => {{
        input.checked = batchSelectedFiles.has(input.value);
      }});
    }}

    function batchSelectedSources() {{
      return Array.from(document.querySelectorAll(".batch-file-checkbox:checked"))
        .map((input) => input.value)
        .filter(Boolean);
    }}

    function updateBatchSelectionSummary() {{
      if (!batchSelectionCount) return;
      const selected = batchSelectedSources().length || batchSelectedFiles.size;
      const total = sourceSelect.options.length;
      batchSelectionCount.textContent = `${{selected}} из ${{total}} выбрано`;
      updateRunAvailability();
    }}

    function setJobsHtml(html) {{
      if (renderedJobsListHtml === html) return;
      jobsNode.innerHTML = html;
      renderedJobsListHtml = html;
    }}

    function setResultsHtml(html) {{
      if (renderedResultsListHtml === html) return;
      resultsList.innerHTML = html;
      renderedResultsListHtml = html;
    }}

    async function loadJobs() {{
      let payload;
      try {{
        const response = await fetch("/api/jobs");
        payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "request failed");
      }} catch (error) {{
        showForegroundProblem(error, {{ offline: true, statusLabel: "offline", activeLabel: "offline" }});
        return;
      }}
      const jobs = payload.jobs || [];
      updateQueueSummary(jobs);
      if (!jobs.length) {{
        setJobsHtml('<div class="empty">Нет задач</div>');
        if (activeView !== "result" && activeView !== "problem") {{
          resultDetails.innerHTML = '<div class="empty">Нет выбранной задачи</div>';
          setStatusBadge(resultState, "", "-");
          setLogText("");
          setStatusBadge(activeJobNode, "", "-");
          renderedResultKey = null;
        }}
        return;
      }}
      const previousActiveJobId = activeJobId;
      if (!activeJobId) activeJobId = jobs[0].id;
      const active = jobs.find((job) => job.id === activeJobId) || jobs[0];
      activeJobId = active.id;
      setJobsHtml(jobs.map((job) => renderJob(job)).join(""));
      if (activeView !== "result" && activeView !== "problem") {{
        setStatusBadge(activeJobNode, statusClass(active.status), statusLabel(active.status));
        setStatusBadge(resultState, statusClass(active.status), statusLabel(active.status));
        setLogText(active.log.join(""), {{ job: active }});
        renderResults(active, {{ force: active.id !== previousActiveJobId }});
      }}
    }}

    async function loadResults(preferredResultId = null) {{
      let payload;
      try {{
        const response = await fetch("/api/results");
        payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "request failed");
      }} catch (error) {{
        resultCount.textContent = "нет доступа";
        setResultsHtml('<div class="empty">Не удалось прочитать outputs</div>');
        showForegroundProblem(error, {{ context: "results", statusLabel: "outputs недоступны" }});
        return;
      }}
      diskResults = payload.results || [];
      renderResultList();
      if (preferredResultId) {{
        openDiskResult(preferredResultId);
      }}
    }}

    function renderResultList() {{
      resultCount.textContent = `${{diskResults.length}} готово`;
      if (!diskResults.length) {{
        setResultsHtml('<div class="empty">Готовые результаты появятся здесь после обработки</div>');
        return;
      }}
      setResultsHtml(diskResults.map((result) => (
        `<button class="result-row ${{activeView === "result" && result.id === activeResultId ? "active" : ""}}" type="button" data-result-id="${{escapeAttribute(result.id)}}">
          <span class="badge ${{statusClass(result.status)}}">${{escapeHtml(resultKindLabel(result.kind))}}</span>
          <span class="result-main">
            <span class="result-name" title="${{escapeHtml(result.source_name)}}">${{escapeHtml(result.source_name)}}</span>
            <span class="result-meta-line">${{escapeHtml(resultMeta(result))}}</span>
          </span>
          <span class="badge ${{sourceFreshnessClass(result)}}" title="${{escapeAttribute(sourceFreshnessTitle(result))}}">${{escapeHtml(resultListTrail(result))}}</span>
        </button>`
      )).join(""));
    }}

    function openDiskResult(resultId) {{
      const result = diskResults.find((item) => item.id === resultId);
      if (!result) {{
        showForegroundProblem("result not found", {{ context: "results", statusLabel: "результат не найден" }});
        return;
      }}
      activeView = "result";
      activeResultId = result.id;
      renderedResultKey = null;
      setCenterView("results");
      setStatusBadge(activeJobNode, "done", "готовый");
      setStatusBadge(resultState, statusClass(result.status), statusLabel(result.status));
      setLogText((result.log || []).join(""), {{ forceBottom: true, job: result }});
      renderResultList();
      renderResults(result, {{ force: true }});
    }}

    function setLogText(text, options = {{}}) {{
      const rawText = String(text || "");
      const shouldFollow = options.forceBottom || isLogNearBottom();
      const previousScrollTop = logNode.scrollTop;
      if (logNode.textContent !== rawText) {{
        logNode.textContent = rawText;
      }}
      if (logLineCount) logLineCount.textContent = formatLogLineCount(countLogLines(rawText));
      if (shouldFollow) {{
        logNode.scrollTop = logNode.scrollHeight;
      }} else {{
        logNode.scrollTop = previousScrollTop;
      }}
      renderLogSummary(options.job || null, rawText, options.problem || null);
    }}

    function isLogNearBottom() {{
      if (rawLogDetails && !rawLogDetails.open) return true;
      return logNode.scrollHeight - logNode.scrollTop - logNode.clientHeight < 32;
    }}

    function countLogLines(text) {{
      const trimmed = String(text || "").trim();
      if (!trimmed) return 0;
      return trimmed.split(/\\r?\\n/).filter(Boolean).length;
    }}

    function formatLogLineCount(count) {{
      const value = Number(count || 0);
      const mod10 = value % 10;
      const mod100 = value % 100;
      const word = mod10 === 1 && mod100 !== 11
        ? "строка"
        : [2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)
          ? "строки"
          : "строк";
      return `${{value}} ${{word}}`;
    }}

    function renderLogSummary(job, rawText, problem = null) {{
      if (problem) {{
        logSummaryNode.innerHTML = `
          <div class="log-summary-grid">
            <div class="log-summary-item"><span>Состояние</span><strong>${{escapeHtml(problem.title)}}</strong></div>
            <div class="log-summary-item"><span>Действие</span><strong>см. проверку</strong></div>
            <div class="log-summary-item"><span>Raw</span><strong>${{formatLogLineCount(countLogLines(rawText))}}</strong></div>
          </div>
          <div class="heartbeat">${{escapeHtml(problem.detail)}}</div>`;
        return;
      }}
      const lines = meaningfulLogLinesFromText(rawText);
      if (!job && !lines.length) {{
        logSummaryNode.innerHTML = '<div class="empty">Журнал появится после запуска задачи</div>';
        return;
      }}
      const status = job ? statusLabel(job.status) : "Сообщение";
      const stage = job ? (job.is_disk_result ? "Готовый результат" : currentStage(job).label) : "Система";
      const elapsed = job ? formatDuration(elapsedSeconds(job)) : "-";
      const heartbeat = lines.length ? lines[lines.length - 1] : "Ждём первые строки pipeline.";
      logSummaryNode.innerHTML = `
        <div class="log-summary-grid">
          <div class="log-summary-item"><span>Статус</span><strong>${{escapeHtml(status)}}</strong></div>
          <div class="log-summary-item"><span>Этап</span><strong>${{escapeHtml(stage)}}</strong></div>
          <div class="log-summary-item"><span>Elapsed</span><strong>${{escapeHtml(elapsed)}}</strong></div>
        </div>
        <div class="heartbeat">${{escapeHtml(heartbeat)}}</div>
        ${{renderRecentLogEvents(lines)}}`;
    }}

    function renderRecentLogEvents(lines) {{
      const recent = lines.slice(0, -1).slice(-3);
      if (!recent.length) return "";
      return `<div class="log-events">${{recent.map((line) => `<div class="log-event-line">${{escapeHtml(line)}}</div>`).join("")}}</div>`;
    }}

    function updateQueueSummary(jobs) {{
      const counts = jobs.reduce((acc, job) => {{
        acc[job.status] = (acc[job.status] || 0) + 1;
        return acc;
      }}, {{}});
      const activeCount = (counts.running || 0) + (counts.canceling || 0);
      jobCount.textContent = `${{jobs.length}} всего`;
      queuedCount.textContent = `${{counts.queued || 0}} ожидает`;
      runningCount.textContent = `${{activeCount}} выполняется`;
      doneCount.textContent = `${{counts.done || 0}} готово`;
    }}

    function speakerDraftKey(jobId, speaker) {{
      return `${{jobId}}:${{speaker}}`;
    }}

    function speakerNameValue(job, sample) {{
      const key = speakerDraftKey(job.id, sample.speaker);
      if (speakerNameDrafts.has(key)) return speakerNameDrafts.get(key);
      return sample.name || "";
    }}

    function rememberSpeakerNameInput(input) {{
      if (!input || !input.dataset) return;
      speakerNameDrafts.set(speakerDraftKey(input.dataset.job, input.dataset.speaker), input.value);
    }}

    function clearSpeakerNameDrafts(jobId) {{
      Array.from(speakerNameDrafts.keys()).forEach((key) => {{
        if (key.startsWith(`${{jobId}}:`)) speakerNameDrafts.delete(key);
      }});
    }}

    function captureSpeakerFocus() {{
      const input = document.activeElement;
      if (!input || !input.classList || !input.classList.contains("speaker-name-input")) return null;
      rememberSpeakerNameInput(input);
      return {{
        jobId: input.dataset.job,
        speaker: input.dataset.speaker,
        start: input.selectionStart,
        end: input.selectionEnd,
      }};
    }}

    function restoreSpeakerFocus(state) {{
      if (!state) return;
      const input = Array.from(document.querySelectorAll(".speaker-name-input")).find((candidate) => (
        candidate.dataset.job === state.jobId && candidate.dataset.speaker === state.speaker
      ));
      if (!input) return;
      input.focus();
      if (Number.isInteger(state.start) && Number.isInteger(state.end)) {{
        try {{
          input.setSelectionRange(state.start, state.end);
        }} catch (error) {{
          // Some input types do not support selection ranges.
        }}
      }}
    }}

    function wireSpeakerNameInputs() {{
      document.querySelectorAll(".speaker-name-input").forEach((input) => {{
        input.addEventListener("input", () => rememberSpeakerNameInput(input));
      }});
    }}

    function renderJob(job) {{
      const cls = statusClass(job.status);
      const link = job.markdown_url ? `<a class="job-link" href="${{job.markdown_url}}" target="_blank" rel="noreferrer">Markdown</a>` : "";
      return `<button class="job-row ${{activeView === "job" && job.id === activeJobId ? "active" : ""}}" type="button" data-job="${{job.id}}">
        <span class="badge ${{cls}}">${{statusLabel(job.status)}}</span>
        <span class="job-main">
          <span class="job-name" title="${{escapeHtml(job.source_name)}}">${{escapeHtml(job.source_name)}}</span>
          <span class="job-meta">${{escapeHtml(jobMeta(job))}}</span>
        </span>
        ${{link}}
      </button>`;
    }}

    function renderResults(job, options = {{}}) {{
      const key = resultRenderKey(job);
      if (!options.force && key === renderedResultKey) return;
      const focusState = captureSpeakerFocus();
      renderedResultKey = key;
      if (!job.is_disk_result && job.status !== "done") {{
        resultDetails.innerHTML = `
          <div class="result-meta">${{jobBadges(job)}}${{renderJobManagementActions(job)}}</div>
          ${{renderPendingOrFailedJob(job)}}`;
        wireJobManagementActions(job);
        restoreSpeakerFocus(focusState);
        return;
      }}
      const files = job.files || [];
      const samples = job.speaker_samples || [];
      const fileLinks = renderExportGroups(files);
      const activeTab = resultTab(job.id);
      const previewMode = transcriptPreviewMode(job.id);
      const speakerRows = samples.length
        ? samples.map((sample) => `<div class="speaker-row">
            <span class="badge">${{escapeHtml(sample.label)}}</span>
            <audio controls preload="metadata" src="${{sample.url}}"></audio>
            <input class="speaker-name-input" data-job="${{escapeAttribute(job.id)}}" data-speaker="${{escapeAttribute(sample.speaker)}}" value="${{escapeAttribute(speakerNameValue(job, sample))}}" placeholder="Имя спикера ${{sample.speaker}}">
          </div>`).join("")
        : '<div class="empty">Voice samples пока не найдены</div>';
      const speakerActions = `<div class="actions">
        <button class="btn primary" id="apply-speaker-names" type="button">Применить имена</button>
      </div>`;
      resultDetails.innerHTML = `
        <div class="result-meta">${{jobBadges(job)}}${{renderRerunAction(job)}}${{renderJobManagementActions(job)}}</div>
        ${{renderResultTabs(activeTab)}}
        <section class="result-panel" data-result-panel="overview" ${{activeTab === "overview" ? "" : "hidden"}}>
          ${{renderResultOverview(job, files, samples)}}
        </section>
        <section class="result-panel" data-result-panel="text" ${{activeTab === "text" ? "" : "hidden"}}>
          ${{renderTextPreviewShell(files, previewMode)}}
        </section>
        <section class="result-panel" data-result-panel="speakers" ${{activeTab === "speakers" ? "" : "hidden"}}>
          <div class="speaker-editor">
            ${{speakerRows}}
            ${{speakerActions}}
          </div>
        </section>
        <section class="result-panel" data-result-panel="files" ${{activeTab === "files" ? "" : "hidden"}}>
          ${{fileLinks}}
        </section>`;
      wireResultTabs(job);
      wireTranscriptControls(job, files);
      loadTranscriptPreview(job, files);
      wireRerunAction(job);
      wireJobManagementActions(job);
      const applyButton = document.querySelector("#apply-speaker-names");
      if (applyButton) {{
        applyButton.addEventListener("click", async () => {{
          const names = {{}};
          document.querySelectorAll(".speaker-name-input").forEach((input) => {{
            rememberSpeakerNameInput(input);
            names[input.dataset.speaker] = input.value;
          }});
          applyButton.disabled = true;
          try {{
            const endpoint = job.is_disk_result
              ? `/api/results/${{job.id}}/speaker-names`
              : `/api/jobs/${{job.id}}/speaker-names`;
            const response = await fetch(endpoint, {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{ speaker_names: names }}),
            }});
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "request failed");
            clearSpeakerNameDrafts(job.id);
            clearTranscriptCache(payload.files || []);
            renderedResultKey = null;
            if (payload.is_disk_result) {{
              activeView = "result";
              activeResultId = payload.id;
              const index = diskResults.findIndex((item) => item.id === payload.id);
              if (index >= 0) {{
                diskResults[index] = payload;
              }} else {{
                diskResults.unshift(payload);
              }}
              renderResultList();
              setStatusBadge(activeJobNode, "done", "готовый");
              setStatusBadge(resultState, statusClass(payload.status), statusLabel(payload.status));
              setLogText((payload.log || []).join(""), {{ forceBottom: true, job: payload }});
              renderResults(payload, {{ force: true }});
              await loadInbox();
            }} else {{
              activeJobId = payload.id;
              await loadJobs();
            }}
          }} catch (error) {{
            showForegroundProblem(error, {{ context: "applyNames", statusLabel: "имена не применены" }});
          }} finally {{
            applyButton.disabled = false;
          }}
        }});
      }}
      wireSpeakerNameInputs();
      restoreSpeakerFocus(focusState);
    }}

    function renderRerunAction(job) {{
      if (!job.is_disk_result || sourceFreshnessStatus(job) !== "changed") return "";
      return `<button class="btn primary" id="rerun-result" type="button" title="Пересчитать этот результат в ту же папку">Обновить результат</button>`;
    }}

    function renderJobManagementActions(job) {{
      if (job.is_disk_result) return "";
      if (job.status === "queued") {{
        return `<div class="job-actions"><button class="btn danger small" type="button" data-job-action="cancel" data-job-id="${{escapeAttribute(job.id)}}">Снять с очереди</button></div>`;
      }}
      if (job.status === "running") {{
        return `<div class="job-actions"><button class="btn danger small" type="button" data-job-action="cancel" data-job-id="${{escapeAttribute(job.id)}}">Остановить</button></div>`;
      }}
      if (job.status === "canceling") {{
        return `<div class="job-actions"><button class="btn danger small" type="button" disabled>Останавливается</button></div>`;
      }}
      if (["done", "failed", "canceled"].includes(job.status)) {{
        return `<div class="job-actions"><button class="btn ghost small" type="button" data-job-action="delete" data-job-id="${{escapeAttribute(job.id)}}">Убрать из списка</button></div>`;
      }}
      return "";
    }}

    function wireJobManagementActions(job) {{
      document.querySelectorAll("[data-job-action][data-job-id]").forEach((button) => {{
        button.addEventListener("click", async () => {{
          button.disabled = true;
          const action = button.dataset.jobAction;
          const jobId = button.dataset.jobId;
          try {{
            if (action === "cancel") {{
              await cancelJob(jobId);
            }} else if (action === "delete") {{
              await deleteJob(jobId);
            }}
          }} catch (error) {{
            showForegroundProblem(error, {{ context: action === "cancel" ? "cancel" : "delete" }});
            button.disabled = false;
          }}
        }});
      }});
    }}

    async function cancelJob(jobId) {{
      const response = await fetch(`/api/jobs/${{jobId}}/cancel`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{}}),
      }});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "cancel failed");
      activeView = "job";
      activeJobId = payload.id;
      activeResultId = null;
      renderedResultKey = null;
      setLogText((payload.log || []).join(""), {{ forceBottom: true, job: payload }});
      await loadJobs();
    }}

    async function deleteJob(jobId) {{
      const response = await fetch(`/api/jobs/${{jobId}}`, {{ method: "DELETE" }});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "delete failed");
      if (activeJobId === jobId) activeJobId = null;
      renderedResultKey = null;
      await loadJobs();
    }}

    function wireRerunAction(job) {{
      const button = document.querySelector("#rerun-result");
      if (!button) return;
      button.addEventListener("click", async () => {{
        button.disabled = true;
        setLogText("Ставлю обновление результата в очередь...\\n", {{ forceBottom: true }});
        try {{
          const response = await fetch(`/api/results/${{job.id}}/rerun`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{}}),
          }});
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || "request failed");
          activeView = "job";
          activeJobId = payload.id;
          activeResultId = null;
          renderedResultKey = null;
          setStatusBadge(activeJobNode, statusClass(payload.status), statusLabel(payload.status));
          setStatusBadge(resultState, statusClass(payload.status), statusLabel(payload.status));
          setLogText((payload.log || []).join(""), {{ forceBottom: true, job: payload }});
          await loadJobs();
          await loadResults();
        }} catch (error) {{
          showForegroundProblem(error, {{ context: "rerun", statusLabel: "обновление не запущено" }});
          button.disabled = false;
        }}
      }});
    }}

    function resultTab(jobId) {{
      return resultTabDrafts.get(jobId) || "text";
    }}

    function transcriptPreviewMode(jobId) {{
      return previewModeDrafts.get(jobId) || "timestamps";
    }}

    function renderResultTabs(activeTab) {{
      const tabs = [
        ["overview", "Обзор"],
        ["text", "Текст"],
        ["speakers", "Спикеры"],
        ["files", "Файлы"],
      ];
      return `<div class="result-tabs" role="tablist" aria-label="Разделы результата">
        ${{tabs.map(([key, label]) => `<button class="result-tab ${{activeTab === key ? "active" : ""}}" type="button" role="tab" aria-selected="${{activeTab === key ? "true" : "false"}}" data-result-tab="${{key}}">${{label}}</button>`).join("")}}
      </div>`;
    }}

    function wireResultTabs(job) {{
      document.querySelectorAll(".result-tab").forEach((button) => {{
        button.addEventListener("click", () => {{
          resultTabDrafts.set(job.id, button.dataset.resultTab);
          document.querySelectorAll(".result-tab").forEach((tab) => {{
            const active = tab.dataset.resultTab === button.dataset.resultTab;
            tab.classList.toggle("active", active);
            tab.setAttribute("aria-selected", active ? "true" : "false");
          }});
          document.querySelectorAll(".result-panel").forEach((panel) => {{
            panel.hidden = panel.dataset.resultPanel !== button.dataset.resultTab;
          }});
          if (button.dataset.resultTab === "text") loadTranscriptPreview(job, job.files || []);
        }});
      }});
    }}

    function renderResultOverview(job, files, samples) {{
      const rows = [
        ["Источник", job.source_name || "-"],
        ["ASR", job.asr_engine || "не указан"],
        ["Качество ASR", asrQualityLabel(job)],
        ["Качество спикеров", speakerQualityLabel(job)],
        ["Спикеры", `${{samples.length || job.num_speakers || 0}}`],
        ["Обработано", formatDateTime(job.completed_at)],
        ["Окно", clipLabel(job)],
        ["Распознано", resultDurationLabel(job)],
        ["Файлы", `${{files.length}} экспортов`],
        ["Папка", job.output_dir || "outputs"],
        ["Тип", resultKindLabel(job.kind)],
        ["Исходник", sourceFreshnessLabel(job)],
      ];
      return `<div class="overview-grid">${{rows.map(([label, value]) => `<div class="overview-item"><span>${{escapeHtml(label)}}</span><span title="${{escapeHtml(value)}}">${{escapeHtml(value)}}</span></div>`).join("")}}</div>`;
    }}

    function renderTextPreviewShell(files, mode) {{
      const source = transcriptPreviewFile(files, mode);
      if (!source) {{
        return '<div class="empty">Текстовый экспорт пока не найден</div>';
      }}
      return `<div class="transcript-toolbar">
        <div class="actions">
          <button class="preset-button ${{mode === "timestamps" ? "active" : ""}}" type="button" data-preview-mode="timestamps">С таймкодами</button>
          <button class="preset-button ${{mode === "clean" ? "active" : ""}}" type="button" data-preview-mode="clean">Без таймкодов</button>
        </div>
        <a class="job-link" href="${{source.url}}" target="_blank" rel="noreferrer">Открыть файл</a>
      </div>
      <div class="transcript-preview" id="transcript-preview" data-preview-url="${{escapeAttribute(source.url)}}">Загружаю текст...</div>`;
    }}

    function wireTranscriptControls(job, files) {{
      document.querySelectorAll("[data-preview-mode]").forEach((button) => {{
        button.addEventListener("click", () => {{
          previewModeDrafts.set(job.id, button.dataset.previewMode);
          const panel = document.querySelector('[data-result-panel="text"]');
          if (panel) panel.innerHTML = renderTextPreviewShell(files, button.dataset.previewMode);
          wireTranscriptControls(job, files);
          loadTranscriptPreview(job, files);
        }});
      }});
    }}

    async function loadTranscriptPreview(job, files) {{
      if (resultTab(job.id) !== "text") return;
      const container = document.querySelector("#transcript-preview");
      if (!container) return;
      const url = container.dataset.previewUrl;
      if (!url) return;
      try {{
        let text = transcriptCache.get(url);
        if (!text) {{
          const response = await fetch(url);
          if (!response.ok) throw new Error(`preview fetch failed: ${{response.status}}`);
          text = await response.text();
          transcriptCache.set(url, text);
        }}
        container.innerHTML = renderTranscriptMarkdown(text);
      }} catch (error) {{
        container.innerHTML = `<div class="empty">${{escapeHtml(String(error))}}</div>`;
      }}
    }}

    function transcriptPreviewFile(files, mode) {{
      const preferredKeys = mode === "clean"
        ? ["edited_text", "clean_markdown", "clean_text", "edited_markdown", "clean_timestamps_markdown", "timeline_text", "detailed_markdown"]
        : ["edited_markdown", "clean_timestamps_markdown", "timeline_text", "detailed_markdown", "clean_markdown", "clean_text"];
      for (const key of preferredKeys) {{
        const file = files.find((item) => item.key === key);
        if (file) return file;
      }}
      return files[0] || null;
    }}

    function renderTranscriptMarkdown(text) {{
      const lines = String(text || "").split(/\\r?\\n/);
      const turns = [];
      let current = null;
      for (const rawLine of lines) {{
        const line = rawLine.trim();
        if (!line) continue;
        if (line.startsWith("# ")) continue;
        if (line.startsWith("> ")) continue;
        if (line.startsWith("## ")) {{
          if (current) turns.push(current);
          current = {{ speaker: line.replace(/^##\\s+/, ""), lines: [] }};
          continue;
        }}
        if (!current) current = {{ speaker: "Текст", lines: [] }};
        current.lines.push(line);
      }}
      if (current) turns.push(current);
      if (!turns.length) return '<div class="empty">Текст пуст</div>';
      return turns.slice(0, 160).map((turn) => `<article class="transcript-turn">
        <div class="transcript-speaker">${{escapeHtml(turn.speaker)}}</div>
        ${{turn.lines.map(renderTranscriptLine).join("")}}
      </article>`).join("") + (turns.length > 160 ? '<div class="empty">Показан первый фрагмент. Полный текст откройте файлом экспорта.</div>' : "");
    }}

    function renderTranscriptLine(line) {{
      const match = line.match(/^`([^`]+)`\\s*(.*)$/);
      if (match) {{
        return `<p class="transcript-line"><span class="timecode">${{escapeHtml(match[1])}}</span>${{escapeHtml(match[2])}}</p>`;
      }}
      return `<p class="transcript-line">${{escapeHtml(line.replace(/^[-*]\\s+/, ""))}}</p>`;
    }}

    function clearTranscriptCache(files) {{
      (files || []).forEach((file) => {{
        if (file.url) transcriptCache.delete(file.url);
      }});
    }}

    function resultRenderKey(job) {{
      if (job.status !== "done") {{
        const elapsedBucket = Math.floor(elapsedSeconds(job) / 2);
        return `${{job.id}}:${{job.status}}:${{job.returncode ?? ""}}:${{currentStageIndex(job)}}:${{meaningfulLogLines(job).length}}:${{elapsedBucket}}`;
      }}
      const files = (job.files || [])
        .map((file) => `${{file.key}}=${{file.url}}:${{file.label}}`)
        .join("|");
      const samples = (job.speaker_samples || [])
        .map((sample) => `${{sample.speaker}}=${{sample.url}}:${{sample.label}}:${{sample.name || ""}}`)
        .join("|");
      return `${{job.id}}:${{job.status}}:${{jobMeta(job)}}:${{job.source_status || ""}}:${{qualityRenderKey(job)}}:${{files}}:${{samples}}`;
    }}

    function jobBadges(job) {{
      const badges = [
        `<span class="badge ${{statusClass(job.status)}}">${{statusLabel(job.status)}}</span>`,
        `<span class="badge">${{escapeHtml(clipLabel(job))}}</span>`,
        `<span class="badge">${{escapeHtml(speakerLabel(job))}}</span>`,
        `<span class="badge">${{escapeHtml(job.output_dir || "outputs")}}</span>`,
      ];
      const sourceBadge = sourceFreshnessBadge(job);
      if (sourceBadge) badges.push(sourceBadge);
      return badges.join("");
    }}

    function jobMeta(job) {{
      if (job.status === "running") {{
        return `${{currentStage(job).label}} · ${{formatDuration(elapsedSeconds(job))}} · ${{job.device || "auto"}}`;
      }}
      if (job.status === "canceling") {{
        return `останавливается · ${{formatDuration(elapsedSeconds(job))}} · ${{job.device || "auto"}}`;
      }}
      if (job.status === "canceled") {{
        return `отменено · ${{formatDuration(elapsedSeconds(job))}} · ${{job.device || "auto"}}`;
      }}
      if (job.status === "queued") {{
        return `ожидает · ${{formatDuration(elapsedSeconds(job))}} · ${{job.device || "auto"}}`;
      }}
      if (job.status === "failed") {{
        return `ошибка · ${{diagnoseProblem(jobLogText(job)).title}}`;
      }}
      return `${{clipLabel(job)}} · ${{speakerLabel(job)}} · ${{job.device || "auto"}}`;
    }}

    function resultMeta(result) {{
      const parts = [
        resultKindLabel(result.kind),
        speakerLabel(result),
        result.asr_engine || "ASR",
        result.output_dir || "outputs",
        sourceFreshnessInline(result),
      ];
      return parts.filter(Boolean).join(" · ");
    }}

    function resultListTrail(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "changed") return "обновить";
      if (status === "missing") return "нет исходника";
      return formatDateTime(result.completed_at);
    }}

    function sourceFreshnessStatus(result) {{
      if (!result) return "unknown";
      if (result.source_changed) return "changed";
      if (result.source_missing) return "missing";
      return result.source_status || "unknown";
    }}

    function sourceFreshnessLabel(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "fresh") return "исходник свежий";
      if (status === "changed") return "исходник изменился после обработки";
      if (status === "missing") return "исходник не найден";
      return result?.source_status_label || "исходник не проверен";
    }}

    function sourceFreshnessInline(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "changed" || status === "missing") return sourceFreshnessLabel(result);
      return "";
    }}

    function sourceFreshnessBadge(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "fresh" || status === "unknown") return "";
      return `<span class="badge ${{sourceFreshnessClass(result)}}" title="${{escapeAttribute(sourceFreshnessTitle(result))}}">${{escapeHtml(sourceFreshnessLabel(result))}}</span>`;
    }}

    function sourceFreshnessClass(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "changed") return "done";
      if (status === "missing") return "failed";
      return "";
    }}

    function sourceFreshnessTagClass(result) {{
      const status = sourceFreshnessStatus(result);
      if (status === "changed") return "changed";
      if (status === "missing") return "missing";
      return "";
    }}

    function sourceFreshnessTitle(result) {{
      const label = sourceFreshnessLabel(result);
      const path = result?.source_path ? ` · ${{result.source_path}}` : "";
      return `${{label}}${{path}}`;
    }}

    function resultDurationLabel(job) {{
      if (job.recording_duration !== null && job.recording_duration !== undefined) {{
        return formatDuration(job.recording_duration);
      }}
      if (job.duration !== null && job.duration !== undefined) {{
        return formatDuration(job.duration);
      }}
      return "-";
    }}

    function resultKindLabel(kind) {{
      return kind === "clip" ? "фрагмент" : "полный";
    }}

    function asrQualityLabel(job) {{
      const quality = job?.asr_quality;
      if (!quality) return "-";
      const status = quality.status === "warning"
        ? "проверить"
        : quality.status === "ok"
          ? "норма"
          : "мало данных";
      const punct = metricValue(quality.punctuation_per_100_words);
      const caps = metricValue(quality.sentence_capitalized_percent);
      return `${{status}} · ${{punct}}/100 · ${{caps}}%`;
    }}

    function speakerQualityLabel(job) {{
      const quality = job?.speaker_quality;
      if (!quality) return "-";
      const status = quality.status === "warning"
        ? "проверить"
        : quality.status === "ok"
          ? "норма"
          : "мало данных";
      const shortTurns = metricValue(quality.short_turn_percent);
      const switches = metricValue(quality.switches_per_minute);
      const islands = Number.isFinite(Number(quality.speaker_island_count))
        ? Number(quality.speaker_island_count)
        : "-";
      return `${{status}} · коротких ${{shortTurns}}% · смен ${{switches}}/мин · островков ${{islands}}`;
    }}

    function qualityRenderKey(job) {{
      const asrQuality = job?.asr_quality
        ? `${{job.asr_quality.status}}:${{job.asr_quality.punctuation_per_100_words}}:${{job.asr_quality.sentence_capitalized_percent}}`
        : "";
      const speakerQuality = job?.speaker_quality
        ? `${{job.speaker_quality.status}}:${{job.speaker_quality.short_turn_percent}}:${{job.speaker_quality.switches_per_minute}}:${{job.speaker_quality.speaker_island_count}}`
        : "";
      return `${{asrQuality}}|${{speakerQuality}}`;
    }}

    function metricValue(value) {{
      return Number.isFinite(Number(value)) ? Number(value).toFixed(1) : "-";
    }}

    function renderExportGroups(files) {{
      if (!files.length) return '<div class="empty">Файлы результата пока не найдены</div>';
      const groups = [
        {{ title: "Основной результат", keys: ["edited_markdown", "edited_text"] }},
        {{ title: "Raw / проверка", keys: ["detailed_markdown"] }},
        {{ title: "Чистые raw-версии", keys: ["clean_timestamps_markdown", "clean_markdown"] }},
        {{ title: "Текстовые версии", keys: ["clean_text", "timeline_text"] }},
        {{ title: "Диагностика", keys: ["repair_json"] }},
      ];
      const byKey = new Map(files.map((file) => [file.key, file]));
      const rendered = groups.map((group) => {{
        const links = group.keys.map((key) => byKey.get(key)).filter(Boolean);
        if (!links.length) return "";
        return `<div class="export-group">
          <div class="export-group-title">${{escapeHtml(group.title)}}</div>
          <div class="link-list">${{links.map(renderExportLink).join("")}}</div>
        </div>`;
      }}).filter(Boolean).join("");
      const leftovers = files.filter((file) => !groups.some((group) => group.keys.includes(file.key)));
      const diagnostics = leftovers.length
        ? `<div class="export-group">
            <div class="export-group-title">Диагностика</div>
            <div class="link-list">${{leftovers.map(renderExportLink).join("")}}</div>
          </div>`
        : "";
      return `<div class="export-groups">${{rendered}}${{diagnostics}}</div>`;
    }}

    function renderExportLink(file) {{
      return `<a class="link-chip" href="${{file.url}}" target="_blank" rel="noreferrer">
        <span>${{escapeHtml(file.label)}}</span>
        <small>${{escapeHtml(exportHint(file.key))}}</small>
      </a>`;
    }}

    function exportHint(key) {{
      const hints = {{
        edited_markdown: "улучшенный Markdown с таймкодами и спикерами",
        edited_text: "улучшенный TXT без таймкодов",
        detailed_markdown: "общий файл с таймкодами и спикерами",
        clean_timestamps_markdown: "чистый Markdown с таймкодами",
        clean_markdown: "чистый Markdown без таймкодов",
        clean_text: "TXT без таймкодов",
        timeline_text: "TXT с таймкодами",
        repair_json: "служебная карта подозрительных фрагментов",
      }};
      return hints[key] || "служебный файл";
    }}

    function renderPendingOrFailedJob(job) {{
      if (job.status === "failed") {{
        return renderDiagnosticBlock(diagnoseProblem(jobLogText(job), {{ job }}));
      }}
      if (job.status === "canceled") {{
        return `<div class="progress-block" aria-live="polite">
          <div class="stage-top">
            <span class="badge canceled">Отменено</span>
            <span class="badge">${{escapeHtml(formatDuration(elapsedSeconds(job)))}}</span>
          </div>
          <p>Задача остановлена пользователем. Уже созданные промежуточные файлы могут остаться в cache/outputs, но новая обработка проверит их по metadata.</p>
          <div class="heartbeat">Последний сигнал: ${{escapeHtml(lastMeaningfulLog(job))}}</div>
        </div>`;
      }}
      if (job.status === "canceling") {{
        return renderProgressBlock(job, "Останавливаю дочерний процесс. Это может занять несколько секунд, если ASR/diarization завершает текущую операцию.");
      }}
      if (job.status === "running") {{
        return renderProgressBlock(job, runningDetail(job));
      }}
      return renderProgressBlock(job, "Задача ожидает очереди. Можно открыть другую задачу — эта не потеряется.");
    }}

    function renderProgressBlock(job, detail) {{
      const stage = currentStage(job);
      const started = job.created_at ? formatTime(job.created_at) : "сейчас";
      const heartbeat = lastMeaningfulLog(job);
      return `<div class="progress-block" aria-live="polite">
        <div class="stage-top">
          <span class="badge ${{statusClass(job.status)}}">${{escapeHtml(stage.label)}}</span>
          <span class="badge">${{escapeHtml(formatDuration(elapsedSeconds(job)))}} · старт ${{escapeHtml(started)}}</span>
        </div>
        ${{renderStageList(job)}}
        <p>${{escapeHtml(detail)}}</p>
        <div class="heartbeat">Последний сигнал: ${{escapeHtml(heartbeat)}}</div>
      </div>`;
    }}

    function renderStageList(job) {{
      const activeIndex = currentStageIndex(job);
      return `<div class="stage-list" aria-label="Этапы pipeline">${{pipelineStages.map((stage, index) => {{
        const state = index < activeIndex ? "done" : index === activeIndex ? "active" : "";
        return `<div class="stage-step ${{state}}">
          <div class="stage-bar"><span></span></div>
          <span>${{escapeHtml(stage.label)}}</span>
        </div>`;
      }}).join("")}}</div>`;
    }}

    function currentStage(job) {{
      return pipelineStages[currentStageIndex(job)] || pipelineStages[0];
    }}

    function currentStageIndex(job) {{
      if (job.status === "done") return pipelineStages.length - 1;
      if (job.status === "canceled") return 0;
      const text = meaningfulLogLines(job).join("\\n").toLowerCase();
      if (/manifest:|clean txt:|clean markdown:|markdown:|done:|export/.test(text)) return 4;
      if (/diarization json:|speaker sample|speaker names|склейк|merge|align|format/.test(text)) return 3;
      if (/diarization|pyannote|vad|speaker-diarization|speaker separation|matplotlib|font cache/.test(text)) return 2;
      if (/asr json:|asr engine:|transcrib|recogniz|gigastt|whisper/.test(text)) return 1;
      return 0;
    }}

    function runningDetail(job) {{
      const stage = currentStage(job);
      if (stage && stage.key === "diarization") {{
        return "Идёт разделение по спикерам. На первом запуске pyannote может несколько минут загружать модель и готовить локальный cache.";
      }}
      if (stage && stage.key === "asr") {{
        return "Идёт распознавание речи. Для длинных файлов ASR работает по частям и пишет промежуточные JSON.";
      }}
      return "Задача выполняется. Результаты и спикеры появятся здесь после завершения.";
    }}

    function elapsedSeconds(job) {{
      if (!job.created_at) return 0;
      const end = job.completed_at || Date.now() / 1000;
      return Math.max(0, Math.round(end - job.created_at));
    }}

    function formatDuration(seconds) {{
      const total = Math.max(0, Math.round(seconds || 0));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const secs = total % 60;
      if (hours) return `${{hours}}:${{String(minutes).padStart(2, "0")}}:${{String(secs).padStart(2, "0")}}`;
      return `${{minutes}}:${{String(secs).padStart(2, "0")}}`;
    }}

    function formatTime(epochSeconds) {{
      try {{
        return new Date(epochSeconds * 1000).toLocaleTimeString("ru-RU", {{
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }});
      }} catch (error) {{
        return "сейчас";
      }}
    }}

    function formatDateTime(epochSeconds) {{
      if (!epochSeconds) return "-";
      try {{
        return new Date(epochSeconds * 1000).toLocaleString("ru-RU", {{
          day: "2-digit",
          month: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }});
      }} catch (error) {{
        return "-";
      }}
    }}

    function jobLogText(job) {{
      return (job.log || []).map((line) => String(line)).join("\\n");
    }}

    function meaningfulLogLinesFromText(rawText) {{
      return String(rawText || "")
        .split(/\\r?\\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .filter((line) => !line.startsWith("$ "));
    }}

    function meaningfulLogLines(job) {{
      return meaningfulLogLinesFromText(jobLogText(job));
    }}

    function lastMeaningfulLog(job) {{
      const lines = meaningfulLogLines(job);
      return lines.length ? lines[lines.length - 1] : "Команда запущена, ждём первый лог pipeline.";
    }}

    function showForegroundProblem(error, options = {{}}) {{
      const rawText = String(error?.message || error || "unknown error");
      const problem = diagnoseProblem(rawText, options);
      const statusText = options.statusLabel || "ошибка";
      activeView = "problem";
      setStatusBadge(resultState, "failed", statusText);
      setStatusBadge(activeJobNode, "failed", options.activeLabel || statusText);
      resultDetails.innerHTML = renderDiagnosticBlock(problem);
      setLogText(problemLogText(problem, rawText), {{ forceBottom: true, problem }});
      renderedResultKey = `foreground-error:${{options.context || ""}}:${{rawText}}`;
    }}

    function problemLogText(problem, rawText) {{
      const actions = (problem.actions || []).map((action) => `- ${{action}}`).join("\\n");
      return `${{problem.title}}\\n${{problem.detail}}\\n\\nЧто сделать:\\n${{actions}}\\n\\nТехническая деталь:\\n${{rawText}}`;
    }}

    function diagnoseProblem(rawText, options = {{}}) {{
      const text = String(rawText || "").toLowerCase();
      const context = String(options.context || "");
      if (options.offline) {{
        return {{
          title: "Сервер не отвечает",
          detail: "Интерфейс не смог получить список задач. Обычно это значит, что локальный сервер остановлен или перезапускается.",
          actions: [
            "Проверьте окно Terminal с сервером или запустите `Запустить Диктум.command`.",
            "Если порт занят старым процессом, используйте `Остановить Диктум.command`, затем запустите снова.",
            "После запуска обновите страницу браузера.",
          ],
        }};
      }}
      if (/unsupported file type|invalid upload filename|upload filename|no supported files uploaded|upload must use multipart|no supported files/.test(text)) {{
        return {{
          title: "Файл не загрузился",
          detail: "Файл не прошёл проверку загрузки. Чаще всего это неподдержанный формат или пустой выбор файлов.",
          actions: [
            "Выберите обычный аудиофайл: `.m4a`, `.mp3`, `.wav`, `.flac`, `.ogg` или видеофайл `.mp4/.mov/.mkv/.webm`.",
            "Если файл уже есть в `Inbox`, выберите его из списка и не загружайте повторно.",
            "Если формат нестандартный, сначала экспортируйте запись в `.m4a` или `.wav`.",
          ],
        }};
      }}
      if (/output_dir must stay inside outputs|output.*inside outputs|outside outputs/.test(text)) {{
        return {{
          title: "Папка результатов вне outputs",
          detail: "Диктум хранит результаты только внутри локальной папки `outputs/`, чтобы не писать файлы в неожиданное место.",
          actions: [
            "Верните поле `Результаты` к значению `outputs/pipeline` или другой подпапке внутри `outputs/`.",
            "Не указывайте абсолютный путь к личным папкам или внешним дискам в этом поле.",
            "После исправления повторите запуск с теми же настройками.",
          ],
        }};
      }}
      if (/time values must be non-negative|could not convert string to float|invalid literal|incorrect time|некорректное время/.test(text)) {{
        return {{
          title: "Проверьте время фрагмента",
          detail: "Старт и длительность должны быть положительным временем в секундах или формате `мм:сс` / `чч:мм:сс`.",
          actions: [
            "Нажмите один из пресетов тест-фрагмента: `0:30`, `2:00` или `5:00`.",
            "Проверьте, что фрагмент не выходит за пределы длительности записи.",
            "Для полного файла очистите поля `Старт` и `Длительность` или выберите режим `Один файл`.",
          ],
        }};
      }}
      if (/speaker_mode|num_speakers|min_speakers|max_speakers|speaker.*required|speakers.*required/.test(text)) {{
        return {{
          title: "Проверьте настройки спикеров",
          detail: "Режим спикеров и числовые поля сейчас не согласованы: для точного режима нужно число, для диапазона — минимум или максимум.",
          actions: [
            "Выберите `Auto по файлу`, если не уверены в количестве участников.",
            "Для режима `Точно` заполните только поле `Спикеров`.",
            "Для режима `Диапазон` заполните `Мин.` и/или `Макс.`, где минимум не больше максимума.",
          ],
        }};
      }}
      if (/audio file too long|maximum supported|7200s|file too long/.test(text)) {{
        return {{
          title: "Файл длиннее лимита ASR-движка",
          detail: "Движок отказался брать файл целиком. Для длинных записей нужно запускать chunking или обработку по фрагментам.",
          actions: [
            "Запустите файл через режим длинной обработки/chunking, если он доступен.",
            "Для быстрой проверки укажите тестовый фрагмент, например 120 секунд.",
            "Если ошибка повторяется, переключите ASR-движок или уменьшите длительность фрагмента.",
          ],
        }};
      }}
      if (context === "upload") {{
        return {{
          title: "Загрузка не удалась",
          detail: "Интерфейс не смог сохранить выбранный файл в `Inbox/`.",
          actions: [
            "Проверьте, что файл доступен на этом Mac и не удалён после выбора.",
            "Попробуйте положить файл в `Inbox/` вручную и нажать `Обновить`.",
            "Если ошибка повторяется, проверьте права на папку проекта.",
          ],
        }};
      }}
      if (context === "inbox") {{
        return {{
          title: "Не удалось прочитать Inbox",
          detail: "Интерфейс не смог обновить список локальных аудиофайлов.",
          actions: [
            "Проверьте, что папка `Inbox/` существует внутри проекта.",
            "Запустите `Проверить Диктум.command`, если папка или права выглядят сломанными.",
            "После исправления нажмите `Обновить` в интерфейсе.",
          ],
        }};
      }}
      if (context === "results") {{
        return {{
          title: "Не удалось прочитать готовые результаты",
          detail: "Интерфейс не смог открыть библиотеку `outputs/` или выбранный manifest результата.",
          actions: [
            "Нажмите `Обновить`, чтобы перечитать `outputs/`.",
            "Проверьте, что папка `outputs/` не была удалена или перемещена.",
            "Если результат частично удалён, запустите обработку заново или восстановите manifest/export-файлы.",
          ],
        }};
      }}
      if (context === "launch" || context === "batch") {{
        return {{
          title: "Не удалось поставить задачу в очередь",
          detail: "Задача не была запущена, потому что настройки формы не прошли проверку или сервер отказал запросу.",
          actions: [
            "Проверьте выбранный файл, режим фрагмента, число спикеров и папку результатов.",
            "Если это пакетный запуск, убедитесь, что выбран хотя бы один файл.",
            "После исправления нажмите запуск ещё раз — текущая форма не сброшена.",
          ],
        }};
      }}
      if (context === "applyNames") {{
        return {{
          title: "Не удалось применить имена спикеров",
          detail: "Перерендер экспорта с новыми именами не завершился. ASR и диаризация не должны запускаться заново, но existing artifacts должны быть доступны.",
          actions: [
            "Проверьте, что исходный аудиофайл всё ещё лежит в `Inbox/`.",
            "Проверьте, что result artifacts не удалены из `outputs/`.",
            "Повторите действие после `Обновить`; введённые имена останутся в полях до перерисовки.",
          ],
        }};
      }}
      if (context === "rerun") {{
        return {{
          title: "Не удалось обновить результат",
          detail: "Интерфейс не смог поставить пересчёт результата в очередь.",
          actions: [
            "Проверьте, что исходный файл результата существует и находится внутри проекта.",
            "Проверьте, что папка результата всё ещё находится внутри `outputs/`.",
            "Если source был переименован, выберите файл из Inbox и запустите новую задачу.",
          ],
        }};
      }}
      if (context === "cancel" || context === "delete") {{
        return {{
          title: context === "cancel" ? "Не удалось остановить задачу" : "Не удалось убрать задачу",
          detail: "Очередь не приняла действие управления задачей.",
          actions: [
            "Нажмите `Обновить`, чтобы получить актуальное состояние очереди.",
            "Running-задачу сначала нужно остановить, а уже потом убирать из списка.",
            "Если процесс завис, используйте `Остановить Диктум.command`.",
          ],
        }};
      }}
      if (/hf_token|hugging face token|token.*missing|missing.*token|no token/.test(text)) {{
        return {{
          title: "Не найден Hugging Face token",
          detail: "Диаризация pyannote требует локальный `HF_TOKEN` в `.env`. Без него ASR может пройти, но разделение по спикерам упадёт.",
          actions: [
            "Запустите `Настроить Диктум.command` и добавьте read-only HF token.",
            "Проверьте `.env`: там должна быть строка `HF_TOKEN=...` без вывода токена в чат.",
            "После исправления повторите задачу с теми же настройками.",
          ],
        }};
      }}
      if (/gatedrepo|restricted|accept.*condition|access to model|403|401|pyannote/.test(text)) {{
        return {{
          title: "Нет доступа к модели pyannote",
          detail: "Токен найден, но аккаунт не имеет доступа к нужной модели pyannote или не принял условия на Hugging Face.",
          actions: [
            "Откройте страницу модели pyannote и примите условия доступа для используемого аккаунта.",
            "Убедитесь, что в `.env` лежит токен именно этого аккаунта.",
            "Запустите проверку `voice-recognizer check-pyannote-access` или `Проверить Диктум.command`.",
          ],
        }};
      }}
      if (/unsupported device|invalid value:.*device|device.*unsupported|unknown device/.test(text)) {{
        return {{
          title: "Неподдерживаемое устройство обработки",
          detail: "Pipeline получил значение device, которое не поддерживается текущим backend.",
          actions: [
            "Выберите `auto`, `mps` или `cpu` в поле `Устройство`.",
            "Если задача падала на MPS, повторите с `cpu`.",
            "После смены устройства повторите задачу с теми же настройками.",
          ],
        }};
      }}
      if (/mps|metal|mps backend|mps device/.test(text)) {{
        return {{
          title: "Сбой на Apple Silicon/MPS",
          detail: "Модель или один из шагов pipeline не смог выполниться на MPS. Часто помогает повтор на CPU.",
          actions: [
            "Повторите задачу с устройством `cpu`.",
            "Если CPU проходит, оставьте MPS как известный риск для этой модели/записи.",
            "Сохраните лог ошибки для отдельной оптимизации backend.",
          ],
        }};
      }}
      if (/source not found|not found in inbox|no such file|файл.*не найден/.test(text)) {{
        return {{
          title: "Исходный файл не найден",
          detail: "Запись исчезла из Inbox или была переименована после постановки задачи.",
          actions: [
            "Нажмите `Обновить` в Inbox или перезапустите страницу.",
            "Проверьте, что файл всё ещё лежит в `Inbox/`.",
            "Если файл был переименован, выберите его заново и поставьте новую задачу.",
          ],
        }};
      }}
      if (/ffmpeg|ffprobe/.test(text) && /not found|no such file|failed|error/.test(text)) {{
        return {{
          title: "Проблема с ffmpeg/ffprobe",
          detail: "Аудио не удалось подготовить. Обычно это означает, что ffmpeg не установлен или файл повреждён.",
          actions: [
            "Запустите `Настроить Диктум.command` и разрешите установку ffmpeg.",
            "Проверьте файл командой `Проверить Диктум.command`.",
            "Попробуйте другой аудиофайл, если проблема только у одной записи.",
          ],
        }};
      }}
      if (/gigastt|gigaam|onnx|vocab|model/.test(text) && /missing|not found|no such file|failed|error/.test(text)) {{
        return {{
          title: "Проблема с моделью GigaSTT/GigaAM",
          detail: "ASR-движок не нашёл бинарник или файлы модели.",
          actions: [
            "Запустите `Настроить Диктум.command` и разрешите setup GigaSTT.",
            "Проверьте наличие файлов модели через `Проверить Диктум.command`.",
            "Временно переключите ASR-движок, если нужно срочно обработать запись.",
          ],
        }};
      }}
      return {{
        title: "Задача завершилась с ошибкой",
        detail: "Pipeline остановился. Ниже указаны безопасные следующие шаги; технические подробности остаются в журнале.",
        actions: [
          "Скопируйте последние строки журнала для диагностики.",
          "Запустите `Проверить Диктум.command`, чтобы проверить окружение и модели.",
          "Попробуйте короткий тест-фрагмент или повтор на CPU, если ошибка связана с ресурсами.",
        ],
      }};
    }}

    function renderDiagnosticBlock(problem) {{
      return `<div class="diagnostic-block" role="alert">
        <h3>${{escapeHtml(problem.title)}}</h3>
        <p>${{escapeHtml(problem.detail)}}</p>
        <ul class="next-actions">${{problem.actions.map((action) => `<li>${{escapeHtml(action)}}</li>`).join("")}}</ul>
      </div>`;
    }}

    function clipLabel(job) {{
      if (job.duration !== null && job.duration !== undefined) {{
        return `${{job.start || 0}}s + ${{job.duration}}s`;
      }}
      return "полный файл";
    }}

    function speakerLabel(job) {{
      if (job.num_speakers) return `${{job.num_speakers}} спик.`;
      if (job.min_speakers || job.max_speakers) {{
        return `${{job.min_speakers || "?"}}-${{job.max_speakers || "?"}} спик.`;
      }}
      return job.speaker_mode === "auto" ? "auto по файлу" : "спикеры auto";
    }}

    function statusClass(status) {{
      if (status === "done") return "done";
      if (status === "partial") return "running";
      if (status === "failed") return "failed";
      if (status === "running") return "running";
      if (status === "canceling") return "canceling";
      if (status === "canceled") return "canceled";
      return "queued";
    }}

    function statusLabel(status) {{
      if (status === "done") return "Готово";
      if (status === "partial") return "Частично";
      if (status === "failed") return "Ошибка";
      if (status === "running") return "Выполняется";
      if (status === "canceling") return "Остановка";
      if (status === "canceled") return "Отменено";
      return "Ожидает";
    }}

    function setStatusBadge(node, cls, text) {{
      node.className = `badge ${{cls || ""}}`.trim();
      node.textContent = text;
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function escapeAttribute(value) {{
      return escapeHtml(value).replaceAll("'", "&#039;");
    }}

    setSpeakerMode("auto");
    setRunMode("single");
    setCenterView("queue");
    syncFileSelection();
    loadResults();
    loadInbox();
    loadJobs();
    setInterval(loadJobs, 2000);
  </script>
</body>
</html>"""

    def _serve_output(self, path: str, *, head_only: bool = False) -> None:
        relative = Path(unquote(path).lstrip("/"))
        target = (self.web_config.root / relative).resolve()
        try:
            target.relative_to((self.web_config.root / "outputs").resolve())
        except ValueError:
            self._send_json({"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        content_type = _content_type(target)
        file_size = target.stat().st_size
        byte_range = _parse_range_header(self.headers.get("Range"), file_size)
        if byte_range is None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if not head_only:
                with target.open("rb") as file:
                    _copy_file_range(file, self.wfile)
            return

        start, end = byte_range
        length = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if not head_only:
            with target.open("rb") as file:
                file.seek(start)
                _copy_file_range(file, self.wfile, length)

    def _content_length(self) -> int:
        raw = self.headers.get("Content-Length")
        if raw is None:
            return 0
        try:
            length = int(raw)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length < 0:
            raise ValueError("invalid Content-Length")
        return length

    def _read_json_body(self) -> dict[str, object]:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        length = self._content_length()
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError("request body is too large")
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("invalid payload")
        return payload

    def _save_uploads(self) -> list[dict[str, object]]:
        content_type = self.headers.get("Content-Type") or ""
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("upload must use multipart/form-data")
        length = self._content_length()
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("upload exceeds the maximum allowed size")
        self.web_config.inbox.mkdir(parents=True, exist_ok=True)
        created_targets: list[Path] = []

        def open_target(part: FilePart):
            # Reject unsupported/oversized names before opening anything on disk.
            target = _unique_inbox_path(self.web_config.inbox, part.filename)
            handle = target.open("wb")
            created_targets.append(target)

            def finalize(size: int) -> dict[str, object]:
                return _inbox_file_payload(target)

            return handle, finalize

        try:
            saved = stream_form_files(
                self.rfile,
                content_type=content_type,
                content_length=length,
                max_bytes=MAX_UPLOAD_BYTES,
                field_name="files",
                open_target=open_target,
            )
        except (MultipartError, OSError, ValueError) as error:
            for target in created_targets:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ValueError(str(error)) from error
        if not saved:
            raise ValueError("no supported files uploaded")
        return saved

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK, *, head_only: bool = False) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        head_only: bool = False,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)


def _create_job(
    *,
    source: Path,
    output_dir: Path,
    start: float | None,
    duration: float | None,
    device: str,
    asr_engine: str,
    speaker_mode: str,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
    speaker_names: str,
    overwrite: bool,
    root: Path,
) -> Job:
    suffix = _clip_suffix(start, duration)
    markdown_path = output_dir / f"{safe_stem(source)}{suffix}.transcript.md"
    manifest_path = output_dir / f"{safe_stem(source)}{suffix}.manifest.json"
    source_arg = _cli_path(root, source)
    output_dir_arg = _cli_path(root, output_dir)
    command = [
        sys.executable,
        "-u",
        "-m",
        "voice_recognizer.cli",
        "process",
        source_arg,
        "--output-dir",
        output_dir_arg,
        "--asr-engine",
        asr_engine,
        "--device",
        device,
    ]
    if start is not None:
        command.extend(["--start", str(start)])
    if duration is not None:
        command.extend(["--duration", str(duration)])
    if num_speakers is not None:
        command.extend(["--num-speakers", str(num_speakers)])
    if min_speakers is not None:
        command.extend(["--min-speakers", str(min_speakers)])
    if max_speakers is not None:
        command.extend(["--max-speakers", str(max_speakers)])
    if speaker_names.strip():
        command.extend(["--speaker-names", speaker_names.strip()])
    if overwrite:
        command.append("--overwrite")
    job_id = f"{int(time.time() * 1000):x}-{len(JOBS) + 1:x}"
    job = Job(
        id=job_id,
        source_path=source,
        source_name=source.name,
        command=command,
        output_dir=output_dir,
        markdown_path=markdown_path,
        manifest_path=manifest_path,
        start=start,
        duration=duration,
        device=device,
        asr_engine=asr_engine,
        speaker_mode=speaker_mode,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        speaker_names=speaker_names,
    )
    job.log.append("$ " + " ".join(command) + "\n")
    return job


def _job_store_path(root: Path) -> Path:
    return root / ".cache" / "jobs" / "web_jobs.json"


def _initialize_job_store(root: Path, *, start_worker: bool = True) -> None:
    now = time.time()
    payload = _read_job_store(root)
    restored_jobs: dict[str, Job] = {}
    stored_queue: list[str] = []
    if isinstance(payload.get("queue"), list):
        stored_queue = [str(item) for item in payload["queue"]]
    for raw_job in payload.get("jobs", []):
        if not isinstance(raw_job, dict):
            continue
        job = _job_from_store(raw_job, root, now=now)
        if job is not None:
            restored_jobs[job.id] = job

    with JOBS_LOCK:
        JOBS.clear()
        JOB_QUEUE.clear()
        RUNNING_PROCESSES.clear()
        JOBS.update(restored_jobs)
        for job_id in stored_queue:
            job = JOBS.get(job_id)
            if job is not None and job.status == "queued" and job_id not in JOB_QUEUE:
                JOB_QUEUE.append(job_id)
        queued_by_age = sorted(
            (job for job in JOBS.values() if job.status == "queued" and job.id not in JOB_QUEUE),
            key=lambda item: item.created_at,
        )
        JOB_QUEUE.extend(job.id for job in queued_by_age)
        _save_jobs_locked(root)
    if start_worker:
        _start_job_worker(root)


def _read_job_store(root: Path) -> dict[str, object]:
    path = _job_store_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _job_from_store(payload: dict[str, object], root: Path, *, now: float) -> Job | None:
    try:
        job_id = str(payload["id"])
        source_path = _stored_path(root, payload.get("source_path"))
        output_dir = _stored_path(root, payload.get("output_dir"))
        markdown_path = _stored_path(root, payload.get("markdown_path"))
        manifest_path = _stored_path(root, payload.get("manifest_path"))
        command = [str(item) for item in payload.get("command", []) if str(item)]
    except (KeyError, TypeError, ValueError):
        return None
    if not job_id or not command:
        return None
    status = str(payload.get("status") or "queued")
    log = [str(item) for item in payload.get("log", [])][-MAX_LOG_LINES:] if isinstance(payload.get("log"), list) else []
    returncode = _optional_int_value(payload.get("returncode"))
    completed_at = _optional_float_value(payload.get("completed_at"))
    cancel_requested = bool(payload.get("cancel_requested"))
    process_pid = _optional_int_value(payload.get("process_pid"))
    if status in {"running", "canceling"}:
        previous_status = status
        status = "failed" if previous_status == "running" else "canceled"
        completed_at = now
        returncode = -1 if previous_status == "running" else returncode
        cancel_requested = False
        process_pid = None
        log.append(
            "Сервер был перезапущен во время выполнения задачи. "
            "Она помечена как прерванная; при необходимости запустите ее заново.\n"
        )
    return Job(
        id=job_id,
        source_path=source_path,
        source_name=str(payload.get("source_name") or source_path.name),
        command=command,
        output_dir=output_dir,
        markdown_path=markdown_path,
        manifest_path=manifest_path,
        start=_optional_float_value(payload.get("start")),
        duration=_optional_float_value(payload.get("duration")),
        device=str(payload.get("device") or "auto"),
        asr_engine=str(payload.get("asr_engine") or DEFAULT_ASR_ENGINE),
        speaker_mode=str(payload.get("speaker_mode") or "auto"),
        num_speakers=_optional_int_value(payload.get("num_speakers")),
        min_speakers=_optional_int_value(payload.get("min_speakers")),
        max_speakers=_optional_int_value(payload.get("max_speakers")),
        speaker_names=str(payload.get("speaker_names") or ""),
        created_at=_optional_float_value(payload.get("created_at")) or now,
        status=status,
        returncode=returncode,
        completed_at=completed_at,
        log=log,
        cancel_requested=cancel_requested,
        process_pid=process_pid,
    )


def _stored_path(root: Path, value: object) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty path")
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _store_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _save_jobs_locked(root: Path) -> None:
    payload = {
        "version": JOB_STORE_VERSION,
        "saved_at": time.time(),
        "queue": [job_id for job_id in JOB_QUEUE if job_id in JOBS],
        "jobs": [_job_to_store(job, root) for job in sorted(JOBS.values(), key=lambda item: item.created_at)],
    }
    path = _job_store_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    except OSError as error:
        print(f"[job-store] could not save {path}: {error}", file=sys.stderr, flush=True)


def _job_to_store(job: Job, root: Path) -> dict[str, object]:
    return {
        "id": job.id,
        "source_path": _store_path(root, job.source_path),
        "source_name": job.source_name,
        "command": job.command,
        "output_dir": _store_path(root, job.output_dir),
        "markdown_path": _store_path(root, job.markdown_path),
        "manifest_path": _store_path(root, job.manifest_path),
        "start": job.start,
        "duration": job.duration,
        "device": job.device,
        "asr_engine": job.asr_engine,
        "speaker_mode": job.speaker_mode,
        "num_speakers": job.num_speakers,
        "min_speakers": job.min_speakers,
        "max_speakers": job.max_speakers,
        "speaker_names": job.speaker_names,
        "created_at": job.created_at,
        "status": job.status,
        "returncode": job.returncode,
        "completed_at": job.completed_at,
        "log": job.log[-MAX_LOG_LINES:],
        "cancel_requested": job.cancel_requested,
        "process_pid": job.process_pid,
    }


def _start_job_worker(root: Path) -> None:
    global WORKER_THREAD
    with JOBS_LOCK:
        if not JOB_QUEUE:
            return
        if WORKER_THREAD is not None and WORKER_THREAD.is_alive():
            return
        WORKER_THREAD = threading.Thread(target=_job_worker, args=(root,), daemon=True)
        WORKER_THREAD.start()


def _run_job(job_id: str, root: Path) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        if job.cancel_requested:
            job.status = "canceled"
            job.completed_at = time.time()
            job.log.append("Canceled before start\n")
            _save_jobs_locked(root)
            return
        job.status = "running"
        _save_jobs_locked(root)

    env = os.environ.copy()
    env.update(_read_dotenv(root / ".env"))
    env.setdefault("COLUMNS", "180")
    env.setdefault("NO_COLOR", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TERM", "dumb")
    process = subprocess.Popen(
        job.command,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            _terminate_process(process)
            return
        job.process_pid = process.pid
        RUNNING_PROCESSES[job_id] = process
        cancel_now = job.cancel_requested
        _save_jobs_locked(root)
    if cancel_now:
        _terminate_process(process)
    assert process.stdout is not None
    for line in process.stdout:
        _append_job_log(job_id, line, root)
    returncode = process.wait()
    with JOBS_LOCK:
        RUNNING_PROCESSES.pop(job_id, None)
        job = JOBS.get(job_id)
        if job is None:
            return
        job.process_pid = None
        job.returncode = returncode
        job.completed_at = time.time()
        if job.cancel_requested:
            job.status = "canceled"
            job.log.append("Process canceled by user\n")
        else:
            job.status = "done" if returncode == 0 else "failed"
        if returncode != 0 and job.status != "canceled":
            job.log.append(f"Process exited with code {returncode}\n")
        _save_jobs_locked(root)


def _cancel_job(job_id: str, root: Path) -> Job:
    process: subprocess.Popen[str] | None = None
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError("job not found")
        if job.status == "queued":
            if job_id in JOB_QUEUE:
                JOB_QUEUE.remove(job_id)
            job.cancel_requested = True
            job.status = "canceled"
            job.completed_at = time.time()
            job.log.append("Canceled before start\n")
            _save_jobs_locked(root)
            return job
        if job.status in {"running", "canceling"}:
            if not job.cancel_requested:
                job.log.append("Cancellation requested by user\n")
            job.cancel_requested = True
            job.status = "canceling"
            process = RUNNING_PROCESSES.get(job_id)
            _save_jobs_locked(root)
        else:
            return job
    if process is not None:
        _terminate_process(process)
    return job


def _delete_job(job_id: str, root: Path) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError("job not found")
        if job.status in {"running", "canceling"}:
            raise ValueError("stop running job before removing it")
        if job_id in JOB_QUEUE:
            JOB_QUEUE.remove(job_id)
        JOBS.pop(job_id, None)
        _save_jobs_locked(root)


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        try:
            process.terminate()
        except OSError:
            return


def _enqueue_job(job_id: str, root: Path) -> None:
    with JOBS_LOCK:
        if job_id not in JOB_QUEUE:
            JOB_QUEUE.append(job_id)
        _save_jobs_locked(root)
    _start_job_worker(root)


def _job_worker(root: Path) -> None:
    while True:
        with JOBS_LOCK:
            if not JOB_QUEUE:
                return
            job_id = JOB_QUEUE.pop(0)
            job = JOBS.get(job_id)
            _save_jobs_locked(root)
        if job is None:
            continue
        _run_job(job_id, root)


def _append_job_log(job_id: str, line: str, root: Path) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.log.append(line)
        if len(job.log) > MAX_LOG_LINES:
            job.log = job.log[-MAX_LOG_LINES:]
        _save_jobs_locked(root)


def _result_list(root: Path) -> list[dict[str, object]]:
    outputs_dir = (root / "outputs").resolve()
    if not outputs_dir.exists():
        return []
    manifests = sorted(
        outputs_dir.glob("**/*.manifest.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    results = []
    for manifest_path in manifests:
        payload = _result_payload(manifest_path, root)
        if payload:
            results.append(payload)
    return results


def _result_payload(manifest_path: Path, root: Path) -> dict[str, object] | None:
    manifest = _read_manifest(manifest_path)
    if not manifest:
        return None
    try:
        manifest_modified_at = manifest_path.stat().st_mtime
    except OSError:
        manifest_modified_at = time.time()
    completed_at = _optional_float_value(manifest.get("completed_at")) or manifest_modified_at
    created_at = _optional_float_value(manifest.get("created_at")) or completed_at
    files = _manifest_files(manifest, root, manifest_path=manifest_path)
    samples = _manifest_samples(manifest, root)
    clip_start, clip_duration = _manifest_clip_window(manifest, manifest_path)
    source_name = _manifest_source_name(manifest, manifest_path)
    source_freshness = _manifest_source_freshness(manifest, manifest_path, root, completed_at)
    markdown_url = _primary_markdown_url(files)
    speaker_count = _optional_int_value(manifest.get("speaker_count"))
    constraint_num, constraint_min, constraint_max = _manifest_speaker_constraints(manifest)
    speaker_mode = "exact" if constraint_num else "range" if constraint_min or constraint_max else "auto"
    return {
        "id": _result_id(manifest_path, root),
        "source_name": source_name,
        "source": str(manifest.get("source") or ""),
        "status": "done" if files else "partial",
        "returncode": 0 if files else None,
        "created_at": created_at,
        "completed_at": completed_at,
        "log": [f"Готовый результат из {_relative_display(root, manifest_path)}\n"],
        "asr_engine": str(manifest.get("asr_engine") or ""),
        "asr_quality": _manifest_asr_quality(manifest),
        "speaker_quality": _manifest_speaker_quality(manifest),
        "device": str(manifest.get("device") or ""),
        "speaker_mode": speaker_mode,
        "start": clip_start,
        "duration": clip_duration,
        "recording_duration": _optional_float_value(manifest.get("result_duration"))
        or _optional_float_value(manifest.get("duration")),
        "detected_speaker_count": speaker_count,
        "num_speakers": constraint_num or speaker_count,
        "min_speakers": constraint_min,
        "max_speakers": constraint_max,
        "output_dir": _relative_display(root, manifest_path.parent),
        "markdown_url": markdown_url,
        "files": files,
        "speaker_samples": samples,
        "speaker_names": manifest.get("speaker_names", {}),
        "kind": "clip" if clip_duration is not None else "full",
        "manifest_url": _output_url(root, manifest_path),
        "is_disk_result": True,
        **source_freshness,
    }


def _result_id(manifest_path: Path, root: Path) -> str:
    try:
        identifier = str(manifest_path.resolve().relative_to(root.resolve()))
    except ValueError:
        identifier = str(manifest_path.resolve())
    digest = hashlib.sha1(identifier.encode("utf-8")).hexdigest()[:16]
    return f"result-{digest}"


def _manifest_source_name(manifest: dict[str, object], manifest_path: Path) -> str:
    source = manifest.get("source")
    if source:
        return Path(str(source).replace("\\", "/")).name
    return manifest_path.name.removesuffix(".manifest.json")


def _clip_window_from_manifest_path(manifest_path: Path) -> tuple[float | None, float | None]:
    name = manifest_path.name.removesuffix(".manifest.json")
    parts = name.rsplit("_", 2)
    if len(parts) != 3 or not parts[1].endswith("s") or not parts[2].endswith("s"):
        return None, None
    try:
        start = float(parts[1].removesuffix("s"))
        duration = float(parts[2].removesuffix("s"))
    except ValueError:
        return None, None
    return start, duration


def _manifest_clip_window(manifest: dict[str, object], manifest_path: Path) -> tuple[float | None, float | None]:
    start = _optional_float_value(manifest.get("clip_start"))
    duration = _optional_float_value(manifest.get("clip_duration"))
    if start is not None or duration is not None:
        return start, duration
    return _clip_window_from_manifest_path(manifest_path)


def _manifest_speaker_constraints(manifest: dict[str, object]) -> tuple[int | None, int | None, int | None]:
    constraints = manifest.get("speaker_constraints")
    if not isinstance(constraints, dict):
        return None, None, None
    return (
        _optional_int_value(constraints.get("num_speakers")),
        _optional_int_value(constraints.get("min_speakers")),
        _optional_int_value(constraints.get("max_speakers")),
    )


def _manifest_asr_quality(manifest: dict[str, object]) -> dict[str, object] | None:
    quality = manifest.get("asr_quality")
    return quality if isinstance(quality, dict) else None


def _manifest_speaker_quality(manifest: dict[str, object]) -> dict[str, object] | None:
    quality = manifest.get("speaker_quality")
    return quality if isinstance(quality, dict) else None


def _find_result_manifest(result_id: str, root: Path) -> Path:
    for manifest_path in (root / "outputs").resolve().glob("**/*.manifest.json"):
        if _result_id(manifest_path, root) == result_id:
            return manifest_path
    raise ValueError("result not found")


def _job_list(root: Path) -> list[dict[str, object]]:
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)
        return [_job_payload(job, root) for job in jobs]


def _job_payload(job: Job, root: Path) -> dict[str, object]:
    manifest = _read_manifest(job.manifest_path)
    files = _manifest_files(manifest, root, manifest_path=job.manifest_path)
    samples = _manifest_samples(manifest, root)
    markdown_url = _primary_markdown_url(files) or (_output_url(root, job.markdown_path) if job.markdown_path.exists() else None)
    return {
        "id": job.id,
        "source_name": job.source_name,
        "status": job.status,
        "returncode": job.returncode,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "log": job.log,
        "cancel_requested": job.cancel_requested,
        "process_pid": job.process_pid,
        "asr_engine": job.asr_engine,
        "asr_quality": _manifest_asr_quality(manifest),
        "speaker_quality": _manifest_speaker_quality(manifest),
        "device": job.device,
        "speaker_mode": job.speaker_mode,
        "start": job.start,
        "duration": job.duration,
        "num_speakers": job.num_speakers,
        "min_speakers": job.min_speakers,
        "max_speakers": job.max_speakers,
        "output_dir": _relative_display(root, job.output_dir),
        "markdown_url": markdown_url,
        "files": files,
        "speaker_samples": samples,
        "speaker_names": manifest.get("speaker_names", {}),
    }


def _apply_speaker_names(job_id: str, speaker_names: str, root: Path) -> Job:
    from voice_recognizer.cli import parse_speaker_names, rewrite_manifest_exports

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError("job not found")
        if job.status == "running":
            raise ValueError("job is still running")
        job.status = "running"
        job.speaker_names = speaker_names
        job.log.append("Applying speaker names without rerunning ASR/diarization\n")
        _save_jobs_locked(root)
    try:
        outputs = rewrite_manifest_exports(job.manifest_path, speaker_names=parse_speaker_names(speaker_names))
    except Exception as error:
        with JOBS_LOCK:
            job = JOBS[job_id]
            job.returncode = 1
            job.completed_at = time.time()
            job.status = "failed"
            job.log.append(f"Apply names failed: {error}\n")
            _save_jobs_locked(root)
        raise ValueError("apply speaker names failed") from error

    with JOBS_LOCK:
        job = JOBS[job_id]
        job.returncode = 0
        job.completed_at = time.time()
        job.status = "done"
        job.markdown_path = outputs.get("edited_markdown", job.markdown_path)
        job.log.append(f"Edited Markdown: {outputs.get('edited_markdown')}\n")
        job.log.append(f"Edited TXT: {outputs.get('edited_text')}\n")
        if len(job.log) > MAX_LOG_LINES:
            job.log = job.log[-MAX_LOG_LINES:]
        _save_jobs_locked(root)
        return job


def _apply_result_speaker_names(result_id: str, speaker_names: str, root: Path) -> dict[str, object]:
    from voice_recognizer.cli import parse_speaker_names, rewrite_manifest_exports

    manifest_path = _find_result_manifest(result_id, root)
    outputs = rewrite_manifest_exports(manifest_path, speaker_names=parse_speaker_names(speaker_names))
    payload = _result_payload(manifest_path, root)
    if payload is None:
        raise ValueError("result manifest disappeared")
    payload["log"] = [
        "Speaker names applied without rerunning ASR/diarization\n",
        f"Edited Markdown: {outputs.get('edited_markdown')}\n",
        f"Edited TXT: {outputs.get('edited_text')}\n",
    ]
    return payload


def _create_result_rerun_job(result_id: str, root: Path) -> Job:
    manifest_path = _find_result_manifest(result_id, root)
    manifest = _read_manifest(manifest_path)
    if not manifest:
        raise ValueError("result manifest disappeared")
    source_path = _manifest_source_path(manifest, root)
    start, duration = _manifest_clip_window(manifest, manifest_path)
    num_speakers, min_speakers, max_speakers = _manifest_speaker_constraints(manifest)
    asr_engine = normalize_asr_engine(str(manifest.get("asr_engine") or DEFAULT_ASR_ENGINE))
    device = str(manifest.get("device") or "auto")
    speaker_names = _speaker_names_payload_to_cli(manifest.get("speaker_names"))
    return _create_job(
        source=source_path,
        output_dir=manifest_path.parent,
        start=start,
        duration=duration,
        device=device,
        asr_engine=asr_engine,
        speaker_mode="auto",
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        speaker_names=speaker_names,
        overwrite=True,
        root=root,
    )


def _manifest_source_freshness(
    manifest: dict[str, object],
    manifest_path: Path,
    root: Path,
    completed_at: float,
) -> dict[str, object]:
    raw_source = str(manifest.get("source") or "").strip()
    base: dict[str, object] = {
        "source_status": "unknown",
        "source_status_label": "исходник не проверен",
        "source_changed": False,
        "source_missing": False,
        "source_modified_at": None,
        "source_size": None,
        "source_path": "",
    }
    if not raw_source:
        return base

    source_path = Path(raw_source)
    if not source_path.is_absolute():
        source_path = root / source_path
    source_path = source_path.resolve()
    try:
        source_path.relative_to(root.resolve())
    except ValueError:
        base["source_status_label"] = "исходник вне проекта"
        base["source_path"] = str(source_path)
        return base

    base["source_path"] = _relative_display(root, source_path)
    if not source_path.exists():
        base.update(
            {
                "source_status": "missing",
                "source_status_label": "исходник не найден",
                "source_missing": True,
            }
        )
        return base

    try:
        source_stat = source_path.stat()
    except OSError:
        return base

    source_modified_at = source_stat.st_mtime
    stored_source_mtime = _optional_float_value(manifest.get("source_mtime"))
    stored_source_size = _optional_int_value(manifest.get("source_size"))
    if stored_source_mtime is not None or stored_source_size is not None:
        changed = (
            stored_source_size is not None
            and source_stat.st_size != stored_source_size
        ) or (
            stored_source_mtime is not None
            and abs(source_modified_at - stored_source_mtime) > SOURCE_FRESHNESS_TOLERANCE_SECONDS
        )
    else:
        changed = source_modified_at > completed_at + SOURCE_FRESHNESS_TOLERANCE_SECONDS
    base.update(
        {
            "source_status": "changed" if changed else "fresh",
            "source_status_label": "исходник изменился" if changed else "исходник свежий",
            "source_changed": changed,
            "source_modified_at": source_modified_at,
            "source_size": source_stat.st_size,
        }
    )
    return base


def _manifest_source_path(manifest: dict[str, object], root: Path) -> Path:
    raw_source = str(manifest.get("source") or "").strip()
    if not raw_source:
        raise ValueError("result manifest does not include source")
    path = Path(raw_source)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("result source must stay inside project") from error
    if not path.exists():
        raise ValueError("result source file not found")
    return path


def _resolve_source(inbox: Path, source_name: str) -> Path:
    files = {path.name: path for path in iter_media_files(inbox)}
    if source_name not in files:
        raise ValueError("source not found in Inbox")
    return files[source_name]


def _inbox_files_payload(inbox: Path, results: list[dict[str, object]] | None = None) -> list[dict[str, object]]:
    results_by_source = _results_by_source(results or [])
    return [
        _inbox_file_payload(path, results_by_source.get(_source_match_key(path.name), []))
        for path in iter_media_files(inbox)
    ]


def _inbox_file_payload(path: Path, results: list[dict[str, object]] | None = None) -> dict[str, object]:
    stat = path.stat()
    metadata = _media_metadata(path, stat)
    result_summaries = [_inbox_result_summary(result) for result in (results or [])]
    return {
        "name": path.name,
        "size": stat.st_size,
        "size_label": _file_size_label(path),
        "duration": metadata.get("duration"),
        "duration_label": metadata.get("duration_label"),
        "format_label": metadata.get("format_label"),
        "modified_label": metadata.get("modified_label"),
        "processed": bool(result_summaries),
        "results": result_summaries,
    }


def _results_by_source(results: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    by_source: dict[str, list[dict[str, object]]] = {}
    for result in results:
        source_name = str(result.get("source_name") or "")
        if not source_name:
            continue
        by_source.setdefault(_source_match_key(source_name), []).append(result)
    return by_source


def _source_match_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _inbox_result_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "id": result.get("id"),
        "status": result.get("status"),
        "kind": result.get("kind"),
        "completed_at": result.get("completed_at"),
        "output_dir": result.get("output_dir"),
        "file_count": len(result.get("files", [])) if isinstance(result.get("files"), list) else 0,
        "speaker_count": len(result.get("speaker_samples", [])) if isinstance(result.get("speaker_samples"), list) else 0,
        "source_status": result.get("source_status"),
        "source_status_label": result.get("source_status_label"),
        "source_changed": result.get("source_changed"),
        "source_missing": result.get("source_missing"),
    }


def _unique_inbox_path(inbox: Path, filename: str) -> Path:
    inbox = inbox.resolve()
    clean_name = _safe_upload_name(filename)
    target = (inbox / clean_name).resolve()
    try:
        target.relative_to(inbox)
    except ValueError as error:
        raise ValueError("invalid upload filename") from error
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    for index in range(2, 10000):
        candidate = (inbox / f"{stem}-{index}{suffix}").resolve()
        try:
            candidate.relative_to(inbox)
        except ValueError as error:
            raise ValueError("invalid upload filename") from error
        if not candidate.exists():
            return candidate
    raise ValueError("too many files with the same name in Inbox")


def _safe_upload_name(filename: str) -> str:
    name = Path(str(filename).replace("\\", "/")).name.strip()
    if not name:
        raise ValueError("upload filename is empty")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_MEDIA_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_MEDIA_EXTENSIONS))
        raise ValueError(f"unsupported file type {suffix or '<none>'}; supported: {supported}")
    stem = Path(name).stem.strip().strip(".") or "audio"
    clean_stem = "".join(
        "_" if char in {"/", "\\", ":", "\0"} or ord(char) < 32 else char
        for char in stem
    ).strip(". ")
    return f"{clean_stem or 'audio'}{suffix}"


def _read_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_files(manifest: dict[str, object], root: Path, *, manifest_path: Path | None = None) -> list[dict[str, str]]:
    labels = {
        "edited_markdown": "Улучшенный Markdown",
        "edited_text": "Улучшенный TXT",
        "detailed_markdown": "Общий Markdown",
        "clean_timestamps_markdown": "Чистый + время",
        "clean_markdown": "Чистый",
        "clean_text": "TXT",
        "timeline_text": "TXT + время",
    }
    outputs = manifest.get("outputs", {})
    if not isinstance(outputs, dict):
        return []
    files = []
    for key, label in labels.items():
        value = outputs.get(key)
        if value:
            path = (root / str(value)).resolve()
        elif key == "edited_markdown" and manifest_path is not None:
            path = _edited_export_paths(manifest_path)[0]
        elif key == "edited_text" and manifest_path is not None:
            path = _edited_export_paths(manifest_path)[1]
        else:
            continue
        if path.exists():
            files.append({"key": key, "label": label, "url": _output_url(root, path) or ""})
    if manifest_path is not None:
        repair_path = _repair_report_path(manifest_path)
        if repair_path.exists() and not any(file.get("key") == "repair_json" for file in files):
            files.append({"key": "repair_json", "label": "Диагностика JSON", "url": _output_url(root, repair_path) or ""})
    return files


def _primary_markdown_url(files: list[dict[str, str]]) -> str | None:
    for key in ("edited_markdown", "detailed_markdown", "clean_timestamps_markdown", "clean_markdown"):
        match = next((file for file in files if file.get("key") == key and file.get("url")), None)
        if match:
            return match["url"]
    return None


def _repair_report_path(manifest_path: Path) -> Path:
    name = manifest_path.name
    if name.endswith(".manifest.json"):
        return manifest_path.with_name(name.removesuffix(".manifest.json") + ".repair.json")
    return manifest_path.with_suffix(".repair.json")


def _edited_export_paths(manifest_path: Path) -> tuple[Path, Path]:
    name = manifest_path.name
    if name.endswith(".manifest.json"):
        stem = name.removesuffix(".manifest.json")
        return manifest_path.with_name(f"{stem}.edited.md"), manifest_path.with_name(f"{stem}.edited.txt")
    return manifest_path.with_suffix(".edited.md"), manifest_path.with_suffix(".edited.txt")


def _manifest_samples(manifest: dict[str, object], root: Path) -> list[dict[str, str]]:
    samples = manifest.get("speaker_samples", {})
    names = manifest.get("speaker_names", {})
    if not isinstance(samples, dict):
        return []
    if not isinstance(names, dict):
        names = {}
    rows = []
    for speaker, value in sorted(samples.items(), key=lambda item: int(item[0])):
        path = (root / str(value)).resolve()
        if path.exists():
            rows.append(
                {
                    "speaker": str(speaker),
                    "label": str(names.get(str(speaker)) or f"Спикер {speaker}"),
                    "name": str(names.get(str(speaker)) or ""),
                    "url": _output_url(root, path) or "",
                }
            )
    return rows


def _output_url(root: Path, path: Path) -> str | None:
    try:
        relative = str(path.resolve().relative_to(root.resolve())).replace(os.sep, "/")
    except ValueError:
        return None
    return "/" + quote(relative)


def _speaker_names_payload_to_cli(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    lines = []
    for key, name in sorted(value.items(), key=lambda item: int(str(item[0]))):
        clean = str(name).strip()
        if clean:
            lines.append(f"{key}={clean}")
    return "\n".join(lines)


def _copy_file_range(source: object, target: object, length: int | None = None) -> None:
    remaining = length
    while remaining is None or remaining > 0:
        chunk_size = RESPONSE_STREAM_CHUNK_BYTES
        if remaining is not None:
            chunk_size = min(chunk_size, remaining)
        chunk = source.read(chunk_size)
        if not chunk:
            return
        target.write(chunk)
        if remaining is not None:
            remaining -= len(chunk)


def _parse_range_header(value: str | None, file_size: int) -> tuple[int, int] | None:
    if not value or not value.startswith("bytes=") or file_size <= 0:
        return None
    requested = value.removeprefix("bytes=").split(",", 1)[0].strip()
    if "-" not in requested:
        return None
    raw_start, raw_end = requested.split("-", 1)
    if raw_start == "":
        suffix = int(raw_end) if raw_end.isdigit() else 0
        if suffix <= 0:
            return None
        return max(0, file_size - suffix), file_size - 1
    if not raw_start.isdigit():
        return None
    start = int(raw_start)
    end = int(raw_end) if raw_end.isdigit() else file_size - 1
    if start >= file_size or end < start:
        return None
    return start, min(end, file_size - 1)


def _content_type(path: Path) -> str:
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    if path.suffix == ".txt":
        return "text/plain; charset=utf-8"
    if path.suffix == ".json":
        return "application/json; charset=utf-8"
    if path.suffix == ".wav":
        return "audio/wav"
    return "application/octet-stream"


def _resolve_output_dir(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    outputs_root = (root / "outputs").resolve()
    try:
        path.relative_to(outputs_root)
    except ValueError as error:
        raise ValueError("output_dir must stay inside outputs/") from error
    return path


def _optional_float_value(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _optional_int_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = float(text)
    if parsed < 0:
        raise ValueError("time values must be non-negative")
    return parsed


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = int(text)
    if parsed < 0:
        raise ValueError("numeric values must be non-negative")
    return parsed


def _speaker_constraints_from_payload(payload: dict[str, object]) -> tuple[str, int | None, int | None, int | None]:
    num_speakers = _optional_int(payload.get("num_speakers"))
    min_speakers = _optional_int(payload.get("min_speakers"))
    max_speakers = _optional_int(payload.get("max_speakers"))
    raw_mode = payload.get("speaker_mode")
    if raw_mode is None:
        speaker_mode = "exact" if num_speakers is not None else "range" if min_speakers is not None or max_speakers is not None else "auto"
    else:
        speaker_mode = str(raw_mode).strip().lower()
    if speaker_mode not in {"auto", "exact", "range"}:
        raise ValueError("speaker_mode must be auto, exact, or range")
    if speaker_mode == "auto":
        return "auto", None, None, None
    if speaker_mode == "exact":
        if num_speakers is None:
            raise ValueError("num_speakers is required in exact speaker mode")
        return "exact", num_speakers, None, None
    if min_speakers is None and max_speakers is None:
        raise ValueError("min_speakers or max_speakers is required in range speaker mode")
    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        raise ValueError("min_speakers must be less than or equal to max_speakers")
    return "range", None, min_speakers, max_speakers


def _clip_suffix(start: float | None, duration: float | None) -> str:
    if start is None and duration is None:
        return ""
    return f"_{int(start or 0)}s_{int(duration or 0)}s"


def _media_metadata(path: Path, stat: os.stat_result | None = None) -> dict[str, object]:
    stat = stat or path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = MEDIA_METADATA_CACHE.get(key)
    if cached is not None:
        return cached
    metadata: dict[str, object] = {
        "format_label": _format_label(path),
        "modified_label": _modified_label(path, stat),
    }
    duration = _probe_duration(path)
    if duration is not None:
        metadata["duration"] = duration
        metadata["duration_label"] = _duration_label(duration)
    if len(MEDIA_METADATA_CACHE) > 256:
        MEDIA_METADATA_CACHE.clear()
    MEDIA_METADATA_CACHE[key] = metadata
    return metadata


def _probe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        process = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0:
        return None
    try:
        payload = json.loads(process.stdout)
        duration = float(payload.get("format", {}).get("duration"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return duration if duration >= 0 else None


def _duration_label(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_label(path: Path) -> str:
    return path.suffix.upper().lstrip(".") or "AUDIO"


def _modified_label(path: Path, stat: os.stat_result | None = None) -> str:
    stat = stat or path.stat()
    return time.strftime("%d.%m %H:%M", time.localtime(stat.st_mtime))


def _file_size_label(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} GB"


def _render_asr_engine_option(value: str, label: str, available: bool) -> str:
    selected = " selected" if value == DEFAULT_ASR_ENGINE else ""
    disabled = "" if available else " disabled"
    suffix = "" if available else " (скоро)"
    return (
        f'<option value="{html.escape(value)}"{selected}{disabled}>'
        f"{html.escape(label + suffix)}</option>"
    )


def _asr_runtime_status(root: Path) -> dict[str, str]:
    gigastt_bin = root / "tools" / "bin" / "gigastt"
    model_dir = root / ".models" / "gigastt"
    required = [
        ("encoder", ["v3_rnnt_encoder.onnx", "v3_rnnt_encoder_int8.onnx"]),
        ("decoder", ["v3_rnnt_decoder.onnx"]),
        ("joint", ["v3_rnnt_joint.onnx"]),
        ("vocab", ["v3_vocab.txt"]),
        ("punct", ["punct/rupunct_small_int8.onnx", "punct/config.json", "punct/tokenizer.json"]),
    ]
    missing: list[str] = []
    if not gigastt_bin.exists() or not os.access(gigastt_bin, os.X_OK):
        missing.append("tools/bin/gigastt")
    for label, alternatives in required:
        if not any((model_dir / name).exists() for name in alternatives):
            missing.append(label)
    if missing:
        return {
            "class": "failed",
            "label": "GigaSTT не настроен",
            "detail": "локальный ASR еще не готов",
            "help": "Откройте 'Настроить Диктум.command' и разрешите этап 4/5: GigaSTT/GigaAM v3.",
            "title": "Не найдено: " + ", ".join(missing),
        }
    return {
        "class": "done",
        "label": "GigaSTT готов",
        "detail": "GigaAM v3 найден локально",
        "help": "Можно запускать обработку. Это локальный распознаватель речи для русского языка.",
        "title": "tools/bin/gigastt и файлы .models/gigastt доступны на этом Mac",
    }


def _relative_display(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _cli_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values
