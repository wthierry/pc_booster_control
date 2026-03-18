#!/usr/bin/env python3
"""Simple ChatGPT CLI using the OpenAI Responses API.

Usage:
  # Option A: .env in project root (supports OPENAI_API_KEY, CHATGPT_API_KEY, CHAT_GPT_API, API_KEY)
  # Option B: export one of those keys in shell
  export CHAT_GPT_API=...
  python3 scripts/chatgpt_cli.py "Hello"
  python3 scripts/chatgpt_cli.py --chat
  python3 scripts/chatgpt_cli.py --chat "Start with this prompt"
  python3 scripts/chatgpt_cli.py --system "You are Rook, a witty robot assistant."
  python3 scripts/chatgpt_cli.py
"""

import argparse
import json
import os
import ssl
import sys
from urllib import error, request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "pc_booster_control"))

from pc_booster_control.memory_store import append_history_turn, build_prompt_with_context, capture_implicit_memory, maybe_handle_memory_command


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4.1-mini"
API_KEY_NAMES = ("OPENAI_API_KEY", "CHATGPT_API_KEY", "CHAT_GPT_API", "API_KEY")
DEFAULT_SYSTEM_PROMPT = (
    "You are Rook, a practical robotics assistant for Wesley. "
    "Keep responses concise, actionable, and technically accurate. "
    "Use light humor sparingly."
)


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
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
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        return


def resolve_api_key() -> str:
    for name in API_KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def resolve_system_prompt() -> str:
    prompt_file = os.environ.get("CHATGPT_SYSTEM_PROMPT_FILE", "").strip()
    if prompt_file:
        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = Path(__file__).resolve().parents[1] / prompt_path
        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            pass
    inline_prompt = os.environ.get("CHATGPT_SYSTEM_PROMPT", "").strip()
    return inline_prompt or DEFAULT_SYSTEM_PROMPT


def call_openai(api_key: str, model: str, prompt: str, system_prompt: str) -> str:
    payload = {
        "model": model,
        "input": prompt,
        "instructions": system_prompt,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        API_URL,
        data=data,
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
        with request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {msg}") from exc
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(str(exc)) from exc

    parsed = json.loads(body)
    text = parsed.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    # Fallback parser for older/alternate response shapes.
    out = parsed.get("output", [])
    chunks: list[str] = []
    if isinstance(out, list):
        for item in out:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    t = part.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
    joined = "".join(chunks).strip()
    if joined:
        return joined
    return "(No text in response)"


def main() -> int:
    load_env_file()
    parser = argparse.ArgumentParser(description="ChatGPT CLI")
    parser.add_argument("prompt", nargs="*", help="Prompt text. If omitted, enters interactive mode.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--system",
        default=resolve_system_prompt(),
        help="System persona/instructions prompt for the assistant.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Force interactive chat mode in terminal. Optional prompt becomes first message.",
    )
    args = parser.parse_args()

    api_key = resolve_api_key()
    if not api_key:
        print("API key not found. Set OPENAI_API_KEY (or CHATGPT_API_KEY/API_KEY) in .env or env.", file=sys.stderr)
        return 1

    if args.prompt and not args.chat:
        prompt = " ".join(args.prompt).strip()
        if not prompt:
            print("Prompt is empty", file=sys.stderr)
            return 1
        try:
            memory_reply = maybe_handle_memory_command(prompt)
            if memory_reply:
                print(memory_reply)
                append_history_turn(prompt, memory_reply, llm_backend="openai", llm_model=args.model)
                return 0
            capture_implicit_memory(prompt)
            assistant_text = call_openai(
                api_key,
                args.model,
                build_prompt_with_context(prompt, llm_backend="openai", llm_model=args.model),
                args.system,
            )
            print(assistant_text)
            append_history_turn(prompt, assistant_text, llm_backend="openai", llm_model=args.model)
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    print("Interactive mode. Type 'exit' to quit.")
    if args.prompt and args.chat:
        initial = " ".join(args.prompt).strip()
        if initial:
            try:
                print(f"> {initial}")
                memory_reply = maybe_handle_memory_command(initial)
                if memory_reply:
                    print(memory_reply)
                    append_history_turn(initial, memory_reply, llm_backend="openai", llm_model=args.model)
                else:
                    capture_implicit_memory(initial)
                    assistant_text = call_openai(
                        api_key,
                        args.model,
                        build_prompt_with_context(initial, llm_backend="openai", llm_model=args.model),
                        args.system,
                    )
                    print(assistant_text)
                    append_history_turn(initial, assistant_text, llm_backend="openai", llm_model=args.model)
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            break
        try:
            memory_reply = maybe_handle_memory_command(line)
            if memory_reply:
                print(memory_reply)
                append_history_turn(line, memory_reply, llm_backend="openai", llm_model=args.model)
                continue
            capture_implicit_memory(line)
            assistant_text = call_openai(
                api_key,
                args.model,
                build_prompt_with_context(line, llm_backend="openai", llm_model=args.model),
                args.system,
            )
            print(assistant_text)
            append_history_turn(line, assistant_text, llm_backend="openai", llm_model=args.model)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
