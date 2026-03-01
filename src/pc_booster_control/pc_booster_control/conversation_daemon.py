import base64
import json
import os
import shlex
import shutil
import signal
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


OPENAI_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_TIMEOUT_SEC = 60
OPENAI_KEY_NAMES = ("OPENAI_API_KEY", "CHATGPT_API_KEY", "CHAT_GPT_API", "API_KEY")
DEFAULT_SYSTEM_PROMPT = (
    "You are Booster K1's onboard assistant. Keep responses concise, practical, and lightly witty."
)

PIPER_BIN = Path("/home/booster/piper/piper/piper")
PIPER_VOICE_DIR = Path("/home/booster/piper/voices")
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"
PIPER_APLAY_DEVICE = "plughw:CARD=Device,DEV=0"
PIPER_PLAYBACK_MODE = "auto"
PIPER_LENGTH_SCALE = ""
PIPER_ESPEAK_VOICE = ""

CONVO_ENABLED = True
CONVO_USE_WAKE_WORD = True
CONVO_WAKE_WORD = "hal"
CONVO_WAKE_CMD = ""
CONVO_STT_CMD = ""
CONVO_WAKE_TIMEOUT_SEC = 1800
CONVO_STT_TIMEOUT_SEC = 25
CONVO_VOICE_TYPE = DEFAULT_PIPER_VOICE
CONVO_WAKE_ONLY = False
CONVO_MIN_TEXT_LEN = 2
CONVO_RETRY_SLEEP_SEC = 1.5
CONVO_WAKE_BEEP_ENABLED = True
CONVO_WAKE_BEEP_FREQ_HZ = 880
CONVO_WAKE_BEEP_DURATION_MS = 140

_STOP = False


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


