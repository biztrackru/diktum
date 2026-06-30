#!/bin/bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

VERSION="2.5.0"
ARCHIVE="gigastt-${VERSION}-aarch64-apple-darwin.tar.gz"
URL="https://github.com/ekhodzitsky/gigastt/releases/download/v${VERSION}/${ARCHIVE}"
EXPECTED_SHA256="7c02bb78f5fc5086f63769d98f1729923bee726aa09deafa053ee2ae5efc6074"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "${APP_DIR}/.." && pwd)"
BIN_DIR="${WORKSPACE_DIR}/tools/bin"
DOWNLOAD_DIR="${WORKSPACE_DIR}/.cache/downloads"
MODEL_DIR="${WORKSPACE_DIR}/.models/gigastt"
PUNCT_DIR="${MODEL_DIR}/punct"
PUNCT_DOWNLOAD_DIR="${DOWNLOAD_DIR}/punct"
PUNCT_BASE_URL="https://huggingface.co/ekhodzitsky/rupunct-small-onnx/resolve/main"

mkdir -p "${BIN_DIR}" "${DOWNLOAD_DIR}" "${MODEL_DIR}" "${PUNCT_DIR}" "${PUNCT_DOWNLOAD_DIR}"

relative_path() {
  local path="$1"
  case "$path" in
    "${WORKSPACE_DIR}"/*)
      printf '%s\n' "${path#"${WORKSPACE_DIR}/"}"
      ;;
    *)
      printf '%s\n' "$path"
      ;;
  esac
}

print_gigastt_inventory() {
  echo
  echo "GigaSTT file inventory"
  echo "----------------------"
  if [[ -x "${BIN_DIR}/gigastt" ]]; then
    echo "[OK] tools/bin/gigastt"
  else
    echo "[MISSING] tools/bin/gigastt"
  fi
  if find "${MODEL_DIR}" -maxdepth 3 \( -type f -o -type l \) -print -quit | grep -q .; then
    find "${MODEL_DIR}" -maxdepth 3 \( -type f -o -type l \) -print | sort | while IFS= read -r path; do
      echo " - $(relative_path "$path")"
    done
  else
    echo " - .models/gigastt/ is empty"
  fi
  echo
}

verify_gigastt_ready() {
  local missing=0
  local required_files=(
    "v3_rnnt_decoder.onnx"
    "v3_rnnt_joint.onnx"
    "v3_vocab.txt"
    "punct/rupunct_small_int8.onnx"
    "punct/config.json"
    "punct/tokenizer.json"
  )
  local file

  if [[ ! -x "${BIN_DIR}/gigastt" ]]; then
    echo "[MISSING] tools/bin/gigastt"
    missing=1
  fi
  if [[ ! -f "${MODEL_DIR}/v3_rnnt_encoder.onnx" && ! -f "${MODEL_DIR}/v3_rnnt_encoder_int8.onnx" ]]; then
    echo "[MISSING] .models/gigastt/v3_rnnt_encoder.onnx or v3_rnnt_encoder_int8.onnx"
    missing=1
  fi
  for file in "${required_files[@]}"; do
    if [[ ! -f "${MODEL_DIR}/${file}" ]]; then
      echo "[MISSING] .models/gigastt/${file}"
      missing=1
    fi
  done

  if [[ "$missing" != "0" ]]; then
    echo
    echo "GigaSTT/GigaAM v3 is not complete yet."
    echo "Run Настроить Диктум.command again and allow stage 4/5."
    return 1
  fi
  return 0
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

download_checked_file() {
  local name="$1"
  local expected_sha256="$2"
  local url="${PUNCT_BASE_URL}/${name}"
  local target="${PUNCT_DIR}/${name}"
  local tmp="${PUNCT_DOWNLOAD_DIR}/${name}.download"
  local actual_sha256

  if [[ -f "$target" ]]; then
    actual_sha256="$(sha256_file "$target")"
    if [[ "$actual_sha256" == "$expected_sha256" ]]; then
      echo "[OK] punct/${name}"
      return 0
    fi
    echo "[WARN] punct/${name} exists but checksum is different. Re-downloading."
  fi

  echo "Скачиваю punct/${name}"
  echo "$url"
  rm -f "$tmp"
  curl -L --fail --retry 3 --connect-timeout 30 --max-time 1800 -o "$tmp" "$url"
  actual_sha256="$(sha256_file "$tmp")"
  if [[ "$actual_sha256" != "$expected_sha256" ]]; then
    echo "SHA-256 mismatch for punct/${name}" >&2
    echo "expected: ${expected_sha256}" >&2
    echo "actual:   ${actual_sha256}" >&2
    rm -f "$tmp"
    return 1
  fi
  mv "$tmp" "$target"
  echo "[OK] punct/${name}"
}

ensure_punct_model() {
  echo
  echo "Скачиваю/проверяю модель пунктуации RUPunct..."
  echo "Источник: ekhodzitsky/rupunct-small-onnx"
  download_checked_file "rupunct_small_int8.onnx" "b105da023474d98aa13ba18953ae67b04b17bd0595034bc06030c17536893933"
  download_checked_file "config.json" "6924a8cf41ec2bd3a3aa73a387ae0ccd0aed253ec7cac4d2f53c7d27440891eb"
  download_checked_file "tokenizer.json" "7ca617388c2092a3a84272025c52bbf3c6db0aee225c0351186295c0b5d3ddc6"
}

# Optional integrity pinning for the main GigaAM v3 model files. They are fetched
# by the gigastt binary (over HTTPS) and are NOT checksum-pinned by default. To
# enable verification: run setup once, copy each printed [UNPINNED] hash into the
# matching entry below, and commit the change.
declare -A EXPECTED_MODEL_SHA256=(
  ["v3_rnnt_encoder_int8.onnx"]=""
  ["v3_rnnt_decoder.onnx"]=""
  ["v3_rnnt_joint.onnx"]=""
  ["v3_vocab.txt"]=""
)

verify_model_checksums() {
  echo
  echo "Проверка целостности основных моделей GigaAM v3..."
  local name path actual expected unpinned=0
  for name in "${!EXPECTED_MODEL_SHA256[@]}"; do
    path="${MODEL_DIR}/${name}"
    if [[ ! -f "$path" ]]; then
      continue
    fi
    actual="$(sha256_file "$path")"
    expected="${EXPECTED_MODEL_SHA256[$name]}"
    if [[ -z "$expected" ]]; then
      echo "  [UNPINNED] ${name}: ${actual}"
      unpinned=1
    elif [[ "$actual" == "$expected" ]]; then
      echo "  [OK] ${name}"
    else
      echo "  [FAIL] ${name}: SHA-256 mismatch" >&2
      echo "    expected: ${expected}" >&2
      echo "    actual:   ${actual}" >&2
      return 1
    fi
  done
  if [[ "$unpinned" == "1" ]]; then
    echo "  ВНИМАНИЕ: основные модели не запинены по SHA-256."
    echo "  Вставьте напечатанные значения в EXPECTED_MODEL_SHA256 в этом скрипте,"
    echo "  чтобы включить проверку целостности при будущих установках."
  fi
  return 0
}

cat <<TXT
GigaSTT / GigaAM v3 setup
-------------------------
Это основной локальный ASR-движок Диктум для русского языка.
Он превращает аудио в текст. Pyannote/HF token нужны отдельно только для
разделения по спикерам.

Сейчас setup подготовит:
- binary: tools/bin/gigastt
- модели: .models/gigastt/
- модель пунктуации: .models/gigastt/punct/
- временные загрузки: .cache/downloads/

Будут скачаны GigaSTT release с GitHub, GigaAM v3 модели через gigastt
и небольшая RUPunct-модель с Hugging Face для пунктуации/регистра.
Это может занять несколько минут и сотни мегабайт. Если сеть оборвется,
запустите "Настроить Диктум.command" еще раз: готовые файлы
будут переиспользованы.

TXT

if [[ ! -x "${BIN_DIR}/gigastt" ]]; then
  echo "Скачиваю GigaSTT binary:"
  echo "${URL}"
  curl -L --fail -o "${DOWNLOAD_DIR}/${ARCHIVE}" "${URL}"
  ACTUAL_SHA256="$(shasum -a 256 "${DOWNLOAD_DIR}/${ARCHIVE}" | awk '{print $1}')"
  if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
    echo "SHA-256 mismatch for ${ARCHIVE}" >&2
    echo "expected: ${EXPECTED_SHA256}" >&2
    echo "actual:   ${ACTUAL_SHA256}" >&2
    exit 1
  fi
  tar -xzf "${DOWNLOAD_DIR}/${ARCHIVE}" -C "${BIN_DIR}"
  chmod +x "${BIN_DIR}/gigastt"
else
  echo "GigaSTT binary уже найден: ${BIN_DIR}/gigastt"
fi

echo "Скачиваю/проверяю GigaAM v3 модели..."
"${BIN_DIR}/gigastt" download --model-dir "${MODEL_DIR}" --prequantized
ensure_punct_model

# gigastt 2.5.0 can download and run the pre-quantized INT8 encoder, but the
# transcribe preflight checks for the FP32 filename. The engine itself prefers
# the INT8 encoder when both names exist, so this symlink avoids a redundant
# 844 MB FP32 download.
ln -sf v3_rnnt_encoder_int8.onnx "${MODEL_DIR}/v3_rnnt_encoder.onnx"

verify_model_checksums

print_gigastt_inventory
verify_gigastt_ready

echo "gigastt is ready: ${BIN_DIR}/gigastt"
echo "models are ready: ${MODEL_DIR}"
