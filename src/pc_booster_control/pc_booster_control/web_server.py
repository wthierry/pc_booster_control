import os
import shlex
import shutil
import ssl
import subprocess
import sys
import threading
import time
import re
import json
import struct
import tempfile
import base64
import io
import wave
from collections import deque
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles


def _preload_env_file() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        return


_preload_env_file()

ROS_IMPORT_ERROR: str | None = None
ROS_AVAILABLE = True
try:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor

    from .memory_store import (
        append_history_turn,
        build_chat_messages_with_context,
        build_prompt_with_context,
        capture_implicit_memory,
        describe_saved_memory,
        maybe_handle_memory_command,
    )
    from .web_bridge import RosWebBridge
except Exception as exc:  # pragma: no cover - runtime environment dependent
    ROS_AVAILABLE = False
    ROS_IMPORT_ERROR = str(exc)
    rclpy = None  # type: ignore[assignment]
    MultiThreadedExecutor = Any  # type: ignore[misc,assignment]
    from .memory_store import (
        append_history_turn,
        build_chat_messages_with_context,
        build_prompt_with_context,
        capture_implicit_memory,
        describe_saved_memory,
        maybe_handle_memory_command,
    )
    RosWebBridge = Any  # type: ignore[misc,assignment]


def _resolve_default_piper_bin() -> Path:
    in_path = shutil.which("piper")
    if in_path:
        return Path(in_path)
    for candidate in (
        "/opt/homebrew/bin/piper",
        "/usr/local/bin/piper",
        "/home/booster/piper/piper/piper",
    ):
        path = Path(candidate)
        if path.exists():
            return path
    return Path("/home/booster/piper/piper/piper")


def _resolve_default_piper_voice_dir() -> Path:
    local_voice_dir = Path(__file__).resolve().parents[3] / "piper" / "voices"
    if local_voice_dir.exists():
        return local_voice_dir
    return Path("/home/booster/piper/voices")


