#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
source /opt/booster/BoosterRos2Interface/install/setup.bash
ros2 service call /booster_rtc_service booster_interface/srv/RpcService '{msg: {api_id: 2002, body: "{\"msg\":\"hello direct\"}"}}'
