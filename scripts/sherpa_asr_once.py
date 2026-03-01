#!/usr/bin/env python3
"""Capture one utterance from ALSA mic and print transcript (last line)."""

import argparse
import os
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
        rule2_min_trailing_silence=float(os.environ.get("BOOSTER_SHERPA_RULE2_SILENCE", "1.1")),
        rule3_min_utterance_length=float(os.environ.get("BOOSTER_SHERPA_RULE3_UTTERANCE", "300")),
        decoding_method=os.environ.get("BOOSTER_SHERPA_DECODING_METHOD", "greedy_search"),
        provider=os.environ.get("BOOSTER_SHERPA_PROVIDER", "cpu"),
    )


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
        "--max-seconds",
        type=float,
        default=float(os.environ.get("BOOSTER_SHERPA_STT_MAX_SECONDS", "15")),
        help="Maximum time to wait for a non-empty endpoint transcript",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not model_dir.is_dir():
        print(f"model dir not found: {model_dir}", file=sys.stderr)
        return 2

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
        print(f"stt using ALSA fallback device: {opened_device}", file=sys.stderr, flush=True)

    stream = recognizer.create_stream()
    sample_rate = 16000
    samples_per_read = int(0.1 * sample_rate)
    deadline = time.monotonic() + max(0.5, args.max_seconds)

    while time.monotonic() < deadline:
        samples = alsa.read(samples_per_read)
        stream.accept_waveform(sample_rate, samples)
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        if not recognizer.is_endpoint(stream):
            continue
        result = recognizer.get_result(stream).strip()
        recognizer.reset(stream)
        if result:
            print(f"__STT__:{result}", flush=True)
            return 0

    print("no speech recognized before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
