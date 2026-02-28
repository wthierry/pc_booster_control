#!/usr/bin/env bash
set -eo pipefail

cd /home/booster/pc_booster_control

# ROS setup scripts can reference unset vars under non-interactive shells.
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"
source /opt/ros/humble/setup.bash
source /opt/booster/BoosterRos2Interface/install/setup.bash

export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/booster/BoosterRos2/fastdds_profile.xml
export PYTHONPATH=src/pc_booster_control:${PYTHONPATH:-}

exec python3 -m uvicorn pc_booster_control.web_server:app \
  --app-dir src/pc_booster_control \
  --host 0.0.0.0 \
  --port 8000
