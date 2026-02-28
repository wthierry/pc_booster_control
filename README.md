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
python -m uvicorn pc_booster_control.web_server:app --app-dir src/pc_booster_control --host 127.0.0.1 --port 8000
```

Open: `http://127.0.0.1:8000`

## Run with ROS2 workspace

```bash
cd /Users/wthierry/Development/pc_booster_control
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select booster_interface pc_booster_control
source install/setup.bash
ros2 run pc_booster_control booster_web
```

## Useful env vars

```bash
export BOOSTER_COLOR_TOPIC=/StereoNetNode/rectified_image
export BOOSTER_DEPTH_TOPIC=/StereoNetNode/stereonet_depth
export BOOSTER_WEB_HOST=127.0.0.1
export BOOSTER_WEB_PORT=8000
```
