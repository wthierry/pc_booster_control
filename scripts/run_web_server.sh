#!/usr/bin/env bash
set -eo pipefail

cd /home/booster/pc_booster_control

# Load repo-local environment overrides if present, without shell-eval.
if [[ -f .env ]]; then
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw#"${raw%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    [[ "$line" != *"="* ]] && continue
    if [[ "$line" == export[[:space:]]* ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    key="${line%%=*}"
    val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    if [[ "$val" == \"*\" && "$val" == *\" ]]; then
      val="${val:1:${#val}-2}"
    elif [[ "$val" == \'*\' && "$val" == *\' ]]; then
      val="${val:1:${#val}-2}"
    fi
    [[ -n "$key" ]] && export "$key=$val"
  done < .env
fi

# ROS setup scripts can reference unset vars under non-interactive shells.
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"
source /opt/ros/humble/setup.bash
source /opt/booster/BoosterRos2Interface/install/setup.bash

export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/booster/BoosterRos2/fastdds_profile.xml
export PYTHONPATH=src/pc_booster_control:${PYTHONPATH:-}
export BOOSTER_PIPER_BIN="${BOOSTER_PIPER_BIN:-/home/booster/piper/piper/piper}"
export BOOSTER_PIPER_VOICE_DIR="${BOOSTER_PIPER_VOICE_DIR:-/home/booster/piper/voices}"
export BOOSTER_PIPER_DEFAULT_VOICE="${BOOSTER_PIPER_DEFAULT_VOICE:-en_US-lessac-medium}"
export BOOSTER_PIPER_PLAYBACK_MODE="${BOOSTER_PIPER_PLAYBACK_MODE:-aplay}"
export BOOSTER_PIPER_APLAY_DEVICE="${BOOSTER_PIPER_APLAY_DEVICE:-plughw:CARD=Device,DEV=0}"
export BOOSTER_WEB_HOST="${BOOSTER_WEB_HOST:-0.0.0.0}"
export BOOSTER_WEB_PORT="${BOOSTER_WEB_PORT:-8000}"

exec python3 -m uvicorn pc_booster_control.web_server:app \
  --app-dir src/pc_booster_control \
  --host "${BOOSTER_WEB_HOST}" \
  --port "${BOOSTER_WEB_PORT}"
