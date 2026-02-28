import os
import shlex
import subprocess
import threading
import time
import re
import json
import struct
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

ROS_IMPORT_ERROR: str | None = None
ROS_AVAILABLE = True
try:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor

    from .web_bridge import RosWebBridge
except Exception as exc:  # pragma: no cover - runtime environment dependent
    ROS_AVAILABLE = False
    ROS_IMPORT_ERROR = str(exc)
    rclpy = None  # type: ignore[assignment]
    MultiThreadedExecutor = Any  # type: ignore[misc,assignment]
    RosWebBridge = Any  # type: ignore[misc,assignment]


DEFAULT_COLOR_TOPIC = os.environ.get("BOOSTER_COLOR_TOPIC", "/StereoNetNode/rectified_image")
DEFAULT_DEPTH_TOPIC = os.environ.get("BOOSTER_DEPTH_TOPIC", "/StereoNetNode/stereonet_depth")
BATTERY_SYSFS_DIR = Path("/sys/class/power_supply/battery")
SDK_BATTERY_HELPER_PATH = Path(
    os.environ.get("BOOSTER_SDK_BATTERY_HELPER", "/home/booster/pc_booster_control/battery_soc_once")
)
DEFAULT_RPC_SERVICE = os.environ.get("BOOSTER_RPC_SERVICE", "/booster_rpc_service")
DEFAULT_RTC_SERVICE = os.environ.get("BOOSTER_RTC_SERVICE", "/booster_rtc_service")
CHANGE_MODE_API_ID = int(os.environ.get("BOOSTER_CHANGE_MODE_API_ID", "2000"))
DAMP_MODE_VALUE = int(os.environ.get("BOOSTER_MODE_DAMP", "0"))
PREP_MODE_VALUE = int(os.environ.get("BOOSTER_MODE_PREP", "1"))
DEBUG_LOG_MAX_LINES = int(os.environ.get("BOOSTER_DEBUG_LOG_MAX_LINES", "1200"))
BASHRC_PATH = Path(os.environ.get("BOOSTER_BASHRC_PATH", str(Path.home() / ".bashrc")))
PIPER_BIN = Path(os.environ.get("BOOSTER_PIPER_BIN", "/home/booster/piper/piper/piper"))
PIPER_VOICE_DIR = Path(os.environ.get("BOOSTER_PIPER_VOICE_DIR", "/home/booster/piper/voices"))
DEFAULT_PIPER_VOICE = os.environ.get("BOOSTER_PIPER_DEFAULT_VOICE", "en_US-lessac-medium")
PIPER_APLAY_DEVICE = os.environ.get("BOOSTER_PIPER_APLAY_DEVICE", "plughw:CARD=Device,DEV=0")

# From Booster SDK b1_api_const.hpp::JointIndex (kJointCnt = 23)
B1_JOINT_NAMES: list[str] = [
    "HeadYaw",
    "HeadPitch",
    "LeftShoulderPitch",
    "LeftShoulderRoll",
    "LeftElbowPitch",
    "LeftElbowYaw",
    "RightShoulderPitch",
    "RightShoulderRoll",
    "RightElbowPitch",
    "RightElbowYaw",
    "Waist",
    "LeftHipPitch",
    "LeftHipRoll",
    "LeftHipYaw",
    "LeftKneePitch",
    "CrankUpLeft",
    "CrankDownLeft",
    "RightHipPitch",
    "RightHipRoll",
    "RightHipYaw",
    "RightKneePitch",
    "CrankUpRight",
    "CrankDownRight",
]


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice_type: str | None = None


class VolumeRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class MicrophoneRequest(BaseModel):
    enabled: bool


class CommandRequest(BaseModel):
    cmd: str = Field(min_length=1, max_length=600)
    timeout_sec: int = Field(default=12, ge=1, le=60)