def _reload_config_from_env() -> None:
    global OPENAI_API_URL, OPENAI_MODEL, OPENAI_TIMEOUT_SEC
    global PIPER_BIN, PIPER_VOICE_DIR, DEFAULT_PIPER_VOICE, PIPER_APLAY_DEVICE
    global PIPER_PLAYBACK_MODE, PIPER_LENGTH_SCALE, PIPER_ESPEAK_VOICE
    global CONVO_ENABLED, CONVO_USE_WAKE_WORD, CONVO_WAKE_WORD, CONVO_WAKE_CMD, CONVO_STT_CMD
    global CONVO_WAKE_TIMEOUT_SEC, CONVO_STT_TIMEOUT_SEC, CONVO_VOICE_TYPE
    global CONVO_WAKE_ONLY
    global CONVO_MIN_TEXT_LEN, CONVO_RETRY_SLEEP_SEC
    global CONVO_WAKE_BEEP_ENABLED, CONVO_WAKE_BEEP_FREQ_HZ, CONVO_WAKE_BEEP_DURATION_MS

    OPENAI_API_URL = os.environ.get("BOOSTER_OPENAI_API_URL", "https://api.openai.com/v1/responses")
    OPENAI_MODEL = os.environ.get("BOOSTER_OPENAI_MODEL", "gpt-4.1-mini")
    OPENAI_TIMEOUT_SEC = int(os.environ.get("BOOSTER_OPENAI_TIMEOUT_SEC", "60"))

    PIPER_BIN = Path(os.environ.get("BOOSTER_PIPER_BIN", "/home/booster/piper/piper/piper"))
    PIPER_VOICE_DIR = Path(os.environ.get("BOOSTER_PIPER_VOICE_DIR", "/home/booster/piper/voices"))
    DEFAULT_PIPER_VOICE = os.environ.get("BOOSTER_PIPER_DEFAULT_VOICE", "en_US-lessac-medium")
    PIPER_APLAY_DEVICE = os.environ.get("BOOSTER_PIPER_APLAY_DEVICE", "plughw:CARD=Device,DEV=0")
    PIPER_PLAYBACK_MODE = os.environ.get("BOOSTER_PIPER_PLAYBACK_MODE", "auto").strip().lower()
    PIPER_LENGTH_SCALE = os.environ.get("BOOSTER_PIPER_LENGTH_SCALE", "").strip()
    PIPER_ESPEAK_VOICE = os.environ.get("BOOSTER_PIPER_ESPEAK_VOICE", "").strip()

    CONVO_ENABLED = os.environ.get("BOOSTER_CONVERSATION_ENABLED", "1").strip() not in ("0", "false", "False")
    CONVO_USE_WAKE_WORD = os.environ.get("BOOSTER_CONVERSATION_USE_WAKE_WORD", "1").strip() not in (
        "0",
        "false",
        "False",
    )
    CONVO_WAKE_WORD = os.environ.get("BOOSTER_CONVERSATION_WAKE_WORD", "hal").strip() or "hal"
    CONVO_WAKE_CMD = os.environ.get("BOOSTER_SHERPA_KWS_CMD", "").strip()
    CONVO_STT_CMD = os.environ.get("BOOSTER_SHERPA_STT_CMD", "").strip()
    CONVO_WAKE_TIMEOUT_SEC = int(os.environ.get("BOOSTER_SHERPA_KWS_TIMEOUT_SEC", "1800"))
    CONVO_STT_TIMEOUT_SEC = int(os.environ.get("BOOSTER_SHERPA_STT_TIMEOUT_SEC", "25"))
    CONVO_VOICE_TYPE = os.environ.get("BOOSTER_CONVERSATION_VOICE_TYPE", DEFAULT_PIPER_VOICE).strip() or DEFAULT_PIPER_VOICE
    CONVO_WAKE_ONLY = os.environ.get("BOOSTER_CONVERSATION_WAKE_ONLY", "0").strip() in ("1", "true", "True")
    CONVO_MIN_TEXT_LEN = int(os.environ.get("BOOSTER_CONVERSATION_MIN_TEXT_LEN", "2"))
    CONVO_RETRY_SLEEP_SEC = float(os.environ.get("BOOSTER_CONVERSATION_RETRY_SLEEP_SEC", "1.5"))
    CONVO_WAKE_BEEP_ENABLED = os.environ.get("BOOSTER_CONVERSATION_WAKE_BEEP_ENABLED", "1").strip() not in (
        "0",
        "false",
        "False",
    )
    CONVO_WAKE_BEEP_FREQ_HZ = int(os.environ.get("BOOSTER_CONVERSATION_WAKE_BEEP_FREQ_HZ", "880"))
    CONVO_WAKE_BEEP_DURATION_MS = int(os.environ.get("BOOSTER_CONVERSATION_WAKE_BEEP_DURATION_MS", "140"))


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[conversation {ts}] {msg}", flush=True)


def _resolve_openai_api_key() -> str:
    for name in OPENAI_KEY_NAMES:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    return ""


def _query_openai_response(api_key: str, prompt: str, system_prompt: str, model: str) -> tuple[str | None, str | None]:
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
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return None, str(exc)
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid OpenAI response: {exc}"
    text = parsed.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip(), None
    return None, "no text found in OpenAI response"


def _prepare_tts_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("```", " ").replace("`", "")
    cleaned = cleaned.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    cleaned = " ".join(cleaned.split())
    return cleaned


def _supports_espeak_voice_failure(stderr_text: str) -> bool:
    low = (stderr_text or "").lower()
    if "espeak_voice" not in low and "--espeak_voice" not in low:
        return False
    return any(token in low for token in ("unrecognized", "unknown", "invalid option", "no such option"))


def _resolve_piper_voice(voice: str) -> tuple[Path | None, Path | None, str]:
    voice_id = (voice or "").strip() or DEFAULT_PIPER_VOICE
    model = PIPER_VOICE_DIR / f"{voice_id}.onnx"
    config = PIPER_VOICE_DIR / f"{voice_id}.onnx.json"
    if model.exists() and config.exists():
        return model, config, voice_id
    return None, None, voice_id


