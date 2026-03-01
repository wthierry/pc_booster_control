#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "Missing .venv at $REPO_ROOT/.venv"
  echo "Create it with: python3 -m venv .venv"
  exit 1
fi
source .venv/bin/activate

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  OPENAI_API_KEY="$(security find-generic-password -a "$USER" -s OPENAI_API_KEY -w 2>/dev/null || true)"
  export OPENAI_API_KEY
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is empty."
  echo "Set it in shell or keychain service OPENAI_API_KEY."
  exit 1
fi

if [[ -z "${BOOSTER_PIPER_BIN:-}" ]]; then
  BOOSTER_PIPER_BIN="$(command -v piper || true)"
  export BOOSTER_PIPER_BIN
fi
if [[ -z "${BOOSTER_PIPER_BIN:-}" ]]; then
  echo "Piper binary not found in PATH."
  echo "Install piper or export BOOSTER_PIPER_BIN=/full/path/to/piper"
  exit 1
fi

export BOOSTER_PIPER_VOICE_DIR="${BOOSTER_PIPER_VOICE_DIR:-$REPO_ROOT/piper/voices}"
export BOOSTER_PIPER_DEFAULT_VOICE="${BOOSTER_PIPER_DEFAULT_VOICE:-en_US-lessac-medium}"
export BOOSTER_PIPER_PLAYBACK_MODE="${BOOSTER_PIPER_PLAYBACK_MODE:-afplay}"

export BOOSTER_WEB_HOST="${BOOSTER_WEB_HOST:-127.0.0.1}"
export BOOSTER_WEB_PORT="${BOOSTER_WEB_PORT:-8000}"
export PYTHONPATH="src/pc_booster_control:${PYTHONPATH:-}"

echo "Starting local web server on http://${BOOSTER_WEB_HOST}:${BOOSTER_WEB_PORT}"
echo "Piper: $BOOSTER_PIPER_BIN"
echo "Voice dir: $BOOSTER_PIPER_VOICE_DIR"
echo "Playback mode: $BOOSTER_PIPER_PLAYBACK_MODE"

exec python -m uvicorn pc_booster_control.web_server:app \
  --host "$BOOSTER_WEB_HOST" \
  --port "$BOOSTER_WEB_PORT"