class WebAppState:
    def __init__(self) -> None:
        self.bridge: RosWebBridge | None = None
        self.executor: MultiThreadedExecutor | None = None
        self.spin_thread: threading.Thread | None = None
        self.mode_ui_state: str = "damp"
        self.battery_cache_pct: int | None = None
        self.battery_cache_source: str = "unknown"
        self.battery_cache_ts: float = 0.0
        self.ai_chat_initialized: bool = False
        self.ai_chat_ready: bool = False
        self.ai_chat_starting: bool = False
        self.ai_chat_error: str | None = None
        self.ai_voice_type: str | None = None
        self.mic_enabled: bool = False
        self.motors_cache: list[dict[str, Any]] = []
        self.motors_cache_source: str = "/low_state"
        self.motors_cache_error: str | None = None
        self.motors_cache_ts: float = 0.0
        self.audio_level: float = 0.0
        self.audio_active: bool = False
        self.audio_error: str | None = None
        self.audio_ts: float = 0.0
        self.audio_capture_lock = threading.Lock()
        self.debug_lock = threading.Lock()
        self.debug_lines: deque[tuple[int, str]] = deque(maxlen=max(100, DEBUG_LOG_MAX_LINES))
        self.debug_next_id: int = 1


state = WebAppState()
app = FastAPI(title="Booster K1 Camera Viewer")

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def _startup() -> None:
    _debug_log("web server startup")
    if ROS_AVAILABLE:
        rclpy.init(args=None)
        bridge = RosWebBridge(color_topic=DEFAULT_COLOR_TOPIC, depth_topic=DEFAULT_DEPTH_TOPIC)

        executor = MultiThreadedExecutor()
        executor.add_node(bridge)

        spin_thread = threading.Thread(target=executor.spin, daemon=True)
        spin_thread.start()

        state.bridge = bridge
        state.executor = executor
        state.spin_thread = spin_thread

    piper_ready, piper_error = _piper_ready_state()
    state.ai_chat_initialized = piper_ready
    state.ai_chat_ready = piper_ready
    state.ai_chat_starting = False
    state.ai_chat_error = piper_error
    state.ai_voice_type = DEFAULT_PIPER_VOICE if piper_ready else None
    state.mic_enabled = False
    if piper_ready:
        _debug_log(f"piper ready: {DEFAULT_PIPER_VOICE}")
    else:
        _debug_log(f"piper unavailable: {piper_error}")


@app.on_event("shutdown")
def _shutdown() -> None:
    if not ROS_AVAILABLE:
        return

    if state.executor is not None:
        state.executor.shutdown()
    if state.bridge is not None:
        state.bridge.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    has_color = False
    has_depth = False
    if ROS_AVAILABLE and state.bridge is not None:
        has_color = state.bridge.get_frame_jpeg("color") is not None
        has_depth = state.bridge.get_frame_jpeg("depth") is not None

    battery_percent, battery_source = _read_battery_percent()
    battery_status = _read_battery_text("status")
    volume_percent, volume_source = _read_volume_percent()
    volume_bashrc_default = _read_volume_percent_from_bashrc()
    if volume_percent is None and volume_bashrc_default is not None:
        volume_percent = volume_bashrc_default
        volume_source = "bashrc:vol_default"

    piper_ready, piper_error = _piper_ready_state()
    return {
        "ok": True,
        "ros_available": ROS_AVAILABLE,
        "ros_import_error": ROS_IMPORT_ERROR,
        "color_topic": DEFAULT_COLOR_TOPIC,
        "depth_topic": DEFAULT_DEPTH_TOPIC,
        "has_color_frame": has_color,
        "has_depth_frame": has_depth,
        "battery_percent": battery_percent,
        "battery_status": battery_status,
        "battery_source": battery_source,
        "volume_percent": volume_percent,
        "volume_source": volume_source,
        "volume_bashrc_default": volume_bashrc_default,
        "ai_ready": piper_ready,
        "ai_starting": False,
        "ai_error": piper_error,
        "ai_voice_type": DEFAULT_PIPER_VOICE if piper_ready else None,
        "mic_enabled": False,
        "motors_count": len(state.motors_cache),
        "motors_error": state.motors_cache_error,
        "mode_ui_state": state.mode_ui_state,
        "mode_control": {
            "rpc_service": DEFAULT_RPC_SERVICE,
            "change_mode_api_id": CHANGE_MODE_API_ID,
            "damp_value": DAMP_MODE_VALUE,
            "prep_value": PREP_MODE_VALUE,
        },
    }


