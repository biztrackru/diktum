"""Explicit, hash-verified downloads; processing never calls this installer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import tarfile
import tempfile
import urllib.request
import urllib.error

MANIFEST = Path(__file__).resolve().parents[2] / "config/resources.json"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def target_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Resource path escapes installation: {relative}")
    return path


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def status(root: Path, group: str, manifest: dict | None = None) -> bool:
    definition = (manifest or load_manifest())["groups"][group]
    try:
        receipt = json.loads((root / ".cache/resources" / f"{group}.json").read_text())
        expected = hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
        targets = {name for resource in definition["resources"]
                   for name in resource.get("members", {"file": resource["target"]}).values()}
        return (receipt["definition_sha256"] == expected and set(receipt["files"]) == targets and
                all(target_path(root, name).is_file() and digest(target_path(root, name)) == sha
                    for name, sha in receipt["files"].items()))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def download(resource: dict, cache: Path, *, offline: bool = False) -> Path:
    expected = resource["sha256"]
    destination = cache / expected
    if destination.is_file() and digest(destination) == expected:
        return destination
    if offline:
        raise ValueError("Ресурс отсутствует в кеше. Запустите настройку с доступом к интернету.")
    if not resource["url"].startswith("https://"):
        raise ValueError("Only HTTPS resources are accepted")
    cache.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context()
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    temporary = cache / f"{expected}.part"
    print(f"Скачиваю {resource['target']}", flush=True)
    for attempt in range(3):
        offset = temporary.stat().st_size if temporary.exists() else 0
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Diktum/0.2; +https://github.com/biztrackru/diktum)"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(resource["url"], headers=headers)
            with urllib.request.urlopen(request, context=context, timeout=60) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Resource redirected outside HTTPS")
                append = response.status == 206 and offset > 0
                if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Invalid download resume range")
                if not append:
                    offset = 0
                length = response.headers.get("Content-Length")
                with temporary.open("ab" if append else "wb") as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
                if length is not None and temporary.stat().st_size != offset + int(length):
                    raise OSError("Загрузка оборвалась; продолжаю с сохранённой позиции.")
            break
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            print(f"Повторная загрузка {resource['target']} ({attempt + 2}/3)", flush=True)
    actual = digest(temporary)
    if actual != expected:
        quarantine = cache / f"rejected-{actual}"
        os.replace(temporary, quarantine)
        raise ValueError(f"SHA-256 mismatch: {resource['target']}; expected {expected}, got {actual}. "
                         "Файл изолирован и не установлен.")
    os.replace(temporary, destination)
    return destination


def install(root: Path, groups: list[str], *, offline: bool = False, manifest: dict | None = None) -> None:
    definitions = manifest or load_manifest()
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache = root / ".cache/downloads/resources"
    for group in groups:
        definition = definitions["groups"][group]
        if status(root, group, definitions):
            print(f"[OK] {group} {definition['version']}", flush=True)
            continue
        # Download and verify the entire group before replacing any installed file.
        with tempfile.TemporaryDirectory(dir=root, prefix=".resource-stage-") as directory:
            stage = Path(directory)
            staged: dict[str, Path] = {}
            for resource in definition["resources"]:
                source = download(resource, cache, offline=offline)
                members = resource.get("members")
                if members:
                    with tarfile.open(source, "r:gz") as archive:
                        for basename, relative in members.items():
                            matches = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name == basename]
                            if len(matches) != 1:
                                raise ValueError(f"Archive needs exactly one {basename}")
                            target_path(root, relative)
                            output = stage / str(len(staged))
                            with archive.extractfile(matches[0]) as stream, output.open("wb") as dest:
                                shutil.copyfileobj(stream, dest)
                            staged[relative] = output
                else:
                    relative = resource["target"]
                    target_path(root, relative)
                    output = stage / str(len(staged))
                    shutil.copyfile(source, output)
                    staged[relative] = output
            hashes = {name: digest(path) for name, path in staged.items()}
            changed: list[tuple[Path, Path | None]] = []
            try:
                for relative, source in staged.items():
                    target = target_path(root, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    backup = None
                    if target.exists():
                        backup = root / ".cache/resource-backups" / digest(target) / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                    if relative == "tools/bin/gigastt":
                        source.chmod(0o755)
                    os.replace(source, target)
                    changed.append((target, backup))
                receipt = root / ".cache/resources" / f"{group}.json"
                receipt.parent.mkdir(parents=True, exist_ok=True)
                temporary = stage / "receipt.json"
                temporary.write_text(json.dumps({
                    "version": definition["version"], "files": hashes,
                    "definition_sha256": hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest(),
                }, indent=2) + "\n")
                os.replace(temporary, receipt)
            except BaseException:
                for target, backup in reversed(changed):
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        shutil.copy2(backup, target)
                raise
            print(f"[OK] {group} {definition['version']}; SHA-256 verified", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Диктум: явная установка проверенных локальных ресурсов")
    parser.add_argument("action", choices=["install", "status"])
    parser.add_argument("groups", nargs="*", default=["gigastt", "rnnt", "ctc", "vad"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "install":
            install(args.root, args.groups, offline=args.offline)
        elif not all(status(args.root, group) for group in args.groups):
            raise ValueError("Ресурсы отсутствуют или устарели. Запустите Настроить Диктум.command.")
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Не удалось подготовить ресурсы: {error}\nПовторите настройку; прежние файлы сохранены.\n")


if __name__ == "__main__":
    main()
