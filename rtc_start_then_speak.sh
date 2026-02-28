#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
source /opt/booster/BoosterRos2Interface/install/setup.bash
ros2 service call /booster_rtc_service booster_interface/srv/RpcService '{msg: {api_id: 2000, body: "{\"interrupt_mode\":false,\"asr_config\":{\"interrupt_speech_duration\":200,\"interrupt_keywords\":[\"apple\",\"banana\"]},\"llm_config\":{\"system_prompt\":\"You are Booster K1. Be concise and helpful.\",\"welcome_msg\":\"Hello, I am Booster robot.\",\"prompt_name\":\"\"},\"tts_config\":{\"voice_type\":\"zh_female_shuangkuaisisi_emo_v2_mars_bigtts\",\"ignore_bracket_text\":[3]},\"enable_face_tracking\":false}"}}'
ros2 service call /booster_rtc_service booster_interface/srv/RpcService '{msg: {api_id: 2002, body: "{\"msg\":\"hello from start then speak\"}"}}'