def _resolve_default_sherpa_model_dir() -> Path:
    local_model_dir = (
        Path(__file__).resolve().parents[3]
        / "sherpa-models"
        / "sherpa-onnx-streaming-zipformer-en-2023-06-26"
    )
    if local_model_dir.exists():
        return local_model_dir
    return Path("/home/booster/sherpa-onnx-models/sherpa-onnx-streaming-zipformer-en-2023-06-26")


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
PIPER_BIN = Path(os.environ.get("BOOSTER_PIPER_BIN", str(_resolve_default_piper_bin())))
PIPER_VOICE_DIR = Path(os.environ.get("BOOSTER_PIPER_VOICE_DIR", str(_resolve_default_piper_voice_dir())))
DEFAULT_PIPER_VOICE = os.environ.get("BOOSTER_PIPER_DEFAULT_VOICE", "en_US-lessac-medium")
PIPER_APLAY_DEVICE = os.environ.get("BOOSTER_PIPER_APLAY_DEVICE", "plughw:CARD=Device,DEV=0")
PIPER_PLAYBACK_MODE = os.environ.get("BOOSTER_PIPER_PLAYBACK_MODE", "auto").strip().lower()
PIPER_LENGTH_SCALE = os.environ.get("BOOSTER_PIPER_LENGTH_SCALE", "").strip()
PIPER_ESPEAK_VOICE = os.environ.get("BOOSTER_PIPER_ESPEAK_VOICE", "").strip()
APPLE_TTS_DEFAULT_VOICE = os.environ.get("BOOSTER_APPLE_TTS_DEFAULT_VOICE", "Daniel").strip() or "Daniel"
APPLE_TTS_DEFAULT_RATE = float(os.environ.get("BOOSTER_APPLE_TTS_DEFAULT_RATE", "1.0") or "1.0")
KOKORO_REPO_ID = os.environ.get("BOOSTER_KOKORO_REPO_ID", "hexgrad/Kokoro-82M").strip() or "hexgrad/Kokoro-82M"
KOKORO_DEFAULT_VOICE = os.environ.get("BOOSTER_KOKORO_DEFAULT_VOICE", "af_heart").strip() or "af_heart"
OPENAI_API_URL = os.environ.get("BOOSTER_OPENAI_API_URL", "https://api.openai.com/v1/responses")
OPENAI_MODEL = os.environ.get("BOOSTER_OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TIMEOUT_SEC = int(os.environ.get("BOOSTER_OPENAI_TIMEOUT_SEC", "60"))
OLLAMA_API_URL = os.environ.get("BOOSTER_OLLAMA_API_URL", "http://127.0.0.1:11434/api/chat").strip() or "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("BOOSTER_OLLAMA_MODEL", "qwen2.5:14b").strip() or "qwen2.5:14b"
OLLAMA_TIMEOUT_SEC = int(os.environ.get("BOOSTER_OLLAMA_TIMEOUT_SEC", "120"))
REMOTE_TTS_CATALOG_URL = os.environ.get("BOOSTER_REMOTE_TTS_CATALOG_URL", "").strip()
REMOTE_TTS_CATALOG_TIMEOUT_SEC = int(os.environ.get("BOOSTER_REMOTE_TTS_CATALOG_TIMEOUT_SEC", "5"))
REMOTE_ASSISTANT_BASE_URL = os.environ.get("BOOSTER_REMOTE_ASSISTANT_BASE_URL", "").strip().rstrip("/")
REMOTE_ASSISTANT_TIMEOUT_SEC = int(os.environ.get("BOOSTER_REMOTE_ASSISTANT_TIMEOUT_SEC", "180"))
OPENAI_KEY_NAMES = ("OPENAI_API_KEY", "CHATGPT_API_KEY", "CHAT_GPT_API", "API_KEY")
OPENAI_TTS_API_URL = os.environ.get("BOOSTER_OPENAI_TTS_API_URL", "https://api.openai.com/v1/audio/speech")
OPENAI_TTS_MODEL = os.environ.get("BOOSTER_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_DEFAULT_VOICE = os.environ.get("BOOSTER_OPENAI_TTS_DEFAULT_VOICE", "alloy").strip() or "alloy"
OPENAI_TTS_VOICES = tuple(
    voice.strip()
    for voice in os.environ.get(
        "BOOSTER_OPENAI_TTS_VOICES",
        "alloy,ash,ballad,coral,echo,sage,shimmer,verse",
    ).split(",")
    if voice.strip()
)
DEFAULT_TTS_BACKEND = os.environ.get("BOOSTER_TTS_BACKEND", "piper").strip().lower() or "piper"
DEFAULT_PIPER_NOISE_SCALE = float(os.environ.get("BOOSTER_PIPER_DEFAULT_NOISE_SCALE", "0.667"))
DEFAULT_PIPER_NOISE_W = float(os.environ.get("BOOSTER_PIPER_DEFAULT_NOISE_W", "0.8"))
DEFAULT_PIPER_SENTENCE_SILENCE = float(os.environ.get("BOOSTER_PIPER_DEFAULT_SENTENCE_SILENCE", "0.2"))
DEFAULT_LLM_BACKEND = os.environ.get("BOOSTER_LLM_BACKEND", "openai").strip().lower() or "openai"
SHERPA_ASR_MODEL_DIR = Path(os.environ.get("BOOSTER_SHERPA_ASR_MODEL_DIR", str(_resolve_default_sherpa_model_dir())))
SHERPA_DEVICE_NAME = os.environ.get("BOOSTER_SHERPA_DEVICE_NAME", "").strip()
SHERPA_STT_MAX_SECONDS = float(os.environ.get("BOOSTER_SHERPA_STT_MAX_SECONDS", "12"))
SHERPA_ASR_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "sherpa_asr_once_mac.py"
ROBOT_AUDIO_SSH_HOST = os.environ.get("BOOSTER_ROBOT_AUDIO_SSH_HOST", "booster").strip() or "booster"
ROBOT_AUDIO_SSH_USER = os.environ.get("BOOSTER_ROBOT_AUDIO_SSH_USER", "booster").strip() or "booster"
ROBOT_AUDIO_SSH_PORT = max(1, int(os.environ.get("BOOSTER_ROBOT_AUDIO_SSH_PORT", "22")))
ROBOT_AUDIO_DIR = os.environ.get("BOOSTER_ROBOT_AUDIO_DIR", "/tmp/booster_tts").strip() or "/tmp/booster_tts"
ROBOT_AUDIO_APLAY_DEVICE = (
    os.environ.get("BOOSTER_ROBOT_AUDIO_APLAY_DEVICE", "plughw:CARD=Device,DEV=0").strip() or "plughw:CARD=Device,DEV=0"
)
DEFAULT_SYSTEM_PROMPT = (
    "You are Booster K1's onboard assistant. Keep responses concise, practical, and lightly witty."
)
CONVERSATION_ENABLED = os.environ.get("BOOSTER_CONVERSATION_ENABLED", "0").strip() not in ("0", "false", "False")
_audio_activity_default = "0" if CONVERSATION_ENABLED else "1"
AUDIO_ACTIVITY_ENABLED = os.environ.get("BOOSTER_AUDIO_ACTIVITY_ENABLED", _audio_activity_default).strip() not in (
    "0",
    "false",
    "False",
)
LAST_SET_VOLUME_PERCENT: int | None = None
KOKORO_PIPELINE_CACHE: dict[str, Any] = {}
KOKORO_PIPELINE_LOCK = threading.Lock()

DEFAULT_KOKORO_VOICES = [
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
]

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
    llm_backend: str | None = None
    llm_model: str | None = None
    voice_type: str | None = None
    speech_backend: str | None = None
    tts_enabled: bool = True
    piper_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    piper_noise_scale: float | None = Field(default=None, ge=0.1, le=2.0)
    piper_noise_w: float | None = Field(default=None, ge=0.1, le=2.0)
    piper_sentence_silence: float | None = Field(default=None, ge=0.0, le=2.0)
    apple_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    playback_target: str | None = None


class PreloadRequest(BaseModel):
    llm_backend: str | None = None
    llm_model: str | None = None
    voice_type: str | None = None
    speech_backend: str | None = None
    tts_enabled: bool = True
    piper_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    piper_noise_scale: float | None = Field(default=None, ge=0.1, le=2.0)
    piper_noise_w: float | None = Field(default=None, ge=0.1, le=2.0)
    piper_sentence_silence: float | None = Field(default=None, ge=0.0, le=2.0)
    apple_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    playback_target: str | None = None


class VolumeRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class MicrophoneRequest(BaseModel):
    enabled: bool
    source: str | None = None


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
        self.mic_source: str = "robot"
        self.mic_worker_thread: threading.Thread | None = None
        self.mic_worker_stop = threading.Event()
        self.mic_worker_proc: subprocess.Popen[bytes] | None = None
        self.mic_worker_running: bool = False
        self.mic_last_text: str = ""
        self.mic_last_error: str | None = None
        self.mic_last_ts: float = 0.0
        self.motors_cache: list[dict[str, Any]] = []
        self.motors_cache_source: str = "/low_state"
        self.motors_cache_error: str | None = None
        self.motors_cache_ts: float = 0.0
        self.audio_level: float = 0.0
        self.audio_active: bool = False
        self.audio_error: str | None = None
        self.audio_ts: float = 0.0
        self.audio_source: str = "robot"
        self.audio_capture_lock = threading.Lock()
        self.debug_lock = threading.Lock()
        self.debug_lines: deque[tuple[int, str]] = deque(maxlen=max(100, DEBUG_LOG_MAX_LINES))
        self.debug_next_id: int = 1


state = WebAppState()
app = FastAPI(title="Booster K1 Camera Viewer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def _startup() -> None:
    _debug_log("web server startup")
    _load_env_file()
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

    speech_ready, speech_error, speech_voice = _speech_ready_state()
    state.ai_chat_initialized = speech_ready
    state.ai_chat_ready = speech_ready
    state.ai_chat_starting = False
    state.ai_chat_error = speech_error
    state.ai_voice_type = speech_voice
    state.mic_enabled = False
    state.mic_source = "robot"
    if speech_ready:
        _debug_log(f"speech pipeline ready: model={OPENAI_MODEL}, voice={speech_voice}")
    else:
        _debug_log(f"speech pipeline unavailable: {speech_error}")


@app.on_event("shutdown")
def _shutdown() -> None:
    _stop_microphone_worker()
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

    speech_ready, speech_error, speech_voice = _speech_ready_state()
    health_tts_backend = _normalize_tts_backend(DEFAULT_TTS_BACKEND)
    if speech_ready and health_tts_backend == "piper":
        piper_ready, _ = _piper_ready_state()
        if not piper_ready:
            health_tts_backend = "openai"
    mic_enabled = state.mic_enabled
    mic_source = state.mic_source
    if REMOTE_ASSISTANT_BASE_URL:
        remote_mic, _remote_mic_err = _proxy_remote_assistant_get("/api/microphone/status")
        if isinstance(remote_mic, dict):
            mic_enabled = bool(remote_mic.get("enabled"))
            mic_source = _normalize_mic_source(remote_mic.get("source"))
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
        "ai_ready": speech_ready,
        "ai_starting": False,
        "ai_error": speech_error,
        "ai_voice_type": speech_voice,
        "ai_tts_backend": health_tts_backend,
        "ai_llm_backend": _normalize_llm_backend(DEFAULT_LLM_BACKEND),
        "mic_enabled": mic_enabled,
        "mic_source": mic_source,
        "motors_count": len(state.motors_cache),
        "motors_error": state.motors_cache_error,
        "mode_ui_state": state.mode_ui_state,
        "mode_control": {
            "rpc_service": DEFAULT_RPC_SERVICE,
            "change_mode_api_id": CHANGE_MODE_API_ID,
            "damp_value": DAMP_MODE_VALUE,
            "prep_value": PREP_MODE_VALUE,
        },
        "tts_control": {
            "default_backend": _normalize_tts_backend(DEFAULT_TTS_BACKEND),
            "openai_tts_model": OPENAI_TTS_MODEL,
            "openai_tts_default_voice": OPENAI_TTS_DEFAULT_VOICE,
            "apple_tts_default_voice": APPLE_TTS_DEFAULT_VOICE,
            "kokoro_repo_id": KOKORO_REPO_ID,
            "kokoro_default_voice": KOKORO_DEFAULT_VOICE,
            "piper_length_scale": PIPER_LENGTH_SCALE or None,
            "piper_espeak_voice": PIPER_ESPEAK_VOICE or None,
            "piper_playback_mode": PIPER_PLAYBACK_MODE,
            "robot_audio_host": ROBOT_AUDIO_SSH_HOST,
            "robot_audio_dir": ROBOT_AUDIO_DIR,
        },
        "llm_control": {
            "default_backend": _normalize_llm_backend(DEFAULT_LLM_BACKEND),
            "openai_model": OPENAI_MODEL,
            "ollama_api_url": OLLAMA_API_URL,
            "ollama_model": OLLAMA_MODEL,
        },
    }


@app.get("/api/debug")
def debug_lines(since: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    lines, next_id = _debug_snapshot(since=since, limit=limit)
    return {"ok": True, "lines": lines, "next": next_id}


@app.get("/api/audio/activity")
def audio_activity(source: str | None = Query(default=None)) -> dict[str, Any]:
    _load_env_file()
    mic_source = _normalize_mic_source(source)
    if REMOTE_ASSISTANT_BASE_URL:
        remote_resp, remote_err = _proxy_remote_assistant_get(f"/api/audio/activity?source={mic_source}")
        if remote_resp is not None:
            remote_resp.setdefault("source", mic_source)
            return remote_resp
        return {
            "ok": False,
            "active": False,
            "level": 0.0,
            "threshold": 0.02,
            "device": f"remote {mic_source} capture",
            "source": mic_source,
            "error": remote_err or "remote assistant unavailable",
        }
    level, active, error = _read_audio_activity_cached(mic_source)
    device_name = (
        "sounddevice default capture"
        if mic_source == "mac"
        else (
            f"ssh robot capture ({ROBOT_AUDIO_SSH_HOST})"
            if sys.platform == "darwin" and ROBOT_AUDIO_SSH_HOST
            else "ALSA default capture"
        )
    )
    return {
        "ok": error is None,
        "active": active,
        "level": level,
        "threshold": 0.02,
        "device": device_name,
        "source": mic_source,
        "error": error,
    }


@app.get("/api/microphone/status")
def microphone_status() -> dict[str, Any]:
    _load_env_file()
    if REMOTE_ASSISTANT_BASE_URL:
        remote_resp, remote_err = _proxy_remote_assistant_get("/api/microphone/status")
        if remote_resp is not None:
            return remote_resp
        return {
            "ok": False,
            "enabled": False,
            "source": state.mic_source,
            "listening": False,
            "transcript": "",
            "updated_at": state.mic_last_ts,
            "error": remote_err or "remote assistant unavailable",
        }
    return _microphone_status_payload()


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
    user_text = req.text.strip()
    if not user_text:
        return {"ok": False, "error": "text is empty"}

    _load_env_file()
    remote_resp, remote_err = _proxy_remote_assistant("/api/speak", _model_dump_json(req))
    if remote_resp is not None:
        remote_resp.setdefault("remote_assistant_source", REMOTE_ASSISTANT_BASE_URL)
        return remote_resp
    if remote_err:
        _debug_log(f"remote assistant proxy failed: {remote_err}")
        return {"ok": False, "error": f"Remote assistant error: {remote_err}"}

    llm_backend = _normalize_llm_backend(req.llm_backend or DEFAULT_LLM_BACKEND)
    tts_backend = _normalize_tts_backend(req.speech_backend or DEFAULT_TTS_BACKEND)
    tts_enabled = bool(req.tts_enabled)
    llm_model = (req.llm_model or "").strip() or (OPENAI_MODEL if llm_backend == "openai" else OLLAMA_MODEL)
    api_key = _resolve_openai_api_key()
    if tts_enabled and tts_backend == "openai" and not api_key:
        return {
            "ok": False,
            "error": "OpenAI API key missing for OpenAI Voice (set OPENAI_API_KEY or CHATGPT_API_KEY in .env/environment)",
        }

    memory_reply = maybe_handle_memory_command(user_text)
    if memory_reply:
        assistant_text = memory_reply
        append_history_turn(user_text, assistant_text, llm_backend=llm_backend, llm_model=llm_model)
        if not tts_enabled:
            return {
                "ok": True,
                "llm_backend_used": "memory",
                "llm_model_used": "local-memory",
                "speech_backend_used": None,
                "voice_used": None,
                "assistant_text": assistant_text,
                "tts_text": None,
                "user_text": user_text,
                "tts_enabled": False,
                "playback_target": None,
                "playback_mode": "none",
                "audio_mime": None,
                "audio_base64": None,
                "piper_rate": None,
                "piper_noise_scale": None,
                "piper_noise_w": None,
                "piper_sentence_silence": None,
                "apple_rate": None,
            }
        tts_text = _prepare_tts_text(assistant_text)
        voice = (req.voice_type or "").strip() or _default_voice_for_backend(tts_backend)
        playback_target = _normalize_playback_target(req.playback_target)
        ok, error, voice_id, audio_b64, playback_mode = _speak_with_backend(
            backend=tts_backend,
            voice=voice,
            text=tts_text,
            playback_target=playback_target,
            piper_rate=req.piper_rate,
            piper_noise_scale=req.piper_noise_scale,
            piper_noise_w=req.piper_noise_w,
            piper_sentence_silence=req.piper_sentence_silence,
            apple_rate=req.apple_rate,
            api_key=api_key,
        )
        if not ok:
            return {
                "ok": False,
                "error": error,
                "llm_backend_used": "memory",
                "llm_model_used": "local-memory",
                "speech_backend_used": tts_backend,
                "voice_used": voice_id,
                "assistant_text": assistant_text,
                "tts_text": tts_text,
                "playback_target": playback_target,
                "playback_mode": playback_mode,
                "piper_rate": req.piper_rate if tts_backend == "piper" else None,
                "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
                "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
                "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
                "apple_rate": req.apple_rate if tts_backend == "apple" else None,
            }
        return {
            "ok": True,
            "llm_backend_used": "memory",
            "llm_model_used": "local-memory",
            "speech_backend_used": tts_backend,
            "voice_used": voice_id,
            "assistant_text": assistant_text,
            "tts_text": tts_text,
            "user_text": user_text,
            "tts_enabled": True,
            "playback_target": playback_target,
            "playback_mode": playback_mode,
            "audio_mime": "audio/wav" if audio_b64 else None,
            "audio_base64": audio_b64,
            "piper_rate": req.piper_rate if tts_backend == "piper" else None,
            "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
            "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
            "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
            "apple_rate": req.apple_rate if tts_backend == "apple" else None,
        }

    capture_implicit_memory(user_text)
    system_prompt = _resolve_system_prompt(llm_backend)
    llm_model_used = llm_model
    if llm_backend == "openai":
        llm_prompt = build_prompt_with_context(user_text, llm_backend=llm_backend, llm_model=llm_model)
        if not api_key:
            return {
                "ok": False,
                "error": "OpenAI API key missing for OpenAI chat (set OPENAI_API_KEY or CHATGPT_API_KEY in .env/environment)",
            }
        assistant_text, llm_error, llm_thinking = _query_openai_response(
            api_key=api_key,
            prompt=llm_prompt,
            system_prompt=system_prompt,
            model=llm_model,
        )
    else:
        llm_messages = build_chat_messages_with_context(user_text, llm_backend=llm_backend, llm_model=llm_model)
        assistant_text, llm_error, llm_thinking = _query_ollama_response(
            prompt=None,
            system_prompt=system_prompt,
            model=llm_model,
            messages=llm_messages,
        )
    if llm_error:
        _debug_log(f"{llm_backend} query failed: {llm_error}")
        backend_label = "OpenAI" if llm_backend == "openai" else "Ollama"
        return {"ok": False, "error": f"{backend_label} error: {llm_error}"}

    if not assistant_text:
        backend_label = "OpenAI" if llm_backend == "openai" else "Ollama"
        return {"ok": False, "error": f"{backend_label} returned empty response"}

    append_history_turn(user_text, assistant_text, llm_backend=llm_backend, llm_model=llm_model)
    if not tts_enabled:
        return {
            "ok": True,
            "llm_backend_used": llm_backend,
            "llm_model_used": llm_model_used,
            "llm_thinking": llm_thinking,
            "speech_backend_used": None,
            "voice_used": None,
            "assistant_text": assistant_text,
            "tts_text": None,
            "user_text": user_text,
            "tts_enabled": False,
            "playback_target": None,
            "playback_mode": "none",
            "audio_mime": None,
            "audio_base64": None,
            "piper_rate": None,
            "piper_noise_scale": None,
            "piper_noise_w": None,
            "piper_sentence_silence": None,
            "apple_rate": None,
        }

    tts_text = _prepare_tts_text(assistant_text)
    voice = (req.voice_type or "").strip() or _default_voice_for_backend(tts_backend)
    playback_target = _normalize_playback_target(req.playback_target)
    ok, error, voice_id, audio_b64, playback_mode = _speak_with_backend(
        backend=tts_backend,
        voice=voice,
        text=tts_text,
        playback_target=playback_target,
        piper_rate=req.piper_rate,
        piper_noise_scale=req.piper_noise_scale,
        piper_noise_w=req.piper_noise_w,
        piper_sentence_silence=req.piper_sentence_silence,
        apple_rate=req.apple_rate,
        api_key=api_key,
    )
    if not ok:
        _debug_log(f"{tts_backend} speak failed: {error}")
        return {
            "ok": False,
            "error": error,
            "llm_backend_used": llm_backend,
            "llm_model_used": llm_model_used,
            "speech_backend_used": tts_backend,
            "voice_used": voice_id,
            "assistant_text": assistant_text,
            "tts_text": tts_text,
            "playback_target": playback_target,
            "playback_mode": playback_mode,
            "piper_rate": req.piper_rate if tts_backend == "piper" else None,
            "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
            "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
            "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
            "apple_rate": req.apple_rate if tts_backend == "apple" else None,
        }
    return {
        "ok": True,
        "llm_backend_used": llm_backend,
        "llm_model_used": llm_model_used,
        "llm_thinking": llm_thinking,
        "speech_backend_used": tts_backend,
        "voice_used": voice_id,
        "assistant_text": assistant_text,
        "tts_text": tts_text,
        "user_text": user_text,
        "tts_enabled": True,
        "playback_target": playback_target,
        "playback_mode": playback_mode,
        "audio_mime": "audio/wav" if audio_b64 else None,
        "audio_base64": audio_b64,
        "piper_rate": req.piper_rate if tts_backend == "piper" else None,
        "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
        "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
        "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
        "apple_rate": req.apple_rate if tts_backend == "apple" else None,
    }


@app.post("/api/preload")
def preload(req: PreloadRequest) -> dict[str, Any]:
    _load_env_file()
    remote_resp, remote_err = _proxy_remote_assistant("/api/preload", _model_dump_json(req))
    if remote_resp is not None:
        remote_resp.setdefault("remote_assistant_source", REMOTE_ASSISTANT_BASE_URL)
        return remote_resp
    if remote_err:
        _debug_log(f"remote preload proxy failed: {remote_err}")
        return {"ok": False, "error": f"Remote assistant error: {remote_err}"}

    llm_backend = _normalize_llm_backend(req.llm_backend or DEFAULT_LLM_BACKEND)
    llm_model = (req.llm_model or "").strip() or (OPENAI_MODEL if llm_backend == "openai" else OLLAMA_MODEL)
    tts_backend = _normalize_tts_backend(req.speech_backend or DEFAULT_TTS_BACKEND)
    tts_enabled = bool(req.tts_enabled)
    playback_target = _normalize_playback_target(req.playback_target)
    api_key = _resolve_openai_api_key()

    if llm_backend == "openai" and not api_key:
        return {
            "ok": False,
            "error": "OpenAI API key missing for OpenAI chat (set OPENAI_API_KEY or CHATGPT_API_KEY in .env/environment)",
        }
    if tts_enabled and tts_backend == "openai" and not api_key:
        return {
            "ok": False,
            "error": "OpenAI API key missing for OpenAI Voice (set OPENAI_API_KEY or CHATGPT_API_KEY in .env/environment)",
        }

    if llm_backend == "ollama":
        _debug_log(f"preloading ollama model: {llm_model}")
        _, llm_error, llm_thinking = _query_ollama_response(
            prompt="Reply with exactly: ok",
            system_prompt=_resolve_system_prompt(llm_backend) + "\n\nThis is a warmup request. Reply with exactly ok.",
            model=llm_model,
        )
        if llm_error:
            return {
                "ok": False,
                "error": f"Ollama preload error: {llm_error}",
                "llm_backend_used": llm_backend,
                "llm_model_used": llm_model,
            }
    else:
        llm_thinking = None

    if not tts_enabled:
        return {
            "ok": True,
            "llm_backend_used": llm_backend,
            "llm_model_used": llm_model,
            "llm_thinking": llm_thinking,
            "speech_backend_used": None,
            "voice_used": None,
            "tts_enabled": False,
            "playback_target": None,
            "playback_mode": "none",
            "audio_mime": None,
            "audio_base64": None,
            "message": "Model loaded.",
        }

    voice = (req.voice_type or "").strip() or _default_voice_for_backend(tts_backend)
    ok, error, voice_id, audio_b64, playback_mode = _speak_with_backend(
        backend=tts_backend,
        voice=voice,
        text="Model loaded.",
        playback_target=playback_target,
        piper_rate=req.piper_rate,
        piper_noise_scale=req.piper_noise_scale,
        piper_noise_w=req.piper_noise_w,
        piper_sentence_silence=req.piper_sentence_silence,
        apple_rate=req.apple_rate,
        api_key=api_key,
    )
    if not ok:
        _debug_log(f"{tts_backend} preload speak failed: {error}")
        return {
            "ok": False,
            "error": error,
            "llm_backend_used": llm_backend,
            "llm_model_used": llm_model,
            "speech_backend_used": tts_backend,
            "voice_used": voice_id,
            "tts_enabled": True,
            "playback_target": playback_target,
            "playback_mode": playback_mode,
            "piper_rate": req.piper_rate if tts_backend == "piper" else None,
            "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
            "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
            "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
            "apple_rate": req.apple_rate if tts_backend == "apple" else None,
        }

    return {
        "ok": True,
        "llm_backend_used": llm_backend,
        "llm_model_used": llm_model,
        "llm_thinking": llm_thinking,
        "speech_backend_used": tts_backend,
        "voice_used": voice_id,
        "tts_enabled": True,
        "tts_text": "Model loaded.",
        "playback_target": playback_target,
        "playback_mode": playback_mode,
        "audio_mime": "audio/wav" if audio_b64 else None,
        "audio_base64": audio_b64,
        "message": "Model loaded.",
        "piper_rate": req.piper_rate if tts_backend == "piper" else None,
        "piper_noise_scale": req.piper_noise_scale if tts_backend == "piper" else None,
        "piper_noise_w": req.piper_noise_w if tts_backend == "piper" else None,
        "piper_sentence_silence": req.piper_sentence_silence if tts_backend == "piper" else None,
        "apple_rate": req.apple_rate if tts_backend == "apple" else None,
    }


@app.get("/api/voices")
def voices() -> dict[str, Any]:
    return _build_voices_payload()


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
    if ok and percent is None:
        percent = max(0, min(100, int(req.percent)))
        read_source = "requested:fallback"
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
    _load_env_file()
    mic_source = _normalize_mic_source(req.source)
    state.mic_source = mic_source
    if REMOTE_ASSISTANT_BASE_URL:
        remote_resp, remote_err = _proxy_remote_assistant("/api/microphone", _model_dump_json(req))
        if remote_resp is not None:
            remote_resp.setdefault("source", mic_source)
            return remote_resp
        return {
            "ok": False,
            "enabled": False,
            "source": mic_source,
            "error": remote_err or "remote assistant unavailable",
        }

    state.mic_enabled = bool(req.enabled)
    if state.mic_enabled:
        _start_microphone_worker(mic_source)
    else:
        _stop_microphone_worker()
    _debug_log(f"microphone state updated: source={mic_source} enabled={state.mic_enabled}")
    return {
        "ok": True,
        "enabled": state.mic_enabled,
        "source": mic_source,
        "note": f"Audio capture source set to {mic_source}. Sherpa transcription is running on the Mac and updates the Heard box only.",
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


def _microphone_status_payload() -> dict[str, Any]:
    label = "Mac mic" if state.mic_source == "mac" else "Robot mic"
    return {
        "ok": True,
        "enabled": state.mic_enabled,
        "source": state.mic_source,
        "label": label,
        "listening": state.mic_enabled and state.mic_worker_running,
        "transcript": state.mic_last_text,
        "updated_at": state.mic_last_ts,
        "error": state.mic_last_error,
    }


def _set_microphone_result(text: str = "", error: str | None = None) -> None:
    state.mic_last_text = (text or "").strip()
    state.mic_last_error = error
    state.mic_last_ts = time.time()


def _terminate_microphone_process() -> None:
    proc = state.mic_worker_proc
    if proc is None:
        return
    state.mic_worker_proc = None
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=1.5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass


def _stop_microphone_worker() -> None:
    state.mic_enabled = False
    state.mic_worker_stop.set()
    _terminate_microphone_process()
    thread = state.mic_worker_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)
    state.mic_worker_thread = None
    state.mic_worker_running = False


def _start_microphone_worker(source: str) -> None:
    _stop_microphone_worker()
    state.mic_enabled = True
    state.mic_source = source
    state.mic_worker_stop = threading.Event()
    _set_microphone_result("", None)
    thread = threading.Thread(target=_microphone_worker_loop, args=(source, state.mic_worker_stop), daemon=True)
    state.mic_worker_thread = thread
    thread.start()


def _microphone_worker_loop(source: str, stop_event: threading.Event) -> None:
    state.mic_worker_running = True
    label = "Mac mic" if source == "mac" else "Robot mic"
    _debug_log(f"sherpa listen loop started: source={source}")
    try:
        while not stop_event.is_set() and state.mic_enabled and state.mic_source == source:
            transcript, error = _run_sherpa_once(source, stop_event)
            if stop_event.is_set() or not state.mic_enabled or state.mic_source != source:
                break
            if transcript:
                _set_microphone_result(transcript, None)
                _debug_log(f"heard ({label}): {transcript}")
                continue
            if error and error not in ("no speech recognized before timeout", "stopped"):
                _set_microphone_result(state.mic_last_text, error)
                _debug_log(f"sherpa listen warning ({source}): {error}")
                time.sleep(0.35)
    finally:
        state.mic_worker_running = False
        _terminate_microphone_process()
        _debug_log(f"sherpa listen loop stopped: source={source}")


def _build_robot_audio_capture_command() -> str:
    robot_devices = [
        "plughw:CARD=Device,DEV=0",
        "dsnoop:CARD=Device,DEV=0",
        "hw:CARD=Device,DEV=0",
        "default",
    ]
    attempts = " || ".join(
        [
            (
                f"timeout {max(1.0, SHERPA_STT_MAX_SECONDS):.1f} "
                f"arecord -q -D {shlex.quote(dev)} -f S16_LE -c 1 -r 16000 -t raw"
            )
            for dev in robot_devices
        ]
    )
    remote_cmd = f"bash -lc {shlex.quote(attempts)}"
    return " ".join(
        [
            "ssh",
            "-p",
            shlex.quote(str(ROBOT_AUDIO_SSH_PORT)),
            f"{shlex.quote(ROBOT_AUDIO_SSH_USER)}@{shlex.quote(ROBOT_AUDIO_SSH_HOST)}",
            shlex.quote(remote_cmd),
        ]
    )


def _run_sherpa_once(source: str, stop_event: threading.Event) -> tuple[str, str | None]:
    if not SHERPA_ASR_SCRIPT.exists():
        return "", f"sherpa script missing: {SHERPA_ASR_SCRIPT}"
    if not SHERPA_ASR_MODEL_DIR.is_dir():
        return "", f"sherpa model dir missing: {SHERPA_ASR_MODEL_DIR}"

    if source == "mac":
        cmd = [
            sys.executable,
            str(SHERPA_ASR_SCRIPT),
            "--model-dir",
            str(SHERPA_ASR_MODEL_DIR),
            "--max-seconds",
            str(SHERPA_STT_MAX_SECONDS),
        ]
        if SHERPA_DEVICE_NAME:
            cmd.extend(["--device-name", SHERPA_DEVICE_NAME])
    else:
        if not ROBOT_AUDIO_SSH_HOST:
            return "", "robot ssh host not configured"
        sherpa_cmd = " ".join(
            [
                shlex.quote(sys.executable),
                shlex.quote(str(SHERPA_ASR_SCRIPT)),
                "--stdin-pcm",
                "--sample-rate",
                "16000",
                "--model-dir",
                shlex.quote(str(SHERPA_ASR_MODEL_DIR)),
                "--max-seconds",
                shlex.quote(str(SHERPA_STT_MAX_SECONDS)),
            ]
        )
        shell_cmd = f"{_build_robot_audio_capture_command()} | {sherpa_cmd}"
        cmd = ["bash", "-lc", shell_cmd]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:
        return "", str(exc)

    state.mic_worker_proc = proc
    try:
        while proc.poll() is None:
            if stop_event.is_set() or not state.mic_enabled or state.mic_source != source:
                _terminate_microphone_process()
                return "", "stopped"
            time.sleep(0.1)
        stdout, stderr = proc.communicate(timeout=0.5)
    except Exception as exc:
        _terminate_microphone_process()
        return "", str(exc)
    finally:
        state.mic_worker_proc = None

    out_text = (stdout or b"").decode("utf-8", errors="ignore").strip()
    err_text = (stderr or b"").decode("utf-8", errors="ignore").strip()
    for line in out_text.splitlines():
        if line.startswith("__STT__:"):
            return line.split(":", 1)[1].strip(), None
    return "", err_text or out_text or f"sherpa exited with code {proc.returncode}"


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
    if not _ros2_cli_ready():
        return None, "/low_state", "ROS2 CLI unavailable on this host"

    cmd = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
        "ros2 topic echo --once /low_state"
    )
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
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

    capacity = _read_battery_int("capacity")
    if capacity is not None:
        return max(0, min(100, capacity)), "capacity"

    charge_counter = _read_battery_int("charge_counter")
    charge_full_design = _read_battery_int("charge_full_design")
    if (
        charge_counter is not None
        and charge_full_design is not None
        and charge_full_design > 0
    ):
        pct = int(round((100.0 * float(charge_counter)) / float(charge_full_design)))
        return max(0, min(100, pct)), "charge_counter/charge_full_design"

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
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=6,
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
    if not _ros2_cli_ready():
        return None

    cmd = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
        "ros2 topic echo --once /battery_state"
    )
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
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
    if not _ros2_cli_ready():
        return {"ok": False, "error": "ROS2 CLI unavailable on this host"}

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
            ["bash", "-c", cmd],
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


def _run_shell(
    cmd: str, timeout_sec: int = 4, log_command: bool = True, log_output: bool = True
) -> tuple[int, str]:
    if log_command:
        _debug_log(f"$ {cmd}")
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except Exception as exc:
        if log_output:
            _debug_log(f"shell exception: {exc}")
        return 1, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    if log_output and out.strip():
        _debug_log(_truncate_debug(out.strip()))
    return proc.returncode, out


def _read_audio_activity_cached(source: str = "robot") -> tuple[float, bool, str | None]:
    if not AUDIO_ACTIVITY_ENABLED:
        return 0.0, False, "audio activity disabled"

    now = time.monotonic()
    if state.audio_source == source and (now - state.audio_ts) < 0.35:
        return state.audio_level, state.audio_active, state.audio_error

    if not state.audio_capture_lock.acquire(blocking=False):
        # Another request is already sampling audio; use latest cached snapshot.
        return state.audio_level, state.audio_active, state.audio_error
    try:
        level, error = _read_audio_level_once(source)
        active = level >= 0.02
        state.audio_level = level
        state.audio_active = active
        state.audio_error = error
        state.audio_ts = now
        state.audio_source = source
        return level, active, error
    finally:
        state.audio_capture_lock.release()



def _read_audio_level_once(source: str = "robot") -> tuple[float, str | None]:
    if source == "mac" and sys.platform == "darwin" and shutil.which("arecord") is None:
        return _read_audio_level_once_sounddevice()
    if source == "robot" and sys.platform == "darwin":
        return _read_audio_level_once_robot_over_ssh()

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
                ["bash", "-c", cmd],
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


def _read_audio_level_once_robot_over_ssh() -> tuple[float, str | None]:
    if not ROBOT_AUDIO_SSH_HOST:
        return 0.0, "robot ssh host not configured"

    robot_devices = [
        "plughw:CARD=Device,DEV=0",
        "dsnoop:CARD=Device,DEV=0",
        "hw:CARD=Device,DEV=0",
        "default",
    ]
    attempts = " || ".join(
        [
            f"timeout 0.35 arecord -q -D {shlex.quote(dev)} -f S16_LE -c 1 -r 8000 -t raw"
            for dev in robot_devices
        ]
    )
    remote_cmd = f"bash -lc {shlex.quote(attempts)}"
    ssh_cmd = [
        "ssh",
        "-p",
        str(ROBOT_AUDIO_SSH_PORT),
        f"{ROBOT_AUDIO_SSH_USER}@{ROBOT_AUDIO_SSH_HOST}",
        remote_cmd,
    ]
    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            timeout=4.0,
            check=False,
        )
    except Exception as exc:
        return 0.0, str(exc)
    data = proc.stdout or b""
    if len(data) < 4:
        err_text = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
        return 0.0, err_text or "no capture data"

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


