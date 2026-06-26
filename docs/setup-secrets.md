# Setup Secrets

## Hugging Face Token

Нужен для загрузки pyannote Community-1.

1. Зайти на https://huggingface.co/pyannote/speaker-diarization-community-1.
2. Войти в Hugging Face.
3. Принять условия доступа к модели или отправить запрос на доступ, если Hugging Face показывает gated access.
4. Создать токен на https://huggingface.co/settings/tokens.
5. Достаточно токена с read-доступом.
6. Создать локальный файл `.env` из `app/.env.example`.
7. Вписать токен в `.env`:

```bash
HF_TOKEN=hf_your_token_here
```

Файл `.env` добавлен в `.gitignore`.

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