def _speak_with_piper(text: str, voice: str) -> tuple[bool, str | None]:
    if not PIPER_BIN.exists():
        return False, f"piper binary not found: {PIPER_BIN}"
    model, config, voice_id = _resolve_piper_voice(voice)
    if model is None or config is None:
        return False, f"piper voice not found: {voice_id}"
    cmd_base = [str(PIPER_BIN), "--model", str(model), "--config", str(config)]
    if PIPER_LENGTH_SCALE:
        try:
            value = float(PIPER_LENGTH_SCALE)
            if value > 0:
                cmd_base.extend(["--length_scale", str(value)])
        except Exception:
            pass
    if PIPER_ESPEAK_VOICE:
        cmd_base.extend(["--espeak_voice", PIPER_ESPEAK_VOICE])
    try:
        with tempfile.NamedTemporaryFile(prefix="conv_", suffix=".wav", delete=True) as wav_file:
            piper_cmd = cmd_base + ["--output_file", wav_file.name]
            _log(f"tts synth via piper voice={voice_id}")
            synth = subprocess.run(
                piper_cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=35,
                check=False,
            )
            err_text = (synth.stderr or b"").decode("utf-8", errors="ignore")
            if synth.returncode != 0 and PIPER_ESPEAK_VOICE and _supports_espeak_voice_failure(err_text):
                fallback = [str(PIPER_BIN), "--model", str(model), "--config", str(config)]
                if PIPER_LENGTH_SCALE:
                    try:
                        value = float(PIPER_LENGTH_SCALE)
                        if value > 0:
                            fallback.extend(["--length_scale", str(value)])
                    except Exception:
                        pass
                fallback.extend(["--output_file", wav_file.name])
                synth = subprocess.run(
                    fallback,
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=35,
                    check=False,
                )
                err_text = (synth.stderr or b"").decode("utf-8", errors="ignore")
            if synth.returncode != 0:
                return False, err_text.strip() or f"piper rc={synth.returncode}"
            if PIPER_PLAYBACK_MODE in ("aplay", "auto") and shutil.which("aplay"):
                play = subprocess.run(
                    ["aplay", "-q", "-D", PIPER_APLAY_DEVICE, wav_file.name],
                    capture_output=True,
                    timeout=35,
                    check=False,
                )
                if play.returncode == 0:
                    return True, None
                if PIPER_PLAYBACK_MODE == "aplay":
                    return False, (play.stderr or b"").decode("utf-8", errors="ignore").strip() or "aplay failed"
            if PIPER_PLAYBACK_MODE in ("afplay", "auto") and shutil.which("afplay"):
                play = subprocess.run(
                    ["afplay", wav_file.name],
                    capture_output=True,
                    timeout=35,
                    check=False,
                )
                if play.returncode == 0:
                    return True, None
                if PIPER_PLAYBACK_MODE == "afplay":
                    return False, (play.stderr or b"").decode("utf-8", errors="ignore").strip() or "afplay failed"
            # Last fallback: return synthesized audio to nowhere (daemon mode has no browser playback).
            _ = base64.b64encode(Path(wav_file.name).read_bytes()).decode("ascii")
            return True, None
    except Exception as exc:
        return False, str(exc)