def _read_audio_level_once_sounddevice() -> tuple[float, str | None]:
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        return 0.0, f"sounddevice unavailable: {exc}"

    sample_rate = 8000
    duration_sec = 0.25
    frames = max(1, int(sample_rate * duration_sec))
    try:
        data = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
    except Exception as exc:
        return 0.0, str(exc)

    if data is None or getattr(data, "size", 0) == 0:
        return 0.0, "no capture data"
    try:
        arr = np.asarray(data, dtype=np.float32).reshape(-1)
    except Exception as exc:
        return 0.0, f"invalid capture data: {exc}"
    if arr.size == 0:
        return 0.0, "empty sample set"
    level = float(np.mean(np.abs(arr)))
    return max(0.0, min(1.0, level)), None


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        return


def _resolve_openai_api_key() -> str:
    for name in OPENAI_KEY_NAMES:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    return ""


def _resolve_prompt_from_env(
    file_env_name: str,
    inline_env_name: str,
    default_prompt: str,
) -> str:
    prompt_file = os.environ.get(file_env_name, "").strip()
    if prompt_file:
        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = Path(__file__).resolve().parents[3] / prompt_path
        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception as exc:
            _debug_log(f"system prompt file read failed: {prompt_path} ({exc})")
    inline_prompt = os.environ.get(inline_env_name, "").strip()
    return inline_prompt or default_prompt


