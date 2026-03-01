#!/usr/bin/env python3
"""Wait for wake word from ALSA mic using streaming ASR and exit 0 when detected."""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import sherpa_onnx


def _candidate_capture_devices(device_name: str) -> list[str]:
    raw = (device_name or "").strip()
    if not raw:
        return []
    candidates = [raw]
    if raw.startswith("plughw:CARD="):
        # dsnoop allows shared capture so wake listener can coexist with other mic users.
        candidates.append("dsnoop:" + raw[len("plughw:") :])
    uniq: list[str] = []
    for name in candidates:
        if name and name not in uniq:
            uniq.append(name)
    return uniq


def _open_alsa_with_fallback(device_name: str) -> tuple[sherpa_onnx.Alsa | None, str, str]:
    errors: list[str] = []
    for candidate in _candidate_capture_devices(device_name):
        try:
            return sherpa_onnx.Alsa(candidate), candidate, ""
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            continue
    return None, "", "; ".join(errors)


def _pick_file(model_dir: Path, patterns: list[str], preferred_substr: str | None = None) -> Path:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(sorted(model_dir.glob(pattern)))
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in matches:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    if preferred_substr:
        for p in uniq:
            if preferred_substr in p.name:
                return p
    if not uniq:
        raise FileNotFoundError(f"missing model file in {model_dir} for patterns={patterns}")
    return uniq[0]


def _create_recognizer(model_dir: Path) -> sherpa_onnx.OnlineRecognizer:
    tokens = _pick_file(model_dir, ["tokens.txt", "*tokens*.txt"])
    encoder = _pick_file(model_dir, ["encoder*.onnx", "*encoder*.onnx"], preferred_substr=".int8.")
    decoder = _pick_file(model_dir, ["decoder*.onnx", "*decoder*.onnx"], preferred_substr=".int8.")
    joiner = _pick_file(model_dir, ["joiner*.onnx", "*joiner*.onnx"], preferred_substr=".int8.")
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(tokens),
        encoder=str(encoder),
        decoder=str(decoder),
        joiner=str(joiner),
        num_threads=int(os.environ.get("BOOSTER_SHERPA_NUM_THREADS", "1")),
        sample_rate=16000,
        feature_dim=80,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=float(os.environ.get("BOOSTER_SHERPA_RULE1_SILENCE", "2.4")),
        rule2_min_trailing_silence=float(os.environ.get("BOOSTER_SHERPA_RULE2_SILENCE", "0.8")),
        rule3_min_utterance_length=float(os.environ.get("BOOSTER_SHERPA_RULE3_UTTERANCE", "300")),
        decoding_method=os.environ.get("BOOSTER_SHERPA_DECODING_METHOD", "greedy_search"),
        provider=os.environ.get("BOOSTER_SHERPA_PROVIDER", "cpu"),
    )


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _matches_wake(text: str, aliases: list[str]) -> bool:
    t = f" {_norm(text)} "
    for alias in aliases:
        a = _norm(alias)
        if not a:
            continue
        if f" {a} " in t:
            return True
        if a in t:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--model-dir",
        default=os.environ.get(
            "BOOSTER_SHERPA_ASR_MODEL_DIR",
            "/home/booster/sherpa-onnx-models/sherpa-onnx-streaming-zipformer-en-2023-06-26",
        ),
        help="Directory containing tokens/encoder/decoder/joiner files",
    )
    parser.add_argument(
        "--device-name",
        default=os.environ.get("BOOSTER_SHERPA_DEVICE_NAME", "plughw:CARD=Device,DEV=0"),
        help="ALSA capture device name",
    )
    parser.add_argument(
        "--wake-word",
        default=os.environ.get("BOOSTER_CONVERSATION_WAKE_WORD", "hal"),
        help="Primary wake word",
    )
    parser.add_argument(
        "--wake-aliases",
        default=os.environ.get(
            "BOOSTER_SHERPA_WAKE_ALIASES",
            "hal,hell,hall,howl,charlie,charley,charly,char lee,charli",
        ),
        help="Comma-separated aliases for wake matching",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ.get("BOOSTER_SHERPA_WAKE_MAX_SECONDS", "1800")),
        help="Maximum wait time",
    )
    args = parser.parse_args()
    debug = os.environ.get("BOOSTER_SHERPA_WAKE_DEBUG", "0").strip() in ("1", "true", "True")

    model_dir = Path(args.model_dir)
    if not model_dir.is_dir():
        print(f"model dir not found: {model_dir}", file=sys.stderr)
        return 2

    aliases = [args.wake_word] + [x.strip() for x in args.wake_aliases.split(",") if x.strip()]
    aliases = [a for i, a in enumerate(aliases) if a not in aliases[:i]]

    try:
        recognizer = _create_recognizer(model_dir)
    except Exception as exc:
        print(f"failed to create recognizer: {exc}", file=sys.stderr)
        return 2

    alsa, opened_device, open_err = _open_alsa_with_fallback(args.device_name)
    if alsa is None:
        print(f"failed to open ALSA device '{args.device_name}': {open_err}", file=sys.stderr)
        return 2
    if opened_device != args.device_name:
        print(f"wake using ALSA fallback device: {opened_device}", file=sys.stderr, flush=True)

    stream = recognizer.create_stream()
    sample_rate = 16000
    samples_per_read = int(0.1 * sample_rate)
    deadline = time.monotonic() + max(1.0, args.max_seconds)
    last_partial = ""

    while time.monotonic() < deadline:
        samples = alsa.read(samples_per_read)
        stream.accept_waveform(sample_rate, samples)
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        result = recognizer.get_result(stream).strip()
        if debug and result and result != last_partial:
            print(f"__PARTIAL__:{result}", file=sys.stderr, flush=True)
            last_partial = result
        if result and _matches_wake(result, aliases):
            print(f"__WAKE__:{result}", flush=True)
            return 0
        if recognizer.is_endpoint(stream):
            recognizer.reset(stream)

    print("wake timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
