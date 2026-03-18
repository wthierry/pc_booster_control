#!/usr/bin/env python3
"""Capture one utterance on macOS and print transcript as __STT__:<text>."""

import argparse
import os
import queue
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx


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
        num_threads=int(os.environ.get("BOOSTER_SHERPA_NUM_THREADS", "2")),
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
        default=os.environ.get("BOOSTER_SHERPA_ASR_MODEL_DIR", ""),
        help="Directory containing tokens/encoder/decoder/joiner files",
    )
    parser.add_argument(
        "--device-name",
        default=os.environ.get("BOOSTER_SHERPA_DEVICE_NAME", ""),
        help="Input device name/id for sounddevice (optional)",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ.get("BOOSTER_SHERPA_STT_MAX_SECONDS", "15")),
        help="Maximum time to wait for a non-empty endpoint transcript",
    )
    parser.add_argument(
        "--stdin-pcm",
        action="store_true",
        help="Read mono S16_LE PCM from stdin instead of capturing from sounddevice",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Sample rate for stdin PCM input",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not args.model_dir or not model_dir.is_dir():
        print(f"model dir not found: {model_dir}", file=sys.stderr)
        return 2

    try:
        recognizer = _create_recognizer(model_dir)
    except Exception as exc:
        print(f"failed to create recognizer: {exc}", file=sys.stderr)
        return 2

    stream = recognizer.create_stream()
    sample_rate = int(args.sample_rate) if args.stdin_pcm else 16000

    if args.stdin_pcm:
        deadline = time.monotonic() + max(0.5, args.max_seconds)
        try:
            while time.monotonic() < deadline:
                chunk = sys.stdin.buffer.read(4096)
                if not chunk:
                    break
                nbytes = (len(chunk) // 2) * 2
                if nbytes <= 0:
                    continue
                samples = np.frombuffer(chunk[:nbytes], dtype="<i2").astype(np.float32) / 32768.0
                if samples.size == 0:
                    continue
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
            final_result = recognizer.get_result(stream).strip()
            if final_result:
                print(f"__STT__:{final_result}", flush=True)
                return 0
        except Exception as exc:
            print(f"failed to read stdin audio: {exc}", file=sys.stderr)
            return 2
        print("no speech recognized before timeout", file=sys.stderr)
        return 1

    try:
        import sounddevice as sd
    except Exception:
        print("sounddevice is not installed. Install with: pip install sounddevice", file=sys.stderr)
        return 2

    q: queue.Queue[np.ndarray] = queue.Queue(maxsize=32)

    def _cb(indata, frames, _time_info, status):  # type: ignore[no-untyped-def]
        if status:
            # Keep stderr readable but non-fatal.
            print(f"audio status: {status}", file=sys.stderr)
        try:
            q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    device = args.device_name.strip() or None
    deadline = time.monotonic() + max(0.5, args.max_seconds)
    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=_cb,
            blocksize=int(0.1 * sample_rate),
            device=device,
        ):
            while time.monotonic() < deadline:
                try:
                    samples = q.get(timeout=0.25)
                except queue.Empty:
                    continue
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
    except Exception as exc:
        print(f"failed to capture audio: {exc}", file=sys.stderr)
        return 2

    print("no speech recognized before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
