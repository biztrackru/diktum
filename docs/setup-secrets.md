# Setup Secrets

## Hugging Face Token

Нужен для pyannote Community-1, то есть для разделения записи по спикерам.
ASR и web UI можно установить без него, но speaker diarization будет не готова.

1. Зайти на https://huggingface.co/pyannote/speaker-diarization-community-1.
2. Войти в Hugging Face.
3. Принять условия доступа к модели или отправить запрос на доступ, если Hugging Face показывает gated access.
4. Создать токен на https://huggingface.co/settings/tokens.
5. Достаточно токена с read-доступом.
6. Для семейного или внешнего теста лучше создать отдельный read-only token, например `voice-recognizer-family-test`.
7. Передавать token отдельно от install pack и не вкладывать его в zip, README, чат, screenshots или issue.
8. Создать локальный файл `.env` из `app/.env.example`.
9. Вписать токен в `.env`:

```bash
HF_TOKEN=hf_your_token_here
```

Файл `.env` добавлен в `.gitignore`.
Если token создавался только для тестовой установки на другом Mac, его можно отозвать после проверки в Hugging Face settings.

```bash
cp app/.env.example .env
```

## How To Load Locally

Перед запуском pyannote-команд:

```bash
set -a
source .env
set +a
```

Проверить, что токен виден, не печатая его:

```bash
python3 - <<'PY'
import os
print(bool(os.environ.get("HF_TOKEN")))
PY
```

Если команда pyannote возвращает `403 Forbidden`, токен найден, но доступ к конкретной модели еще не выдан аккаунту. Нужно открыть страницу модели под тем же Hugging Face аккаунтом и принять/request access.

Быстрая проверка доступа:

```bash
set -a
source .env
set +a
.venv/bin/voice-recognizer check-pyannote-access
```