def _resolve_system_prompt(llm_backend: str = "openai") -> str:
    normalized = _normalize_llm_backend(llm_backend)
    if normalized == "ollama":
        return _resolve_prompt_from_env(
            "OLLAMA_SYSTEM_PROMPT_FILE",
            "OLLAMA_SYSTEM_PROMPT",
            _resolve_prompt_from_env(
                "CHATGPT_SYSTEM_PROMPT_FILE",
                "CHATGPT_SYSTEM_PROMPT",
                DEFAULT_SYSTEM_PROMPT,
            ),
        )
    return _resolve_prompt_from_env(
        "CHATGPT_SYSTEM_PROMPT_FILE",
        "CHATGPT_SYSTEM_PROMPT",
        DEFAULT_SYSTEM_PROMPT,
    )


def _speech_ready_state() -> tuple[bool, str | None, str | None]:
    backend = _normalize_tts_backend(DEFAULT_TTS_BACKEND)
    _load_env_file()
    if backend == "piper":
        piper_ready, piper_error = _piper_ready_state()
        if not piper_ready:
            api_key = _resolve_openai_api_key()
            if not api_key:
                return False, piper_error, DEFAULT_PIPER_VOICE
            return True, None, OPENAI_TTS_DEFAULT_VOICE
        return True, None, DEFAULT_PIPER_VOICE
    if backend == "apple":
        apple_ready, apple_error = _apple_tts_ready_state()
        if apple_ready:
            return True, None, APPLE_TTS_DEFAULT_VOICE
        return False, apple_error, APPLE_TTS_DEFAULT_VOICE
    if backend == "kokoro":
        kokoro_ready, kokoro_error = _kokoro_ready_state()
        if kokoro_ready:
            return True, None, KOKORO_DEFAULT_VOICE
        return False, kokoro_error, KOKORO_DEFAULT_VOICE
    api_key = _resolve_openai_api_key()
    if not api_key:
        return False, "OpenAI API key missing", _default_voice_for_backend(backend)
    return True, None, OPENAI_TTS_DEFAULT_VOICE


