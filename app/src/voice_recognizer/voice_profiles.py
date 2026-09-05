"""Local, user-confirmed speaker profiles. Predictions never enroll themselves."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import threading
import time
import uuid
import wave
from pathlib import Path

VERSION = 1
MODEL_REPO = "pyannote/speaker-diarization-community-1"
MIN_SCORE = 0.65
MIN_MARGIN = 0.12
INFERENCE_LOCK = threading.RLock()
_EMBEDDER = None


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write(path: Path, value) -> None:
    from voice_recognizer.handy_ctc import atomic_json
    atomic_json(path, value)
    path.chmod(0o600)


def bank_path(root: Path) -> Path:
    return root / ".voice-profiles/profiles.json"


@contextlib.contextmanager
def bank_lock(root: Path):
    import fcntl
    directory = bank_path(root).parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def result_lock(root: Path, path: Path):
    import fcntl
    lock = root / ".cache/voice-profiles/locks" / f"{_hash(str(path.resolve()))}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_bank(root: Path) -> dict:
    data = _read(bank_path(root), {"version": VERSION, "profiles": []})
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("profiles"), list):
        raise ValueError("Библиотека голосов повреждена или имеет неподдерживаемую версию.")
    return data


def profile_summary(root: Path) -> list[dict]:
    return [{"id": p["id"], "name": p["name"], "examples": len(p["examples"]),
             "recordings": len({e['source'] for e in p['examples']})}
            for p in read_bank(root)["profiles"]]


def remove_profile(root: Path, profile_id: str) -> None:
    with bank_lock(root):
        bank = read_bank(root)
        bank["profiles"] = [p for p in bank["profiles"] if p["id"] != profile_id]
        _write(bank_path(root), bank)


def _local_path(root: Path, value) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("В результате не найден путь к аудио или диаризации.")
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("Файлы профилей должны находиться в папке Диктума.") from error
    if not path.is_file():
        raise ValueError("Нужный аудиофайл не найден. Верните исходник/кэш или обработайте запись заново.")
    return path


def _stat(path: Path) -> dict:
    s = path.stat()
    return {"path": str(path), "size": s.st_size, "mtime_ns": s.st_mtime_ns}


def _manifest(root: Path, path: Path) -> dict:
    path = _local_path(root, str(path.resolve()))
    if not path.is_relative_to((root / "outputs").resolve()) or not path.name.endswith('.manifest.json'):
        raise ValueError("Нужен manifest результата в outputs.")
    data = _read(path)
    if not isinstance(data, dict):
        raise ValueError("Не удалось прочитать результат.")
    return data


def signature(root: Path, manifest: dict) -> str:
    # Names are excluded: confirming them should not invalidate acoustic features.
    files = [_stat(_local_path(root, manifest[k])) for k in ("audio", "diarization_json")]
    return _hash(files)


def source_key(root: Path, manifest: dict) -> str:
    path = Path(str(manifest.get('source') or manifest['audio']))
    return str((path if path.is_absolute() else root / path).resolve())


def _windows(turns: list[dict], speaker: int) -> list[tuple[float, float]]:
    candidates = []
    for turn in turns:
        if int(turn["speaker"]) != speaker:
            continue
        start, end = float(turn['start']) + .3, float(turn['end']) - .3
        if not (math.isfinite(start) and math.isfinite(end)) or end - start < 3.5:
            continue
        length = min(8., end - start)
        for at in ((start + end - length) / 2, start, end - length):
            candidates.append((at, at + length))
    picked = []
    for start, end in sorted(candidates, key=lambda x: -(x[1] - x[0])):
        if any(min(end, b) > max(start, a) for a, b in picked):
            continue
        picked.append((start, end))
        if len(picked) == 3:
            break
    return sorted(picked)


def _unit(vector) -> list[float]:
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    if not values or not all(math.isfinite(v) for v in values) or norm < 1e-8:
        raise ValueError("Не удалось получить устойчивый образец голоса.")
    return [v / norm for v in values]


class Embedder:
    def __init__(self):
        # Resolve a cached file explicitly: this component never downloads models.
        os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
        os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / ".cache/matplotlib"))
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.core.io")
        try:
            from huggingface_hub import hf_hub_download
            checkpoint = Path(hf_hub_download(MODEL_REPO, "embedding/pytorch_model.bin", local_files_only=True))
            import torch
            from pyannote.audio.pipelines.speaker_verification import PyannoteAudioPretrainedSpeakerEmbedding
            from voice_recognizer.handy_ctc import file_digest
            self.model_id = file_digest(checkpoint)
            self.torch = torch
            self.model = PyannoteAudioPretrainedSpeakerEmbedding(str(checkpoint), device=torch.device("cpu"))
        except Exception as error:
            raise ValueError("Локальная модель голосов недоступна. Сначала выполните обычную обработку со спикерами, чтобы подготовить pyannote.") from error

    def extract(self, audio: Path, windows: list[tuple[float, float]]) -> list[list[float]]:
        import numpy as np
        vectors = []
        with wave.open(str(audio), 'rb') as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
                raise ValueError("Для профиля нужен подготовленный WAV mono 16 kHz.")
            for start, end in windows:
                stream.setpos(min(stream.getnframes(), max(0, int(start * 16000))))
                pcm = stream.readframes(int((end - start) * 16000))
                samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
                if len(samples) < 3 * 16000:
                    continue
                vectors.append(_unit(self.model(self.torch.from_numpy(samples)[None, None, :])[0]))
        return vectors


def speaker_vectors(root: Path, manifest: dict) -> dict:
    global _EMBEDDER
    sig = signature(root, manifest)
    with INFERENCE_LOCK:
        if _EMBEDDER is None:
            _EMBEDDER = Embedder()
        model = _EMBEDDER
        cache = root / ".cache/voice-profiles/embeddings" / f"{sig}-{model.model_id}.json"
        cached = _read(cache)
        if isinstance(cached, dict) and cached.get("version") == VERSION:
            return cached
        audio = _local_path(root, manifest["audio"])
        diarization = _read(_local_path(root, manifest['diarization_json']))
        turns = diarization['turns']
        speakers = {}
        for number in sorted({int(t['speaker']) for t in turns}):
            windows = _windows(turns, number)
            vectors = model.extract(audio, windows) if windows else []
            speakers[str(number + 1)] = {"vectors": vectors, "windows": windows}
        result = {"version": VERSION, "signature": sig, "model": model.model_id, "speakers": speakers}
        _write(cache, result)
        return result


def enroll(root: Path, path: Path, speaker: str, name: str) -> dict:
    """Explicit enrollment from a name the user has already applied to a result."""
    manifest = _manifest(root, path)
    name = name.strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError("Укажите имя длиной от 1 до 120 символов.")
    if str(manifest.get('speaker_names', {}).get(str(speaker), '')).strip() != name:
        raise ValueError("Сначала примените подтверждённое имя этого спикера к результату.")
    features = speaker_vectors(root, manifest)
    data = features['speakers'].get(str(speaker), {})
    if not data.get('vectors'):
        raise ValueError("Недостаточно непрерывной речи для профиля. Выберите другую запись с этим человеком.")
    source = source_key(root, manifest)
    example_key = _hash([features['signature'], str(speaker)])
    with bank_lock(root):
        bank = read_bank(root)
        profile = next((p for p in bank['profiles'] if p['name'].casefold() == name.casefold()), None)
        if profile is None:
            profile = {"id": uuid.uuid4().hex, "name": name, "model": features['model'], "examples": []}
            bank['profiles'].append(profile)
        if profile['model'] != features['model']:
            raise ValueError("Модель голосов изменилась. Удалите старый профиль и создайте его заново.")
        profile['examples'] = [e for e in profile['examples'] if e['id'] != example_key]
        profile['examples'].append({"id": example_key, "source": source, "speaker": str(speaker),
                                    "vectors": data['vectors'], "windows": data['windows'],
                                    "confirmed_at": time.time()})
        profile['examples'] = profile['examples'][-12:]
        _write(bank_path(root), bank)
    return {"profiles": profile_summary(root)}


def match_vectors(vectors: list, profiles: list, *, exclude_source: str | None = None) -> dict:
    """Conservative cosine score + runner-up margin + agreement across excerpts."""
    if not vectors:
        return {"status": "insufficient", "reason": "Мало непрерывной речи"}
    candidates = []
    for profile in profiles:
        examples = [v for e in profile['examples'] if e['source'] != exclude_source for v in e['vectors']]
        if not examples:
            continue
        scores = []
        for vector in vectors:
            similarities = [sum(a * b for a, b in zip(vector, ref)) for ref in examples if len(ref) == len(vector)]
            scores.append(max(similarities) if similarities else -1.)
        ordered = sorted(scores, reverse=True)
        score = sum(ordered[:min(2, len(ordered))]) / min(2, len(ordered))
        candidates.append({"profile_id": profile['id'], "name": profile['name'], "score": score,
                           "votes": sum(s >= MIN_SCORE for s in scores)})
    candidates.sort(key=lambda x: x['score'], reverse=True)
    if not candidates:
        return {"status": "unknown", "reason": "Нет подходящих подтверждённых примеров"}
    best = candidates[0]
    margin = best['score'] - (candidates[1]['score'] if len(candidates) > 1 else 0)
    enough = best['votes'] >= min(2, len(vectors))
    if best['score'] < MIN_SCORE or margin < MIN_MARGIN or not enough:
        return {"status": "unknown", "reason": "Нет уверенного совпадения"}
    return {"status": "suggested", "profile_id": best['profile_id'], "name": best['name'],
            "score": round(best['score'], 3), "margin": round(margin, 3)}


def report_path(root: Path, path: Path) -> Path:
    return root / ".cache/voice-profiles/reports" / f"{_hash(str(path.resolve()))}.json"


def suggest(root: Path, path: Path) -> dict:
    manifest = _manifest(root, path)
    bank = read_bank(root)
    if not bank['profiles']:
        raise ValueError("Библиотека пуста. Сначала сохраните подтверждённый голос.")
    features = speaker_vectors(root, manifest)
    profiles = [p for p in bank['profiles'] if p['model'] == features['model']]
    names = manifest.get('speaker_names', {})
    rows = []
    for speaker, data in features['speakers'].items():
        match = match_vectors(data['vectors'], profiles, exclude_source=source_key(root, manifest))
        match.update({"speaker": speaker, "current_name": names.get(speaker, '')})
        if match.get('name') and names.get(speaker):
            match['status'] = 'confirmed' if match['name'] == names[speaker] else 'conflict'
            if match['status'] == 'conflict':
                match['reason'] = 'Уже задано другое имя — оно сохранено'
        rows.append(match)
    report = {"version": VERSION, "signature": features['signature'], "bank_revision": _hash(bank),
              "rows": rows, "created_at": time.time()}
    report['revision'] = _hash(report)
    _write(report_path(root, path), report)
    return report


def saved_suggestions(root: Path, path: Path) -> dict | None:
    try:
        report = _read(report_path(root, path))
        if report and report.get('bank_revision') == _hash(read_bank(root)) and report.get('signature') == signature(root, _manifest(root, path)):
            # Applied names may have changed since prediction.
            names = _manifest(root, path).get('speaker_names', {})
            for row in report['rows']:
                row['current_name'] = names.get(row['speaker'], '')
                if row.get('name') and row['current_name']:
                    row['status'] = 'confirmed' if row['name'] == row['current_name'] else 'conflict'
            return report
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def confirm(root: Path, path: Path, speakers: list[str], revision: str) -> dict:
    from voice_recognizer.cli import rewrite_manifest_exports
    with bank_lock(root), result_lock(root, path):
        report = saved_suggestions(root, path)
        if report is None or not revision or report.get('revision') != revision:
            raise ValueError("Предложения устарели. Нажмите «Узнать голоса» ещё раз.")
        manifest = _manifest(root, path)
        names = dict(manifest.get('speaker_names', {}))
        rows = {r['speaker']: r for r in report['rows']}
        if not speakers:
            raise ValueError("Выберите предложения для подтверждения.")
        for speaker in speakers:
            row = rows.get(str(speaker), {})
            if row.get('status') != 'suggested' or names.get(str(speaker)):
                raise ValueError("Это предложение уже изменилось или у спикера задано имя.")
            names[str(speaker)] = row['name']
        rewrite_manifest_exports(path, speaker_names={int(k) - 1: v for k, v in names.items()})
    # Confirmation applies labels only; it does not train/enroll the predicted voice.
    return {"applied": speakers, "speaker_names": names}
