#!/usr/bin/env bash
set -eo pipefail

cd /home/booster/pc_booster_control

export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"
source /opt/ros/humble/setup.bash
source /opt/booster/BoosterRos2Interface/install/setup.bash

export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/booster/BoosterRos2/fastdds_profile.xml
export PYTHONPATH=src/pc_booster_control:${PYTHONPATH:-}
export BOOSTER_PIPER_BIN="${BOOSTER_PIPER_BIN:-/home/booster/piper/piper/piper}"
export BOOSTER_PIPER_VOICE_DIR="${BOOSTER_PIPER_VOICE_DIR:-/home/booster/piper/voices}"
export BOOSTER_PIPER_PLAYBACK_MODE="${BOOSTER_PIPER_PLAYBACK_MODE:-aplay}"
export BOOSTER_PIPER_APLAY_DEVICE="${BOOSTER_PIPER_APLAY_DEVICE:-plughw:CARD=Device,DEV=0}"
export BOOSTER_CONVERSATION_ENABLED="${BOOSTER_CONVERSATION_ENABLED:-1}"
export BOOSTER_CONVERSATION_USE_WAKE_WORD="${BOOSTER_CONVERSATION_USE_WAKE_WORD:-1}"

exec python3 -m pc_booster_control.conversation_daemon