def _normalize_tts_backend(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("openai", "openai-voice", "openai_tts"):
        return "openai"
    if value in ("apple", "apple-tts", "macos", "macos-system", "system"):
        return "apple"
    if value in ("kokoro", "kokoro-tts"):
        return "kokoro"
    return "piper"


def _default_voice_for_backend(backend: str) -> str:
    if backend == "openai":
        return OPENAI_TTS_DEFAULT_VOICE
    if backend == "apple":
        return APPLE_TTS_DEFAULT_VOICE
    if backend == "kokoro":
        return KOKORO_DEFAULT_VOICE
    return DEFAULT_PIPER_VOICE


def _normalize_playback_target(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("robot", "robot-speakers", "robot_speakers"):
        return "robot"
    return "browser"


def _normalize_llm_backend(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("ollama", "local", "local-ollama"):
        return "ollama"
    return "openai"


def _normalize_mic_source(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("mac", "remote", "assistant"):
        return "mac"
    return "robot"


def _sanitize_model_reply(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
    low = cleaned.lower()
    analysis_markers = (
        "sentiment analysis:",
        "diagnostic check:",
        "recommendation:",
        "fix:",
        "response should",
    )

    if any(marker in low for marker in analysis_markers):
        quoted = re.findall(r'"([^"\n]{3,})"', cleaned)
        if quoted:
            return quoted[-1].strip()

        useful_lines: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip(" -*\t")
            if not line:
                continue
            lowered = line.lower()
            if any(lowered.startswith(marker) for marker in analysis_markers):
                continue
            useful_lines.append(line)
        if useful_lines:
            return " ".join(useful_lines).strip()

    return re.sub(r"\s+", " ", cleaned).strip()


def _sanitize_model_thinking(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"<think>|</think>", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def _fetch_remote_tts_catalog() -> tuple[dict[str, Any] | None, str | None]:
    if not REMOTE_TTS_CATALOG_URL:
        return None, None
    req = urlrequest.Request(
        REMOTE_TTS_CATALOG_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "pc_booster_control/remote-tts-catalog",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=REMOTE_TTS_CATALOG_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return None, str(exc)
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(parsed, dict) or parsed.get("ok") is not True:
        return None, "remote catalog not ok"
    return parsed, None


def _model_dump_json(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return getattr(model, "model_dump")()
    return model.dict()


def _post_remote_json(url: str, payload: dict[str, Any], timeout_sec: int) -> tuple[dict[str, Any] | None, str | None]:
    req = urlrequest.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "pc_booster_control/remote-assistant",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return None, str(exc)
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "remote response was not a JSON object"
    return parsed, None


def _get_remote_json(url: str, timeout_sec: int) -> tuple[dict[str, Any] | None, str | None]:
    req = urlrequest.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "pc_booster_control/remote-assistant",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return None, str(exc)
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "remote response was not a JSON object"
    return parsed, None


def _proxy_remote_assistant(path: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if not REMOTE_ASSISTANT_BASE_URL:
        return None, None
    return _post_remote_json(f"{REMOTE_ASSISTANT_BASE_URL}{path}", payload, REMOTE_ASSISTANT_TIMEOUT_SEC)


def _proxy_remote_assistant_get(path: str) -> tuple[dict[str, Any] | None, str | None]:
    if not REMOTE_ASSISTANT_BASE_URL:
        return None, None
    return _get_remote_json(f"{REMOTE_ASSISTANT_BASE_URL}{path}", REMOTE_ASSISTANT_TIMEOUT_SEC)


def _build_voices_payload() -> dict[str, Any]:
    ollama_models = _list_ollama_model_ids()
    payload: dict[str, Any] = {
        "ok": True,
        "voice_dir": str(PIPER_VOICE_DIR),
        "default_backend": _normalize_tts_backend(DEFAULT_TTS_BACKEND),
        "default_llm_backend": _normalize_llm_backend(DEFAULT_LLM_BACKEND),
        "default_voice": DEFAULT_PIPER_VOICE,
        "voices": _list_piper_voice_ids(),
        "llm_backends": [
            {"id": "openai", "label": f"OpenAI ({OPENAI_MODEL})"},
            {"id": "ollama", "label": f"Ollama ({OLLAMA_MODEL})"},
        ],
        "backends": [
            {"id": "piper", "label": "Piper"},
            {"id": "openai", "label": "OpenAI Voice"},
            {"id": "apple", "label": "Apple System Voice"},
            {"id": "kokoro", "label": "Kokoro"},
        ],
        "playback_targets": [
            {"id": "browser", "label": "This Browser"},
            {"id": "robot", "label": "Robot Speakers"},
        ],
        "piper": {
            "default_voice": DEFAULT_PIPER_VOICE,
            "voices": _list_piper_voice_ids(),
            "default_rate": 1.0,
            "default_noise_scale": DEFAULT_PIPER_NOISE_SCALE,
            "default_noise_w": DEFAULT_PIPER_NOISE_W,
            "default_sentence_silence": DEFAULT_PIPER_SENTENCE_SILENCE,
            "voice_defaults": _list_piper_voice_defaults(),
        },
        "openai": {
            "default_voice": OPENAI_TTS_DEFAULT_VOICE,
            "model": OPENAI_TTS_MODEL,
            "voices": list(OPENAI_TTS_VOICES),
        },
        "openai_llm": {
            "default_model": OPENAI_MODEL,
            "models": [OPENAI_MODEL],
        },
        "ollama": {
            "default_model": OLLAMA_MODEL,
            "api_url": OLLAMA_API_URL,
            "models": ollama_models,
        },
        "apple": {
            "default_voice": APPLE_TTS_DEFAULT_VOICE,
            "voices": _list_apple_voice_ids(),
            "default_rate": APPLE_TTS_DEFAULT_RATE,
        },
        "kokoro": {
            "default_voice": KOKORO_DEFAULT_VOICE,
            "voices": _list_kokoro_voice_ids(),
        },
        "tts_catalog_source": "local",
    }
    remote_catalog, remote_error = _fetch_remote_tts_catalog()
    if remote_catalog:
        payload["voice_dir"] = remote_catalog.get("voice_dir") or payload["voice_dir"]
        payload["default_backend"] = remote_catalog.get("default_backend") or payload["default_backend"]
        payload["default_voice"] = remote_catalog.get("default_voice") or payload["default_voice"]
        payload["default_llm_backend"] = remote_catalog.get("default_llm_backend") or payload["default_llm_backend"]
        payload["voices"] = remote_catalog.get("voices") or payload["voices"]
        payload["backends"] = remote_catalog.get("backends") or payload["backends"]
        payload["llm_backends"] = remote_catalog.get("llm_backends") or payload["llm_backends"]
        payload["piper"] = remote_catalog.get("piper") or payload["piper"]
        payload["openai"] = remote_catalog.get("openai") or payload["openai"]
        payload["openai_llm"] = remote_catalog.get("openai_llm") or payload["openai_llm"]
        payload["ollama"] = remote_catalog.get("ollama") or payload["ollama"]
        payload["apple"] = remote_catalog.get("apple") or payload["apple"]
        payload["kokoro"] = remote_catalog.get("kokoro") or payload["kokoro"]
        payload["tts_catalog_source"] = "remote"
        payload["tts_catalog_url"] = REMOTE_TTS_CATALOG_URL
    elif remote_error:
        payload["tts_catalog_error"] = remote_error
        payload["tts_catalog_url"] = REMOTE_TTS_CATALOG_URL
    return payload


def _ollama_supports_thinking(model: str) -> bool:
    model_id = (model or "").strip().lower()
    return (
        model_id.startswith("deepseek-r1")
        or model_id.startswith("qwen3")
        or model_id.startswith("gpt-oss")
        or model_id.startswith("deepseek-v3.1")
    )


def _query_openai_response(
    api_key: str, prompt: str, system_prompt: str, model: str
) -> tuple[str | None, str | None, str | None]:
    payload = {
        "model": model,
        "input": prompt,
        "instructions": system_prompt,
    }
    req = urlrequest.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
    ssl_ctx = None
    if ca_bundle:
        ssl_ctx = ssl.create_default_context(cafile=ca_bundle)
    else:
        try:
            import certifi  # type: ignore

            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_ctx = ssl.create_default_context()

    try:
        with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_SEC, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {body}", None
    except Exception as exc:
        return None, str(exc), None

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid OpenAI response: {exc}", None

    text = parsed.get("output_text")
    if isinstance(text, str) and text.strip():
        sanitized = _sanitize_model_reply(text)
        if sanitized:
            return sanitized, None, None

    output = parsed.get("output")
    chunks: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "output_text":
                    continue
                piece = part.get("text")
                if isinstance(piece, str):
                    chunks.append(piece)

    joined = "".join(chunks).strip()
    if joined:
        sanitized = _sanitize_model_reply(joined)
        if sanitized:
            return sanitized, None, None
    return None, "no text found in OpenAI response", None


def _query_ollama_response(
    prompt: str | None,
    system_prompt: str,
    model: str,
    messages: list[dict[str, str]] | None = None,
) -> tuple[str | None, str | None, str | None]:
    message_list: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if messages:
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if role not in ("system", "user", "assistant") or not content:
                continue
            message_list.append({"role": role, "content": content})
    elif isinstance(prompt, str) and prompt.strip():
        message_list.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "stream": False,
        "messages": message_list,
    }
    if _ollama_supports_thinking(model):
        payload["think"] = True
    req = urlrequest.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlrequest.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {body}", None
    except Exception as exc:
        return None, str(exc), None

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid Ollama response: {exc}", None

    thinking_text: str | None = None
    message = parsed.get("message")
    if isinstance(message, dict):
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking.strip():
            thinking_text = _sanitize_model_thinking(thinking)
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            sanitized = _sanitize_model_reply(content)
            if sanitized:
                return sanitized, None, thinking_text

    response = parsed.get("response")
    if isinstance(response, str) and response.strip():
        sanitized = _sanitize_model_reply(response)
        if sanitized:
            return sanitized, None, thinking_text
    return None, "no text found in Ollama response", thinking_text


def _list_ollama_model_ids() -> list[str]:
    req = urlrequest.Request(OLLAMA_API_URL.rsplit("/api/chat", 1)[0] + "/api/tags", method="GET")
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
    except Exception:
        return []

    try:
        parsed = json.loads(raw)
    except Exception:
        return []

    models = parsed.get("models")
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _prepare_tts_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", cleaned)
    cleaned = cleaned.replace("```", " ").replace("`", "")
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = cleaned.replace("*", "").replace("_", "")
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or (text or "").strip()


def _speak_with_backend(
    backend: str,
    voice: str,
    text: str,
    playback_target: str,
    piper_rate: float | None,
    piper_noise_scale: float | None,
    piper_noise_w: float | None,
    piper_sentence_silence: float | None,
    apple_rate: float | None,
    api_key: str,
) -> tuple[bool, str | None, str, str | None, str]:
    normalized_backend = _normalize_tts_backend(backend)
    voice_id = (voice or "").strip() or _default_voice_for_backend(normalized_backend)
    if normalized_backend == "openai":
        ok, error, resolved_voice_id, wav_bytes = _synthesize_with_openai(api_key, text, voice_id)
        local_mode = "browser"
    elif normalized_backend == "apple":
        ok, error, resolved_voice_id, wav_bytes = _synthesize_with_apple(text, voice_id, apple_rate)
        local_mode = "browser"
    elif normalized_backend == "kokoro":
        ok, error, resolved_voice_id, wav_bytes = _synthesize_with_kokoro(text, voice_id)
        local_mode = "browser"
    else:
        ok, error, resolved_voice_id, wav_bytes = _synthesize_with_piper(
            text,
            voice_id,
            requested_rate=piper_rate,
            requested_noise_scale=piper_noise_scale,
            requested_noise_w=piper_noise_w,
            requested_sentence_silence=piper_sentence_silence,
        )
        local_mode = PIPER_PLAYBACK_MODE
    if not ok or wav_bytes is None:
        return False, error, resolved_voice_id, None, "none"
    delivered, delivery_error, audio_b64, playback_mode = _deliver_wav_audio(
        wav_bytes,
        local_mode=local_mode,
        playback_target=_normalize_playback_target(playback_target),
    )
    return delivered, delivery_error, resolved_voice_id, audio_b64, playback_mode


def _supports_espeak_voice_failure(stderr_text: str) -> bool:
    low = (stderr_text or "").lower()
    if "espeak_voice" not in low and "--espeak_voice" not in low:
        return False
    return any(token in low for token in ("unrecognized", "unknown", "invalid option", "no such option"))


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


def _list_piper_voice_ids() -> list[str]:
    try:
        if not PIPER_VOICE_DIR.exists():
            return []
        voice_ids: list[str] = []
        for model_path in sorted(PIPER_VOICE_DIR.glob("*.onnx")):
            config_path = Path(str(model_path) + ".json")
            if not config_path.exists():
                continue
            voice_ids.append(model_path.stem)
        return voice_ids
    except Exception:
        return []


def _resolve_piper_voice(voice: str) -> tuple[Path | None, Path | None, str]:
    voice_id = voice.strip() or DEFAULT_PIPER_VOICE
    model = PIPER_VOICE_DIR / f"{voice_id}.onnx"
    config = PIPER_VOICE_DIR / f"{voice_id}.onnx.json"
    if model.exists() and config.exists():
        return model, config, voice_id
    return None, None, voice_id


def _read_piper_voice_defaults(config_path: Path) -> dict[str, float]:
    defaults = {
        "rate": 1.0,
        "noise_scale": DEFAULT_PIPER_NOISE_SCALE,
        "noise_w": DEFAULT_PIPER_NOISE_W,
        "sentence_silence": DEFAULT_PIPER_SENTENCE_SILENCE,
    }
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    inference = parsed.get("inference")
    if not isinstance(inference, dict):
        return defaults

    length_scale = inference.get("length_scale")
    if isinstance(length_scale, (int, float)) and float(length_scale) > 0:
        defaults["rate"] = max(0.5, min(2.0, 1.0 / float(length_scale)))

    noise_scale = inference.get("noise_scale")
    if isinstance(noise_scale, (int, float)):
        defaults["noise_scale"] = max(0.1, min(2.0, float(noise_scale)))

    noise_w = inference.get("noise_w")
    if isinstance(noise_w, (int, float)):
        defaults["noise_w"] = max(0.1, min(2.0, float(noise_w)))

    return defaults


def _list_piper_voice_defaults() -> dict[str, dict[str, float]]:
    defaults: dict[str, dict[str, float]] = {}
    for voice_id in _list_piper_voice_ids():
        _model, config, resolved_voice_id = _resolve_piper_voice(voice_id)
        if config is None:
            continue
        defaults[resolved_voice_id] = _read_piper_voice_defaults(config)
    return defaults
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


def _resolve_piper_length_scale(requested_rate: float | None) -> float | None:
    base_length_scale: float | None = None
    if PIPER_LENGTH_SCALE:
        try:
            parsed = float(PIPER_LENGTH_SCALE)
            if parsed > 0:
                base_length_scale = parsed
        except Exception:
            base_length_scale = None
    if requested_rate is None:
        return base_length_scale
    try:
        rate = float(requested_rate)
    except Exception:
        return base_length_scale
    if rate <= 0:
        return base_length_scale
    effective = (base_length_scale or 1.0) / rate
    return min(3.0, max(0.25, effective))


def _apple_tts_ready_state() -> tuple[bool, str | None]:
    if sys.platform != "darwin":
        return False, "Apple TTS is only available on macOS"
    if not shutil.which("say"):
        return False, "say command not found"
    if not shutil.which("afconvert"):
        return False, "afconvert command not found"
    return True, None


def _kokoro_voice_lang_code(voice: str) -> str:
    voice_id = (voice or "").strip().lower()
    if len(voice_id) >= 1:
        prefix = voice_id[0]
        if prefix in ("a", "b", "e", "f", "h", "i", "j", "p", "z"):
            return prefix
    return "a"


def _kokoro_ready_state() -> tuple[bool, str | None]:
    try:
        import importlib.util

        if importlib.util.find_spec("kokoro") is None:
            return False, "kokoro package not installed"
    except Exception as exc:
        return False, str(exc)
    return True, None


def _list_kokoro_voice_ids() -> list[str]:
    try:
        from huggingface_hub import list_repo_files  # type: ignore

        files = list_repo_files(KOKORO_REPO_ID)
        voices = sorted(
            {
                file_path.split("/")[-1][:-3]
                for file_path in files
                if file_path.startswith("voices/") and file_path.endswith(".pt")
            }
        )
        return voices or DEFAULT_KOKORO_VOICES
    except Exception:
        return list(DEFAULT_KOKORO_VOICES)


def _get_kokoro_pipeline(lang_code: str) -> Any:
    with KOKORO_PIPELINE_LOCK:
        cached = KOKORO_PIPELINE_CACHE.get(lang_code)
        if cached is not None:
            return cached
        from kokoro import KPipeline  # type: ignore

        pipeline = KPipeline(lang_code=lang_code, repo_id=KOKORO_REPO_ID)
        KOKORO_PIPELINE_CACHE[lang_code] = pipeline
        return pipeline


def _float_audio_to_wav_bytes(audio: Any, sample_rate: int) -> bytes:
    import numpy as np  # type: ignore

    samples = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return out.getvalue()


def _list_apple_voice_ids() -> list[str]:
    ready, _ = _apple_tts_ready_state()
    if not ready:
        return []
    try:
        proc = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            timeout=5,
            check=False,
            text=True,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    voices: list[str] = []
    for raw in (proc.stdout or "").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        match = re.match(r"^\s*([^\s].*?\S)\s{2,}", line)
        if not match:
            continue
        voice_id = match.group(1).strip()
        if voice_id:
            voices.append(voice_id)
    return voices


def _resolve_apple_words_per_minute(requested_rate: float | None) -> int:
    base_rate = APPLE_TTS_DEFAULT_RATE if APPLE_TTS_DEFAULT_RATE > 0 else 1.0
    try:
        rate = float(requested_rate) if requested_rate is not None else base_rate
    except Exception:
        rate = base_rate
    rate = min(2.0, max(0.5, rate))
    return max(90, min(360, int(round(175 * rate))))


def _synthesize_with_piper(
    text: str,
    voice: str,
    requested_rate: float | None = None,
    requested_noise_scale: float | None = None,
    requested_noise_w: float | None = None,
    requested_sentence_silence: float | None = None,
) -> tuple[bool, str | None, str, bytes | None]:
    ready, ready_err = _piper_ready_state()
    if not ready:
        return False, ready_err, voice, None

    model, config, voice_id = _resolve_piper_voice(voice)
    if model is None or config is None:
        return False, f"piper voice not found: {voice_id}", voice_id, None

    piper_cmd_base = [str(PIPER_BIN), "--model", str(model), "--config", str(config)]
    length_scale = _resolve_piper_length_scale(requested_rate)
    if length_scale is not None:
        piper_cmd_base.extend(["--length_scale", str(length_scale)])
    noise_scale = requested_noise_scale if requested_noise_scale is not None else DEFAULT_PIPER_NOISE_SCALE
    noise_w = requested_noise_w if requested_noise_w is not None else DEFAULT_PIPER_NOISE_W
    sentence_silence = (
        requested_sentence_silence
        if requested_sentence_silence is not None
        else DEFAULT_PIPER_SENTENCE_SILENCE
    )
    piper_cmd_base.extend(["--noise_scale", str(noise_scale)])
    piper_cmd_base.extend(["--noise_w", str(noise_w)])
    piper_cmd_base.extend(["--sentence_silence", str(sentence_silence)])
    if PIPER_ESPEAK_VOICE:
        piper_cmd_base.extend(["--espeak_voice", PIPER_ESPEAK_VOICE])
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
            if piper_proc.returncode != 0 and PIPER_ESPEAK_VOICE and _supports_espeak_voice_failure(piper_stderr):
                fallback_cmd = [str(PIPER_BIN), "--model", str(model), "--config", str(config)]
                if length_scale is not None:
                    fallback_cmd.extend(["--length_scale", str(length_scale)])
                fallback_cmd.extend(["--noise_scale", str(noise_scale)])
                fallback_cmd.extend(["--noise_w", str(noise_w)])
                fallback_cmd.extend(["--sentence_silence", str(sentence_silence)])
                fallback_cmd.extend(["--output_file", wav_file.name])
                _debug_log("piper --espeak_voice unsupported; retrying without it")
                _debug_log(f"$ {' '.join(shlex.quote(p) for p in fallback_cmd)}")
                piper_proc = subprocess.run(
                    fallback_cmd,
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=25,
                    check=False,
                )
                piper_stderr = (piper_proc.stderr or b"").decode("utf-8", errors="ignore")
            if piper_proc.returncode != 0:
                return False, piper_stderr.strip() or f"piper rc={piper_proc.returncode}", voice_id, None

            wav_bytes = Path(wav_file.name).read_bytes()
            if not wav_bytes:
                return False, "piper produced empty audio", voice_id, None
            return True, None, voice_id, wav_bytes
    except Exception as exc:
        return False, str(exc), voice_id, None


def _synthesize_with_openai(api_key: str, text: str, voice: str) -> tuple[bool, str | None, str, bytes | None]:
    voice_id = voice.strip() or OPENAI_TTS_DEFAULT_VOICE
    payload = {
        "model": OPENAI_TTS_MODEL,
        "input": text,
        "voice": voice_id,
        "response_format": "wav",
    }
    req = urlrequest.Request(
        OPENAI_TTS_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
    ssl_ctx = None
    if ca_bundle:
        ssl_ctx = ssl.create_default_context(cafile=ca_bundle)
    else:
        try:
            import certifi  # type: ignore

            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_ctx = ssl.create_default_context()

    try:
        with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_SEC, context=ssl_ctx) as resp:
            wav_bytes = resp.read()
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {body}", voice_id, None
    except Exception as exc:
        return False, str(exc), voice_id, None

    if not wav_bytes:
        return False, "OpenAI TTS returned empty audio", voice_id, None

    return True, None, voice_id, wav_bytes


def _synthesize_with_apple(text: str, voice: str, requested_rate: float | None = None) -> tuple[bool, str | None, str, bytes | None]:
    ready, ready_err = _apple_tts_ready_state()
    voice_id = voice.strip() or APPLE_TTS_DEFAULT_VOICE
    if not ready:
        return False, ready_err, voice_id, None
    try:
        with tempfile.TemporaryDirectory(prefix="apple_tts_") as temp_dir:
            temp_path = Path(temp_dir)
            aiff_path = temp_path / "speech.aiff"
            wav_path = temp_path / "speech.wav"
            say_cmd = ["say", "-v", voice_id, "-r", str(_resolve_apple_words_per_minute(requested_rate)), "-o", str(aiff_path), text]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in say_cmd)}")
            say_proc = subprocess.run(
                say_cmd,
                capture_output=True,
                timeout=30,
                check=False,
                text=True,
            )
            if say_proc.returncode != 0:
                return False, (say_proc.stderr or say_proc.stdout or "").strip() or f"say rc={say_proc.returncode}", voice_id, None
            convert_cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff_path), str(wav_path)]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in convert_cmd)}")
            convert_proc = subprocess.run(
                convert_cmd,
                capture_output=True,
                timeout=30,
                check=False,
                text=True,
            )
            if convert_proc.returncode != 0:
                return (
                    False,
                    (convert_proc.stderr or convert_proc.stdout or "").strip() or f"afconvert rc={convert_proc.returncode}",
                    voice_id,
                    None,
                )
            wav_bytes = wav_path.read_bytes()
            if not wav_bytes:
                return False, "Apple TTS produced empty audio", voice_id, None
            return True, None, voice_id, wav_bytes
    except Exception as exc:
        return False, str(exc), voice_id, None


def _synthesize_with_kokoro(text: str, voice: str) -> tuple[bool, str | None, str, bytes | None]:
    ready, ready_err = _kokoro_ready_state()
    voice_id = voice.strip() or KOKORO_DEFAULT_VOICE
    if not ready:
        return False, ready_err, voice_id, None
    lang_code = _kokoro_voice_lang_code(voice_id)
    try:
        pipeline = _get_kokoro_pipeline(lang_code)
        wav_chunks: list[bytes] = []
        for result in pipeline(text, voice=voice_id, speed=1.0, split_pattern=r"\n+"):
            audio = getattr(result, "audio", None)
            if audio is None:
                continue
            wav_chunks.append(_float_audio_to_wav_bytes(audio, sample_rate=24000))
        if not wav_chunks:
            return False, "Kokoro produced empty audio", voice_id, None
        if len(wav_chunks) == 1:
            return True, None, voice_id, wav_chunks[0]
        merged = io.BytesIO()
        with wave.open(merged, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            for chunk in wav_chunks:
                with wave.open(io.BytesIO(chunk), "rb") as source:
                    wav_file.writeframes(source.readframes(source.getnframes()))
        return True, None, voice_id, merged.getvalue()
    except Exception as exc:
        return False, str(exc), voice_id, None


def _play_wav_locally(wav_bytes: bytes, local_mode: str) -> tuple[bool, str | None, str | None, str]:
    mode = (local_mode or "browser").strip().lower()
    if mode not in ("auto", "aplay", "afplay", "browser"):
        mode = "browser"
    try:
        with tempfile.NamedTemporaryFile(prefix="speech_", suffix=".wav", delete=True) as wav_file:
            wav_file.write(wav_bytes)
            wav_file.flush()
            if mode in ("auto", "aplay"):
                if shutil.which("aplay"):
                    aplay_cmd = ["aplay", "-q", "-D", PIPER_APLAY_DEVICE, wav_file.name]
                    _debug_log(f"$ {' '.join(shlex.quote(p) for p in aplay_cmd)}")
                    aplay_proc = subprocess.run(aplay_cmd, capture_output=True, timeout=25, check=False)
                    aplay_stderr = (aplay_proc.stderr or b"").decode("utf-8", errors="ignore")
                    if aplay_proc.returncode == 0:
                        return True, None, None, "aplay"
                    if mode == "aplay":
                        return False, aplay_stderr.strip() or f"aplay rc={aplay_proc.returncode}", None, "aplay"
                    _debug_log("aplay failed, falling back to browser audio playback")
                elif mode == "aplay":
                    return False, "aplay not found", None, "aplay"
            if mode in ("auto", "afplay"):
                if shutil.which("afplay"):
                    afplay_cmd = ["afplay", wav_file.name]
                    _debug_log(f"$ {' '.join(shlex.quote(p) for p in afplay_cmd)}")
                    afplay_proc = subprocess.run(afplay_cmd, capture_output=True, timeout=25, check=False)
                    afplay_stderr = (afplay_proc.stderr or b"").decode("utf-8", errors="ignore")
                    if afplay_proc.returncode == 0:
                        return True, None, None, "afplay"
                    if mode == "afplay":
                        return False, afplay_stderr.strip() or f"afplay rc={afplay_proc.returncode}", None, "afplay"
                    _debug_log("afplay failed, falling back to browser audio playback")
                elif mode == "afplay":
                    return False, "afplay not found", None, "afplay"
            return True, None, base64.b64encode(wav_bytes).decode("ascii"), "browser"
    except Exception as exc:
        return False, str(exc), None, "none"


def _play_wav_on_robot_blocking(wav_bytes: bytes) -> tuple[bool, str | None, str]:
    ssh_target = f"{ROBOT_AUDIO_SSH_USER}@{ROBOT_AUDIO_SSH_HOST}"
    remote_file = f"{ROBOT_AUDIO_DIR.rstrip('/')}/speech_{int(time.time() * 1000)}.wav"
    try:
        with tempfile.NamedTemporaryFile(prefix="robot_speech_", suffix=".wav", delete=True) as wav_file:
            wav_file.write(wav_bytes)
            wav_file.flush()
            mkdir_cmd = [
                "ssh",
                "-p",
                str(ROBOT_AUDIO_SSH_PORT),
                ssh_target,
                f"mkdir -p {shlex.quote(ROBOT_AUDIO_DIR)}",
            ]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in mkdir_cmd)}")
            mkdir_proc = subprocess.run(mkdir_cmd, capture_output=True, timeout=15, check=False, text=True)
            if mkdir_proc.returncode != 0:
                return False, (mkdir_proc.stderr or mkdir_proc.stdout or "").strip() or f"ssh rc={mkdir_proc.returncode}", "robot"
            scp_cmd = [
                "scp",
                "-P",
                str(ROBOT_AUDIO_SSH_PORT),
                wav_file.name,
                f"{ssh_target}:{remote_file}",
            ]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in scp_cmd)}")
            scp_proc = subprocess.run(scp_cmd, capture_output=True, timeout=20, check=False, text=True)
            if scp_proc.returncode != 0:
                return False, (scp_proc.stderr or scp_proc.stdout or "").strip() or f"scp rc={scp_proc.returncode}", "robot"
            remote_cmd = (
                f"aplay -q -D {shlex.quote(ROBOT_AUDIO_APLAY_DEVICE)} {shlex.quote(remote_file)}"
                f" && rm -f {shlex.quote(remote_file)}"
            )
            ssh_cmd = ["ssh", "-p", str(ROBOT_AUDIO_SSH_PORT), ssh_target, remote_cmd]
            _debug_log(f"$ {' '.join(shlex.quote(p) for p in ssh_cmd)}")
            ssh_proc = subprocess.run(ssh_cmd, capture_output=True, timeout=45, check=False, text=True)
            if ssh_proc.returncode != 0:
                return False, (ssh_proc.stderr or ssh_proc.stdout or "").strip() or f"ssh rc={ssh_proc.returncode}", "robot"
            return True, None, "robot"
    except Exception as exc:
        return False, str(exc), "robot"


