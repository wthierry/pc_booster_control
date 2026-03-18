# pc_booster_control

PC-side camera viewer for Booster K1.

Current goal implemented here:
- Run a local HTML interface
- Display robot color/depth camera streams
- Keep the interface read-only (no movement/head control commands)

## Workspace layout

- `src/booster_robotics_sdk_ros2`: cloned Booster ROS2 SDK repo
- `src/pc_booster_control`: custom package with camera web app

## Web app features

- `GET /` serves the camera viewer UI
- `GET /stream/color` MJPEG from `/StereoNetNode/rectified_image`
- `GET /stream/depth` MJPEG from `/StereoNetNode/stereonet_depth`
- `GET /api/health` camera/ROS status

## Run on Mac now (before robot connection)

```bash
cd /Users/wthierry/Development/pc_booster_control
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn numpy opencv-python
PYTHONPATH=src/pc_booster_control python -m uvicorn pc_booster_control.web_server:app --host 127.0.0.1 --port 8000
```

Open: `http://127.0.0.1:8000`

### Local Chat + Piper speech on Mac

The same web UI `/api/speak` flow can be tested locally on macOS.

Quick start:

```bash
./scripts/run_local_mac.sh
```

Manual setup:

```bash
cd /Users/wthierry/Development/pc_booster_control
source .venv/bin/activate

# Required for OpenAI responses
export OPENAI_API_KEY=your_key_here

# Point to local Piper setup (if not already discoverable in PATH)
export BOOSTER_PIPER_BIN="$(command -v piper)"
export BOOSTER_PIPER_VOICE_DIR="/Users/wthierry/Development/pc_booster_control/piper/voices"
export BOOSTER_PIPER_DEFAULT_VOICE="en_US-lessac-medium"

# Optional: force macOS speaker playback via afplay
export BOOSTER_PIPER_PLAYBACK_MODE=afplay

PYTHONPATH=src/pc_booster_control python -m uvicorn pc_booster_control.web_server:app --host 127.0.0.1 --port 8000
```

Notes:
- Robot deployment is unchanged: robot scripts/services still use their existing Linux paths and `aplay`.
- On macOS, playback mode `auto` now tries `aplay` then `afplay`, then returns browser-playable audio.

### Sherpa ASR model notes

The repo does not commit Sherpa model binaries. Keep them downloaded locally and point
`BOOSTER_SHERPA_ASR_MODEL_DIR` at the extracted model directory instead.

Expected model directory:

```bash
sherpa-models/sherpa-onnx-streaming-zipformer-en-2023-06-26
```

Key files expected in that directory:

```text
tokens.txt
bpe.model
encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx
decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx
joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx
```

Local Mac setup example:

```bash
cd /Users/wthierry/Development/pc_booster_control
mkdir -p sherpa-models
cd sherpa-models
curl -fL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2
tar -xjf sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2
rm -f sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2
export BOOSTER_SHERPA_ASR_MODEL_DIR=/Users/wthierry/Development/pc_booster_control/sherpa-models/sherpa-onnx-streaming-zipformer-en-2023-06-26
```

## Run with ROS2 workspace

```bash
cd /Users/wthierry/Development/pc_booster_control
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select booster_interface pc_booster_control
source install/setup.bash
ros2 run pc_booster_control booster_web
```

## Deploy/update on robot

```bash
# from your Mac
cd /Users/wthierry/Development/pc_booster_control
rsync -av --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  ./ booster@192.168.5.149:/home/booster/pc_booster_control/
```

On robot, ensure `.env` exists (copy from `.env.robot.example` and fill `OPENAI_API_KEY`):

```bash
ssh booster@192.168.5.149
cd /home/booster/pc_booster_control
cp -n .env.robot.example .env
```

Default robot account:
- User: `booster`
- Default password: `123456`

Then restart service:

```bash
ssh booster@192.168.5.149 'sudo systemctl restart pc_booster_web.service && systemctl is-active pc_booster_web.service'
```

## Conversation daemon (wake word + STT + OpenAI + Piper)

Daemon entrypoint:

```bash
python -m pc_booster_control.conversation_daemon
```

Required environment (robot `.env`):

```bash
BOOSTER_SHERPA_KWS_CMD="<command that blocks until wake word>"
BOOSTER_SHERPA_STT_CMD="<command that captures one utterance and prints transcript>"
BOOSTER_CONVERSATION_WAKE_WORD=hal
OPENAI_API_KEY=sk-...
```

Recommended robot setup in this repo:

```bash
cd /home/booster/pc_booster_control
python3 -m pip install --user sherpa-onnx
chmod +x scripts/install_sherpa_models_robot.sh scripts/sherpa_wake_once.py scripts/sherpa_asr_once.py
./scripts/install_sherpa_models_robot.sh
```

Then set in `/home/booster/pc_booster_control/.env`:

```bash
BOOSTER_SHERPA_DEVICE_NAME=plughw:CARD=Device,DEV=0
BOOSTER_SHERPA_ASR_MODEL_DIR=/home/booster/sherpa-onnx-models/sherpa-onnx-streaming-zipformer-en-2023-06-26
BOOSTER_SHERPA_WAKE_ALIASES=hal,hell,hall,howl
BOOSTER_SHERPA_KWS_CMD=python3 scripts/sherpa_wake_once.py --wake-word "{wake_word}"
BOOSTER_SHERPA_STT_CMD=python3 scripts/sherpa_asr_once.py
```

Command contract:
- Wake command exits `0` when wake word is detected.
- STT command exits `0` and prints transcript text to stdout (last line used).
- `BOOSTER_SHERPA_KWS_CMD` may include `{wake_word}` and it will be replaced from `BOOSTER_CONVERSATION_WAKE_WORD`.
- Daemon plays a short beep when wake word is detected (configurable via `BOOSTER_CONVERSATION_WAKE_BEEP_*`).

Robot service files:
- `scripts/run_conversation_daemon.sh`
- `deploy/systemd/pc_booster_conversation.service`

Enable on robot:

```bash
ssh booster@192.168.5.149
cd /home/booster/pc_booster_control
chmod +x scripts/run_conversation_daemon.sh
sudo cp deploy/systemd/pc_booster_conversation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pc_booster_conversation.service
systemctl status --no-pager pc_booster_conversation.service
```

## Useful env vars

```bash
export BOOSTER_COLOR_TOPIC=/StereoNetNode/rectified_image
export BOOSTER_DEPTH_TOPIC=/StereoNetNode/stereonet_depth
export BOOSTER_WEB_HOST=127.0.0.1
export BOOSTER_WEB_PORT=8000
```
