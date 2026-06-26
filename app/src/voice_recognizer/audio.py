from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class AudioToolError(RuntimeError):
    pass


SUPPORTED_MEDIA_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flac",
    ".flv",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".wav",
    ".webm",
    ".wmv",
}


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration_seconds: float
    sample_rate: int | None
    channels: int | None
    codec: str | None

    @property
    def duration_label(self) -> str:
        total = int(round(self.duration_seconds))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise AudioToolError("ffmpeg is not installed or is not available in PATH")
    if not shutil.which("ffprobe"):
        raise AudioToolError("ffprobe is not installed or is not available in PATH")


def probe_audio(path: Path) -> AudioInfo:
    require_ffmpeg()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    audio_stream = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio"), {})
    duration = payload.get("format", {}).get("duration") or audio_stream.get("duration") or 0
    return AudioInfo(
        path=path,
        duration_seconds=float(duration),
        sample_rate=int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
        channels=int(audio_stream["channels"]) if audio_stream.get("channels") else None,
        codec=audio_stream.get("codec_name"),
    )


def normalize_audio(source: Path, target: Path, *, start: float | None = None, duration: float | None = None) -> Path:
    require_ffmpeg()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y"]
    if start is not None:
        command += ["-ss", f"{start:.3f}"]
    command += ["-i", str(source)]
    if duration is not None:
        command += ["-t", f"{duration:.3f}"]
    command += [
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(target),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


def safe_stem(path: Path) -> str:
    keep = []
    for char in path.stem:
        if char.isalnum() or char in (" ", "-", "_", "+"):
            keep.append(char)
        else:
            keep.append("_")
    return "".join(keep).strip().replace(" ", "_")


def iter_media_files(directory: Path, *, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in directory.glob(pattern)
        if path.is_file() and path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
    ]
    return sorted(files, key=lambda path: path.name.lower())