def _play_wav_on_robot(wav_bytes: bytes) -> tuple[bool, str | None, str]:
    def _worker(audio_bytes: bytes) -> None:
        ok, error, _mode = _play_wav_on_robot_blocking(audio_bytes)
        if not ok and error:
            _debug_log(f"robot playback failed: {error}")

    try:
        threading.Thread(target=_worker, args=(bytes(wav_bytes),), daemon=True).start()
        return True, None, "robot"
    except Exception as exc:
        return False, str(exc), "robot"


def _deliver_wav_audio(wav_bytes: bytes, local_mode: str, playback_target: str) -> tuple[bool, str | None, str | None, str]:
    if playback_target == "robot":
        ok, error, playback_mode = _play_wav_on_robot(wav_bytes)
        return ok, error, None, playback_mode
    return _play_wav_locally(wav_bytes, local_mode)


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


def _parse_plain_percent(output: str) -> int | None:
    text = (output or "").strip()
    if not text or text == "missing value":
        return None
    match = re.search(r"\b([0-9]{1,3})\b", text)
    if not match:
        return None
    try:
        return max(0, min(100, int(match.group(1))))
    except Exception:
        return None


def _parse_macos_volume_settings(output: str) -> int | None:
    text = (output or "").strip()
    if not text:
        return None
    match = re.search(r"output volume:([0-9]{1,3}|missing value)", text)
    if not match:
        return None
    token = match.group(1)
    if token == "missing value":
        return None
    try:
        return max(0, min(100, int(token)))
    except Exception:
        return None