@app.get("/api/debug")
def debug_lines(since: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    lines, next_id = _debug_snapshot(since=since, limit=limit)
    return {"ok": True, "lines": lines, "next": next_id}


@app.get("/api/audio/activity")
def audio_activity() -> dict[str, Any]:
    level, active, error = _read_audio_activity_cached()
    return {
        "ok": error is None,
        "active": active,
        "level": level,
        "threshold": 0.02,
        "device": "ALSA default capture",
        "error": error,
    }


@app.post("/api/command")
def run_command(req: CommandRequest) -> dict[str, Any]:
    cmd = req.cmd.strip()
    if not cmd:
        return {"ok": False, "error": "command is empty"}
    rc, out = _run_shell(cmd, timeout_sec=req.timeout_sec)
    return {
        "ok": rc == 0,
        "rc": rc,
        "cmd": cmd,
        "timeout_sec": req.timeout_sec,
        "output": _truncate_debug(out.strip(), max_chars=8000) if out else "",
    }


@app.post("/api/mode/{target}")
def set_mode(target: str) -> dict[str, Any]:
    normalized = target.strip().lower()
    if normalized not in ("damp", "prep"):
        return {"ok": False, "error": "target must be damp or prep"}

    if state.mode_ui_state == normalized:
        return {"ok": True, "already": True, "mode_ui_state": state.mode_ui_state}

    mode_value = DAMP_MODE_VALUE if normalized == "damp" else PREP_MODE_VALUE
    rpc_result = _call_change_mode_rpc(mode_value)
    if not rpc_result.get("ok"):
        return {
            "ok": False,
            "error": rpc_result.get("error", "mode switch failed"),
            "mode_ui_state": state.mode_ui_state,
        }

    state.mode_ui_state = normalized
    return {"ok": True, "mode_ui_state": state.mode_ui_state, "rpc_result": rpc_result}


@app.post("/api/speak")
def speak(req: SpeakRequest) -> dict[str, Any]:
    text = req.text.strip()
    if not text:
        return {"ok": False, "error": "text is empty"}

    voice = (req.voice_type or "").strip() or DEFAULT_PIPER_VOICE
    ok, error, voice_id = _speak_with_piper(text, voice)
    if not ok:
        _debug_log(f"piper speak failed: {error}")
        return {"ok": False, "error": error, "voice_used": voice_id}
    return {"ok": True, "voice_used": voice_id}


@app.get("/api/volume")
def get_volume() -> dict[str, Any]:
    percent, source = _read_volume_percent()
    bashrc_default = _read_volume_percent_from_bashrc()
    if percent is None and bashrc_default is not None:
        percent = bashrc_default
        source = "bashrc:vol_default"
    return {
        "ok": percent is not None,
        "percent": percent,
        "source": source,
        "bashrc_default": bashrc_default,
    }


@app.post("/api/volume")
def set_volume(req: VolumeRequest) -> dict[str, Any]:
    ok, source, error = _set_volume_percent(req.percent)
    percent, read_source = _read_volume_percent()
    return {
        "ok": ok,
        "requested_percent": req.percent,
        "percent": percent,
        "source": source,
        "read_source": read_source,
        "error": error,
    }


@app.post("/api/microphone")
def set_microphone(req: MicrophoneRequest) -> dict[str, Any]:
    _debug_log("microphone toggle rejected: speech engine disabled")
    return {
        "ok": False,
        "enabled": False,
        "error": "speech engine disabled",
    }


@app.get("/api/motors")
def motors() -> dict[str, Any]:
    motors_data, source, error = _read_motors_cached()
    return {
        "ok": motors_data is not None,
        "topic": "/low_state",
        "source": source,
        "error": error,
        "count": len(motors_data or []),
        "motors": motors_data or [],
    }


def _debug_log(message: str) -> None:
    ts = time.strftime("%H:%M:%S")
    text = (message or "").rstrip("\n")
    if not text:
        return
    with state.debug_lock:
        for part in text.splitlines():
            state.debug_lines.append((state.debug_next_id, f"[{ts}] {part}"))
            state.debug_next_id += 1


def _debug_snapshot(since: int, limit: int) -> tuple[list[str], int]:
    with state.debug_lock:
        rows = [line for seq, line in state.debug_lines if seq > since]
        next_id = state.debug_next_id
    if len(rows) > limit:
        rows = rows[-limit:]
    return rows, next_id


def _truncate_debug(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated {len(text) - max_chars} chars]"


def _read_battery_text(name: str) -> str | None:
    path = BATTERY_SYSFS_DIR / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _read_motors_cached() -> tuple[list[dict[str, Any]] | None, str, str | None]:
    now = time.monotonic()
    if (now - state.motors_cache_ts) < 1.5 and state.motors_cache:
        return state.motors_cache, state.motors_cache_source, state.motors_cache_error

    motors_data, source, error = _read_motors_once()
    state.motors_cache_ts = now
    state.motors_cache_source = source
    state.motors_cache_error = error
    if motors_data is not None:
        state.motors_cache = motors_data
    return state.motors_cache if state.motors_cache else motors_data, source, error


def _read_motors_once() -> tuple[list[dict[str, Any]] | None, str, str | None]:
    cmd = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
        "ros2 topic echo --once /low_state"
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except Exception as exc:
        _debug_log(f"$ {cmd}")
        _debug_log(f"motor read exception: {exc}")
        return None, "/low_state", str(exc)

    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        _debug_log(f"$ {cmd}")
        _debug_log(f"motor read rc={proc.returncode}")
        if out.strip():
            _debug_log(_truncate_debug(out.strip()))
        return None, "/low_state", out.strip() or f"rc={proc.returncode}"

    text = proc.stdout or ""
    motors_data = _parse_low_state_motors(text)
    if not motors_data:
        return None, "/low_state", "no motor data parsed"
    return motors_data, "/low_state", None


def _parse_low_state_motors(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    parsed: dict[str, list[dict[str, Any]]] = {"parallel": [], "serial": []}
    for section in ("motor_state_parallel", "motor_state_serial"):
        entries = _extract_low_state_section_entries(lines, section)
        prefix = "P" if section.endswith("parallel") else "S"
        group = "parallel" if section.endswith("parallel") else "serial"
        for idx, entry in enumerate(entries):
            q = _to_float(entry.get("q"))
            temp = _to_int(entry.get("temperature"))
            mode = _to_int(entry.get("mode"))
            if q is None and temp is None:
                continue
            joint_name = _joint_name_for_index(idx)
            parsed[group].append(
                {
                    "name": joint_name,
                    "raw_id": f"{prefix}{idx:02d}",
                    "group": group,
                    "index": idx,
                    "position_rad": q,
                    "temperature_c": temp,
                    "mode": mode,
                }
            )

    parallel = parsed["parallel"]
    serial = parsed["serial"]
    if parallel:
        # Prefer the parallel set for display; serial often duplicates positions with temp=0.
        return parallel
    return serial


def _joint_name_for_index(idx: int) -> str:
    if 0 <= idx < len(B1_JOINT_NAMES):
        return B1_JOINT_NAMES[idx]
    return f"Joint{idx}"


def _extract_low_state_section_entries(lines: list[str], section: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    in_section = False
    current: dict[str, str] | None = None

    for line in lines:
        if not in_section:
            if line.startswith(section + ":"):
                in_section = True
            continue

        # End of section at next top-level key.
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:\s*$", line):
            if current:
                entries.append(current)
            break

        stripped = line.lstrip()
        if stripped.startswith("- "):
            if current:
                entries.append(current)
            current = {}
            remainder = stripped[2:]
            if ":" in remainder:
                k, v = remainder.split(":", 1)
                current[k.strip()] = v.strip()
            continue

        if current is None:
            continue
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        current[k.strip()] = v.strip()

    if in_section and current:
        entries.append(current)
    return entries


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _read_battery_int(name: str) -> int | None:
    text = _read_battery_text(name)
    if text is None:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _read_battery_percent() -> tuple[int | None, str]:
    sdk_pct = _read_battery_percent_from_sdk_binary_cached()
    if sdk_pct is not None:
        return sdk_pct, "sdk:BatteryState.soc"

    topic_pct = _read_battery_percent_from_topic_cached()
    if topic_pct is not None:
        return topic_pct, "topic:/battery_state.soc"

    # Some firmware reports capacity=100 while discharging; derive from raw counters first.
    charge_counter = _read_battery_int("charge_counter")
    charge_full_design = _read_battery_int("charge_full_design")
    if (
        charge_counter is not None
        and charge_full_design is not None
        and charge_full_design > 0
    ):
        pct = int(round((100.0 * float(charge_counter)) / float(charge_full_design)))
        return max(0, min(100, pct)), "charge_counter/charge_full_design"

    capacity = _read_battery_int("capacity")
    if capacity is not None:
        return max(0, min(100, capacity)), "capacity"

    return None, "unavailable"


def _read_battery_percent_from_sdk_binary_cached() -> int | None:
    now = time.monotonic()
    if (now - state.battery_cache_ts) < 8.0 and state.battery_cache_source == "sdk":
        return state.battery_cache_pct

    pct = _read_battery_percent_from_sdk_binary_once()
    if pct is None:
        return None
    state.battery_cache_pct = pct
    state.battery_cache_source = "sdk"
    state.battery_cache_ts = now
    return pct


def _read_battery_percent_from_sdk_binary_once() -> int | None:
    if not SDK_BATTERY_HELPER_PATH.exists():
        return None

    cmd = (
        "export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/booster/BoosterRos2/fastdds_profile.xml && "
        "export LD_LIBRARY_PATH=/home/booster/booster_robotics_sdk/lib/aarch64:"
        "/home/booster/booster_robotics_sdk/third_party/lib/aarch64:$LD_LIBRARY_PATH && "
        + shlex.quote(str(SDK_BATTERY_HELPER_PATH))
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    text = (proc.stdout or "").strip().splitlines()
    if not text:
        return None
    try:
        pct = int(round(float(text[-1].strip())))
    except Exception:
        return None
    return max(0, min(100, pct))


def _read_battery_percent_from_topic_cached() -> int | None:
    now = time.monotonic()
    if (now - state.battery_cache_ts) < 8.0 and state.battery_cache_source == "topic":
        return state.battery_cache_pct

    pct = _read_battery_percent_from_topic_once()
    state.battery_cache_ts = now
    if pct is not None:
        state.battery_cache_pct = pct
        state.battery_cache_source = "topic"
    return state.battery_cache_pct


def _read_battery_percent_from_topic_once() -> int | None:
    cmd = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
        "ros2 topic echo --once /battery_state"
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    text = proc.stdout or ""
    # Supports either "soc: 72.3" or "soc : 72.3"
    match = re.search(r"\bsoc\s*:\s*([0-9]+(?:\\.[0-9]+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        pct = int(round(float(match.group(1))))
    except Exception:
        return None
    return max(0, min(100, pct))


def _call_change_mode_rpc(mode_value: int) -> dict[str, Any]:
    return _call_rpc_service(
        service=DEFAULT_RPC_SERVICE,
        api_id=CHANGE_MODE_API_ID,
        body={"mode": mode_value},
    )


def _call_rpc_service(
    service: str, api_id: int, body: dict[str, Any], timeout_sec: int = 8
) -> dict[str, Any]:
    body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload = "{msg: {api_id: " + str(api_id) + ", body: " + shlex.quote(body_json) + "}}"
    cmd = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
        "ros2 service call "
        + shlex.quote(service)
        + " booster_interface/srv/RpcService "
        + shlex.quote(payload)
    )
    _debug_log(f"$ {cmd}")
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except Exception as exc:
        _debug_log(f"rpc exception: {exc}")
        return {"ok": False, "error": str(exc)}

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        _debug_log(f"rpc rc={proc.returncode}")
        if out.strip():
            _debug_log(_truncate_debug(out.strip()))
        return {"ok": False, "error": out.strip() or f"rc={proc.returncode}"}

    if out.strip():
        _debug_log(_truncate_debug(out.strip()))
    return {"ok": True, "output": out.strip()}


def _run_shell(cmd: str, timeout_sec: int = 4) -> tuple[int, str]:
    _debug_log(f"$ {cmd}")
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except Exception as exc:
        _debug_log(f"shell exception: {exc}")
        return 1, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        _debug_log(_truncate_debug(out.strip()))
    return proc.returncode, out


def _read_audio_activity_cached() -> tuple[float, bool, str | None]:
    now = time.monotonic()
    if (now - state.audio_ts) < 0.35:
        return state.audio_level, state.audio_active, state.audio_error

    if not state.audio_capture_lock.acquire(blocking=False):
        # Another request is already sampling audio; use latest cached snapshot.
        return state.audio_level, state.audio_active, state.audio_error
    try:
        level, error = _read_audio_level_once()
        active = level >= 0.02
        state.audio_level = level
        state.audio_active = active
        state.audio_error = error
        state.audio_ts = now
        return level, active, error
    finally:
        state.audio_capture_lock.release()



def _read_audio_level_once() -> tuple[float, str | None]:
    devices = [
        "default",
        "plughw:CARD=XFMDPV0018,DEV=0",
        "hw:CARD=XFMDPV0018,DEV=0",
    ]
    data = b""
    last_error: str | None = None
    for dev in devices:
        cmd = f"timeout 0.30 arecord -q -D {shlex.quote(dev)} -f S16_LE -c 1 -r 8000 -t raw"
        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True,
                timeout=2.0,
                check=False,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        data = proc.stdout or b""
        if len(data) >= 4:
            break
        err_text = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
        if err_text:
            last_error = err_text

    if len(data) < 4:
        return 0.0, last_error or "no capture data"

    nbytes = (len(data) // 2) * 2
    if nbytes <= 0:
        return 0.0, "invalid capture data"

    total_abs = 0
    count = 0
    for (sample,) in struct.iter_unpack("<h", data[:nbytes]):
        total_abs += abs(int(sample))
        count += 1

    if count == 0:
        return 0.0, "empty sample set"

    level = float(total_abs) / float(count) / 32768.0
    return max(0.0, min(1.0, level)), None


def _piper_ready_state() -> tuple[bool, str | None]:
    if not PIPER_BIN.exists():
        return False, f"piper binary not found: {PIPER_BIN}"
    model = PIPER_VOICE_DIR / f"{DEFAULT_PIPER_VOICE}.onnx"
    config = PIPER_VOICE_DIR / f"{DEFAULT_PIPER_VOICE}.onnx.json"
    if not model.exists():
        return False, f"piper model missing: {model}"
    if not config.exists():
        return False, f"piper config missing: {config}"
    return True, None


def _resolve_piper_voice(voice: str) -> tuple[Path | None, Path | None, str]:
    voice_id = voice.strip() or DEFAULT_PIPER_VOICE
    model = PIPER_VOICE_DIR / f"{voice_id}.onnx"
    config = PIPER_VOICE_DIR / f"{voice_id}.onnx.json"
    if model.exists() and config.exists():
        return model, config, voice_id
    return None, None, voice_id


def _read_sample_rate_from_piper_config(config_path: Path) -> int:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        audio = payload.get("audio", {})
        sr = int(audio.get("sample_rate", 22050))
        if 8000 <= sr <= 96000:
            return sr
    except Exception:
        pass
    return 22050


def _speak_with_piper(text: str, voice: str) -> tuple[bool, str | None, str]:
    ready, ready_err = _piper_ready_state()
    if not ready:
        return False, ready_err, voice

    model, config, voice_id = _resolve_piper_voice(voice)
    if model is None or config is None:
        return False, f"piper voice not found: {voice_id}", voice_id

    piper_cmd_base = [str(PIPER_BIN), "--model", str(model), "--config", str(config)]
    try:
        with tempfile.NamedTemporaryFile(prefix="piper_", suffix=".wav", delete=True) as wav_file:
            piper_cmd = piper_cmd_base + ["--output_file", wav_file.name]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in piper_cmd)}")
            piper_proc = subprocess.run(
                piper_cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=25,
                check=False,
            )
            piper_stderr = (piper_proc.stderr or b"").decode("utf-8", errors="ignore")
            if piper_proc.returncode != 0:
                return False, piper_stderr.strip() or f"piper rc={piper_proc.returncode}", voice_id

            aplay_cmd = ["aplay", "-q", "-D", PIPER_APLAY_DEVICE, wav_file.name]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in aplay_cmd)}")
            aplay_proc = subprocess.run(
                aplay_cmd,
                capture_output=True,
                timeout=25,
                check=False,
            )
            aplay_stderr = (aplay_proc.stderr or b"").decode("utf-8", errors="ignore")
            if aplay_proc.returncode != 0:
                return False, aplay_stderr.strip() or f"aplay rc={aplay_proc.returncode}", voice_id
    except Exception as exc:
        return False, str(exc), voice_id
    return True, None, voice_id


def _parse_volume_percent(output: str) -> int | None:
    matches = re.findall(r"\[([0-9]{1,3})%\]", output)
    if not matches:
        return None
    values: list[int] = []
    for token in matches:
        try:
            values.append(max(0, min(100, int(token))))
        except Exception:
            continue
    if not values:
        return None
    return int(round(sum(values) / len(values)))


def _read_volume_percent() -> tuple[int | None, str]:
    commands = [
        ("amixer:pulse", "amixer -D pulse sget Master"),
        ("amixer:default", "amixer sget Master"),
        ("pactl:default", "pactl get-sink-volume @DEFAULT_SINK@"),
    ]
    for source, cmd in commands:
        rc, out = _run_shell(cmd, timeout_sec=3)
        if rc != 0:
            continue
        pct = _parse_volume_percent(out)
        if pct is not None:
            return pct, source
    return None, "unavailable"


def _set_volume_percent(percent: int) -> tuple[bool, str, str | None]:
    pct = max(0, min(100, int(percent)))
    commands = [
        (
            "bashrc:vol",
            "source ~/.bashrc >/dev/null 2>&1 || true; "
            + "if command -v vol >/dev/null 2>&1; then vol "
            + str(pct)
            + "; else exit 127; fi",
        ),
        ("amixer:pulse", "amixer -D pulse sset Master " + str(pct) + "%"),
        ("pactl:default", "pactl set-sink-volume @DEFAULT_SINK@ " + str(pct) + "%"),
    ]
    last_error: str | None = None
    for source, cmd in commands:
        rc, out = _run_shell(cmd, timeout_sec=4)
        if rc == 0:
            return True, source, None
        last_error = out.strip() or f"rc={rc}"
    return False, "unavailable", last_error


def _read_volume_percent_from_bashrc() -> int | None:
    try:
        text = BASHRC_PATH.read_text(encoding="utf-8")
    except Exception:
        return None

    found: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Remove trailing comments to avoid false positives.
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        matches = re.findall(r"(?:^|[;&]\s*)vol\s+([0-9]{1,3})\b", line)
        if not matches:
            continue
        for token in matches:
            try:
                found = max(0, min(100, int(token)))
            except Exception:
                continue
    return found


def _mjpeg_stream(stream_name: str):
    boundary = b"--frame\r\n"
    header = b"Content-Type: image/jpeg\r\n\r\n"
    if not ROS_AVAILABLE:
        while True:
            time.sleep(0.5)
        return

    bridge = state.bridge
    if bridge is None:
        while True:
            time.sleep(0.5)
        return

    while True:
        frame = bridge.get_frame_jpeg(stream_name)
        if frame is not None:
            yield boundary + header + frame + b"\r\n"
        time.sleep(0.05)


@app.get("/stream/color")
def color_stream() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_stream("color"),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/stream/depth")
def depth_stream() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_stream("depth"),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def main() -> int:
    host = os.environ.get("BOOSTER_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("BOOSTER_WEB_PORT", "8000"))
    uvicorn.run("pc_booster_control.web_server:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
