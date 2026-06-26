#!/usr/bin/env bash
set -euo pipefail

VERSION="2.5.0"
ARCHIVE="gigastt-${VERSION}-aarch64-apple-darwin.tar.gz"
URL="https://github.com/ekhodzitsky/gigastt/releases/download/v${VERSION}/${ARCHIVE}"
EXPECTED_SHA256="7c02bb78f5fc5086f63769d98f1729923bee726aa09deafa053ee2ae5efc6074"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${ROOT_DIR}/tools/bin"
DOWNLOAD_DIR="${ROOT_DIR}/.cache/downloads"
MODEL_DIR="${ROOT_DIR}/.models/gigastt"

mkdir -p "${BIN_DIR}" "${DOWNLOAD_DIR}" "${MODEL_DIR}"

if [[ ! -x "${BIN_DIR}/gigastt" ]]; then
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
fi

"${BIN_DIR}/gigastt" download --model-dir "${MODEL_DIR}" --prequantized

# gigastt 2.5.0 can download and run the pre-quantized INT8 encoder, but the
# transcribe preflight checks for the FP32 filename. The engine itself prefers
# the INT8 encoder when both names exist, so this symlink avoids a redundant
# 844 MB FP32 download.
ln -sf v3_rnnt_encoder_int8.onnx "${MODEL_DIR}/v3_rnnt_encoder.onnx"

echo "gigastt is ready: ${BIN_DIR}/gigastt"
echo "models are ready: ${MODEL_DIR}"