def _read_volume_percent() -> tuple[int | None, str]:
    commands: list[tuple[str, str]] = []
    if sys.platform == "darwin" and shutil.which("osascript"):
        commands.append(("osascript:output", "osascript -e 'output volume of (get volume settings)'"))
        commands.append(("osascript:settings", "osascript -e 'get volume settings'"))
    if shutil.which("amixer"):
        commands.append(("amixer:pulse", "amixer -D pulse sget Master"))
        commands.append(("amixer:default", "amixer sget Master"))
    if shutil.which("pactl"):
        commands.append(("pactl:default", "pactl get-sink-volume @DEFAULT_SINK@"))
    if not commands:
        if LAST_SET_VOLUME_PERCENT is not None:
            return LAST_SET_VOLUME_PERCENT, "cache:last_set"
        return None, "unavailable"

    for source, cmd in commands:
        rc, out = _run_shell(cmd, timeout_sec=3, log_command=False, log_output=False)
        if rc != 0:
            continue
        if source.startswith("osascript:"):
            pct = _parse_plain_percent(out) if source == "osascript:output" else _parse_macos_volume_settings(out)
            if pct is not None:
                return pct, source
            if source == "osascript:settings":
                muted_match = re.search(r"output muted:(true|false)", out)
                if muted_match and muted_match.group(1) == "true":
                    return 0, source
            continue
        pct = _parse_volume_percent(out)
        if pct is not None:
            return pct, source
    if LAST_SET_VOLUME_PERCENT is not None:
        return LAST_SET_VOLUME_PERCENT, "cache:last_set"
    return None, "unavailable"