def _run_shell_capture(cmd: str, timeout_sec: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, output
    except Exception as exc:
        return 1, str(exc)


def _extract_marked_output(raw: str, prefix: str) -> str:
    if not raw:
        return ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _render_wake_cmd() -> str:
    if not CONVO_WAKE_CMD:
        return ""
    return CONVO_WAKE_CMD.replace("{wake_word}", CONVO_WAKE_WORD)


def _play_wake_beep() -> None:
    if not CONVO_WAKE_BEEP_ENABLED:
        return
    sr = 16000
    duration_ms = max(40, min(1000, CONVO_WAKE_BEEP_DURATION_MS))
    freq_hz = max(120, min(5000, CONVO_WAKE_BEEP_FREQ_HZ))
    n = int(sr * (duration_ms / 1000.0))
    if n <= 0:
        return
    try:
        import math
        import wave

        with tempfile.NamedTemporaryFile(prefix="wake_", suffix=".wav", delete=True) as wav:
            with wave.open(wav.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                frames = bytearray()
                for i in range(n):
                    amp = int(14000 * math.sin((2.0 * math.pi * freq_hz * i) / sr))
                    frames.extend(int(amp).to_bytes(2, byteorder="little", signed=True))
                wf.writeframes(bytes(frames))
            if shutil.which("aplay"):
                subprocess.run(
                    ["aplay", "-q", "-D", PIPER_APLAY_DEVICE, wav.name],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                return
            if shutil.which("afplay"):
                subprocess.run(["afplay", wav.name], capture_output=True, timeout=5, check=False)
    except Exception:
        return


def _wait_for_wake_word() -> bool:
    if not CONVO_USE_WAKE_WORD:
        return True
    wake_cmd = _render_wake_cmd()
    if not wake_cmd:
        _log("wake word enabled but BOOSTER_SHERPA_KWS_CMD is empty")
        time.sleep(CONVO_RETRY_SLEEP_SEC)
        return False
    _log(f"waiting wake word: {CONVO_WAKE_WORD}")
    rc, out = _run_shell_capture(wake_cmd, timeout_sec=CONVO_WAKE_TIMEOUT_SEC)
    if rc != 0:
        _log(f"wake command failed rc={rc}: {out[:300]}")
        time.sleep(CONVO_RETRY_SLEEP_SEC)
        return False
    wake_text = _extract_marked_output(out, "__WAKE__:")
    if not wake_text:
        _log("wake command returned without wake marker; ignoring")
        time.sleep(CONVO_RETRY_SLEEP_SEC)
        return False
    _log(f"wake detected: {wake_text}")
    _play_wake_beep()
    return True


def _capture_user_text() -> str | None:
    if not CONVO_STT_CMD:
        _log("BOOSTER_SHERPA_STT_CMD is empty")
        time.sleep(CONVO_RETRY_SLEEP_SEC)
        return None
    rc, out = _run_shell_capture(CONVO_STT_CMD, timeout_sec=CONVO_STT_TIMEOUT_SEC)
    if rc != 0:
        _log(f"stt command failed rc={rc}: {out[:300]}")
        time.sleep(CONVO_RETRY_SLEEP_SEC)
        return None
    text = _extract_marked_output(out, "__STT__:")
    if not text:
        # Fallback for legacy wrappers; ignore known framework noise.
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        lines = [
            line
            for line in lines
            if not line.startswith("Current sample rate:")
            and line != "Recording started!"
            and "No microphone devices found" not in line
        ]
        text = lines[-1].strip() if lines else ""
    if len(text) < CONVO_MIN_TEXT_LEN:
        _log("stt text too short; ignoring")
        return None
    _log(f"user: {text}")
    return text


def _handle_signal(signum, _frame) -> None:  # type: ignore[no-untyped-def]
    global _STOP
    _STOP = True
    _log(f"signal received: {signum}; stopping")


def main() -> int:
    _load_env_file()
    _reload_config_from_env()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if not CONVO_ENABLED:
        _log("conversation disabled by BOOSTER_CONVERSATION_ENABLED")
        return 0

    api_key = _resolve_openai_api_key()
    if not api_key:
        _log("OpenAI key missing (OPENAI_API_KEY/CHATGPT_API_KEY)")
        return 1
    system_prompt = os.environ.get("CHATGPT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT).strip() or DEFAULT_SYSTEM_PROMPT
    _log(f"conversation daemon started (wake_word={CONVO_WAKE_WORD})")

    while not _STOP:
        if not _wait_for_wake_word():
            continue
        if CONVO_WAKE_ONLY:
            continue
        user_text = _capture_user_text()
        if not user_text:
            continue
        assistant_text, err = _query_openai_response(api_key, user_text, system_prompt, OPENAI_MODEL)
        if err:
            _log(f"openai error: {err}")
            time.sleep(CONVO_RETRY_SLEEP_SEC)
            continue
        if not assistant_text:
            _log("openai returned empty text")
            continue
        _log(f"assistant: {assistant_text}")
        tts_text = _prepare_tts_text(assistant_text)
        ok, speak_err = _speak_with_piper(tts_text, CONVO_VOICE_TYPE)
        if not ok:
            _log(f"tts error: {speak_err}")
            time.sleep(CONVO_RETRY_SLEEP_SEC)
            continue
    _log("conversation daemon stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
