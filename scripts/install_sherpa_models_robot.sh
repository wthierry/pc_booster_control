#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${1:-/home/booster/sherpa-onnx-models}"
ASR_URL="${2:-https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2}"

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

archive="$(basename "$ASR_URL")"
model_dir="${archive%.tar.bz2}"

if [[ -d "$model_dir" ]]; then
  echo "Model already present: $BASE_DIR/$model_dir"
  exit 0
fi

echo "Downloading $ASR_URL"
curl -fL --retry 3 -o "$archive" "$ASR_URL"
tar -xjf "$archive"
rm -f "$archive"

echo "Installed: $BASE_DIR/$model_dir"