def _set_volume_percent(percent: int) -> tuple[bool, str, str | None]:
    global LAST_SET_VOLUME_PERCENT
    pct = max(0, min(100, int(percent)))
    commands: list[tuple[str, str]] = []
    if sys.platform == "darwin" and shutil.which("osascript"):
        commands.append(("osascript:output", "osascript -e 'set volume output volume " + str(pct) + "'"))
    commands.append(
        (
            "bashrc:vol",
            "source ~/.bashrc >/dev/null 2>&1 || true; "
            + "if command -v vol >/dev/null 2>&1; then vol "
            + str(pct)
            + "; else exit 127; fi",
        )
    )
    if shutil.which("amixer"):
        commands.append(("amixer:pulse", "amixer -D pulse sset Master " + str(pct) + "%"))
    if shutil.which("pactl"):
        commands.append(("pactl:default", "pactl set-sink-volume @DEFAULT_SINK@ " + str(pct) + "%"))

    last_error: str | None = None
    for source, cmd in commands:
        rc, out = _run_shell(cmd, timeout_sec=4, log_command=False, log_output=False)
        if rc == 0:
            LAST_SET_VOLUME_PERCENT = pct
            return True, source, None
        last_error = out.strip() or f"rc={rc}"
    return False, "unavailable", last_error


def _ros2_cli_ready() -> bool:
    return (
        shutil.which("ros2") is not None
        and Path("/opt/ros/humble/setup.bash").exists()
        and Path("/opt/booster/BoosterRos2Interface/install/setup.bash").exists()
    )


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
