# Robot Setup Notes (Current)

Date: 2026-03-01

## Access
- Default robot user: `booster`
- Default robot password: `123456`

## Code Sync State
Core project files are hash-matched between local and robot:
- `src/pc_booster_control/pc_booster_control/web_server.py`
- `src/pc_booster_control/pc_booster_control/static/index.html`
- `src/pc_booster_control/pc_booster_control/static/styles.css`
- `src/pc_booster_control/pc_booster_control/static/app.js`
- `scripts/run_web_server.sh`
- `deploy/systemd/pc_booster_web.service`

## Web Service
- Service: `pc_booster_web.service`
- Status: enabled/active
- Starts at boot and runs the FastAPI web app.

## Speech/TTS (Current)
- Booster RTC chat/mic services disabled at system level:
  - `booster-rtc-speech.service` -> disabled/inactive
  - `booster-lui.service` -> disabled/inactive
- Web app speech uses local Piper (offline), not Booster RTC chat.

## Piper Install (Robot)
- Binary: `/home/booster/piper/piper/piper`
- Voice model: `/home/booster/piper/voices/en_US-lessac-medium.onnx`
- Voice config: `/home/booster/piper/voices/en_US-lessac-medium.onnx.json`
- Backend defaults:
  - `BOOSTER_PIPER_BIN=/home/booster/piper/piper/piper`
  - `BOOSTER_PIPER_VOICE_DIR=/home/booster/piper/voices`
  - `BOOSTER_PIPER_DEFAULT_VOICE=en_US-lessac-medium`
  - `BOOSTER_PIPER_APLAY_DEVICE=plughw:CARD=Device,DEV=0`

## Audio Indicator
- UI polls `/api/audio/activity`.
- Blinks red only when measured audio level exceeds threshold.
- Busy/unavailable mic states are shown without red blinking.

## Useful Robot Commands
- Service status: `systemctl is-active pc_booster_web.service`
- Restart web app: `sudo systemctl restart pc_booster_web.service`
- Health: `curl -s http://127.0.0.1:8000/api/health`
- Speak test: `curl -s -X POST http://127.0.0.1:8000/api/speak -H 'Content-Type: application/json' -d '{"text":"hello"}'`
- Debug stream: `curl -s 'http://127.0.0.1:8000/api/debug?since=0&limit=60'`
