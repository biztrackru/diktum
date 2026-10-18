"""Content identities for cache invalidation, without repeated model hashing."""
from functools import lru_cache
import importlib.metadata
from pathlib import Path


@lru_cache(maxsize=128)
def _digest(path: str, size: int, mtime: int, ctime: int, inode: int) -> str:
    from voice_recognizer.assets import digest
    return digest(Path(path))


def file_identity(path: Path) -> str | None:
    try:
        resolved = path.resolve()
        stat = resolved.stat()
        return _digest(str(resolved), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    except FileNotFoundError:
        return None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def disable_onnx_telemetry() -> None:
    try:
        import onnxruntime
    except ImportError:
        return
    onnxruntime.disable_telemetry_events()


def gigastt_identity(binary: Path | None, models: Path | None, punct: Path | None) -> dict:
    return {
        "binary_sha256": file_identity(binary) if binary else None,
        "models": {p.name: file_identity(p) for p in sorted(models.glob("v3*")) if p.is_file()} if models else {},
        "punctuation": {p.name: file_identity(p) for p in sorted(punct.glob("*")) if p.is_file()} if punct else {},
    }
