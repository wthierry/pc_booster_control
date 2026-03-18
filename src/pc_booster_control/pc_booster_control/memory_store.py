from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_path(env_name: str, default_relpath: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = _project_root() / path
        return path
    return _project_root() / default_relpath


def _memory_file() -> Path:
    return _resolve_path("CHATGPT_MEMORY_FILE", "data/chatgpt_memory.json")


def _sanitize_scope_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", (value or "").strip().lower()).strip("._-")
    return cleaned or fallback


def _history_scope_key(llm_backend: str | None = None, llm_model: str | None = None) -> str:
    backend = _sanitize_scope_part(llm_backend or "default", "default")
    model = _sanitize_scope_part(llm_model or "default", "default")
    return f"{backend}__{model}"


def _history_file(llm_backend: str | None = None, llm_model: str | None = None) -> Path:
    base = _resolve_path("CHATGPT_HISTORY_FILE", "data/chatgpt_history.json")
    scope = _history_scope_key(llm_backend=llm_backend, llm_model=llm_model)
    return base.with_name(f"{base.stem}__{scope}{base.suffix}")


def _saved_memory_enabled() -> bool:
    return os.environ.get("CHATGPT_SAVED_MEMORY_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def _history_enabled() -> bool:
    return os.environ.get("CHATGPT_REFERENCE_CHAT_HISTORY_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def _max_history_items() -> int:
    raw = os.environ.get("CHATGPT_HISTORY_MAX_ITEMS", "12").strip()
    try:
        value = int(raw)
    except Exception:
        value = 12
    return max(2, min(40, value))


def _truncate_text(text: str, limit: int = 280) -> str:
    value = " ".join((text or "").split()).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _normalize_memory_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    profile = data.get("profile")
    facts = data.get("facts")
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(facts, list):
        facts = []
    normalized_facts: list[dict[str, Any]] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        normalized_facts.append(
            {
                "text": text,
                "created_at": float(item.get("created_at", time.time())),
                "updated_at": float(item.get("updated_at", time.time())),
            }
        )
    name = str(profile.get("name", "")).strip()
    return {
        "profile": {"name": name} if name else {},
        "facts": normalized_facts,
        "updated_at": float(data.get("updated_at", time.time())),
    }


def _normalize_history_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        text = str(item.get("text", "")).strip()
        if role not in ("user", "assistant") or not text:
            continue
        normalized_items.append(
            {
                "role": role,
                "text": text,
                "ts": float(item.get("ts", time.time())),
            }
        )
    max_items = _max_history_items() * 2
    return {"items": normalized_items[-max_items:], "updated_at": float(data.get("updated_at", time.time()))}


def load_saved_memory() -> dict[str, Any]:
    with _LOCK:
        return _normalize_memory_payload(_load_json(_memory_file(), {}))


def load_history(llm_backend: str | None = None, llm_model: str | None = None) -> dict[str, Any]:
    with _LOCK:
        return _normalize_history_payload(_load_json(_history_file(llm_backend=llm_backend, llm_model=llm_model), {}))


def _save_saved_memory(payload: dict[str, Any]) -> None:
    payload["updated_at"] = time.time()
    _write_json(_memory_file(), payload)


def _save_history(payload: dict[str, Any], llm_backend: str | None = None, llm_model: str | None = None) -> None:
    payload["updated_at"] = time.time()
    _write_json(_history_file(llm_backend=llm_backend, llm_model=llm_model), payload)


def get_memory_lines() -> list[str]:
    payload = load_saved_memory()
    lines: list[str] = []
    name = str(payload.get("profile", {}).get("name", "")).strip()
    if name:
        lines.append(f"The user's name is {name}.")
    for item in payload.get("facts", []):
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(text)
    return lines


def append_history_turn(
    user_text: str,
    assistant_text: str,
    llm_backend: str | None = None,
    llm_model: str | None = None,
) -> None:
    if not _history_enabled():
        return
    user_value = _truncate_text(user_text)
    assistant_value = _truncate_text(assistant_text)
    if not user_value or not assistant_value:
        return
    with _LOCK:
        payload = _normalize_history_payload(
            _load_json(_history_file(llm_backend=llm_backend, llm_model=llm_model), {})
        )
        payload["items"].append({"role": "user", "text": user_value, "ts": time.time()})
        payload["items"].append({"role": "assistant", "text": assistant_value, "ts": time.time()})
        payload = _normalize_history_payload(payload)
        _save_history(payload, llm_backend=llm_backend, llm_model=llm_model)


def build_prompt_with_context(
    user_text: str,
    llm_backend: str | None = None,
    llm_model: str | None = None,
) -> str:
    sections: list[str] = []
    if _saved_memory_enabled():
        memory_lines = get_memory_lines()
        if memory_lines:
            sections.append("Saved memory about the user:\n" + "\n".join(f"- {line}" for line in memory_lines))
    if _history_enabled():
        history_payload = load_history(llm_backend=llm_backend, llm_model=llm_model)
        items = history_payload.get("items", [])
        if items:
            history_lines = [f"{item['role'].capitalize()}: {_truncate_text(str(item['text']), 220)}" for item in items[-_max_history_items() :]]
            sections.append("Recent chat history:\n" + "\n".join(history_lines))
    if not sections:
        return user_text
    sections.append(f"Current user message:\n{user_text}")
    return "\n\n".join(sections)


def build_chat_messages_with_context(
    user_text: str,
    llm_backend: str | None = None,
    llm_model: str | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if _saved_memory_enabled():
        memory_lines = get_memory_lines()
        if memory_lines:
            messages.append(
                {
                    "role": "system",
                    "content": "Saved memory about the user:\n" + "\n".join(f"- {line}" for line in memory_lines),
                }
            )
    if _history_enabled():
        history_payload = load_history(llm_backend=llm_backend, llm_model=llm_model)
        for item in history_payload.get("items", [])[-_max_history_items() :]:
            role = str(item.get("role", "")).strip().lower()
            if role not in ("user", "assistant"):
                continue
            text = _truncate_text(str(item.get("text", "")), 220)
            if not text:
                continue
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_text})
    return messages


def _set_name(name: str) -> None:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        return
    with _LOCK:
        payload = _normalize_memory_payload(_load_json(_memory_file(), {}))
        payload["profile"]["name"] = cleaned
        _save_saved_memory(payload)


def _add_fact(text: str) -> None:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return
    with _LOCK:
        payload = _normalize_memory_payload(_load_json(_memory_file(), {}))
        facts = payload["facts"]
        lowered = cleaned.lower()
        now = time.time()
        for item in facts:
            if str(item.get("text", "")).strip().lower() == lowered:
                item["text"] = cleaned
                item["updated_at"] = now
                _save_saved_memory(payload)
                return
        facts.append({"text": cleaned, "created_at": now, "updated_at": now})
        payload["facts"] = facts[-50:]
        _save_saved_memory(payload)


def _clear_name() -> bool:
    with _LOCK:
        payload = _normalize_memory_payload(_load_json(_memory_file(), {}))
        if not payload["profile"].get("name"):
            return False
        payload["profile"].pop("name", None)
        _save_saved_memory(payload)
        return True


def _remove_fact_matches(phrase: str) -> int:
    needle = " ".join((phrase or "").split()).strip().lower()
    if not needle:
        return 0
    with _LOCK:
        payload = _normalize_memory_payload(_load_json(_memory_file(), {}))
        before = len(payload["facts"])
        payload["facts"] = [item for item in payload["facts"] if needle not in str(item.get("text", "")).strip().lower()]
        removed = before - len(payload["facts"])
        if removed:
            _save_saved_memory(payload)
        return removed


def describe_saved_memory() -> str:
    lines = get_memory_lines()
    if not lines:
        return "I don't have any saved memories yet."
    return "Here's what I remember:\n" + "\n".join(f"- {line}" for line in lines)


def maybe_handle_memory_command(user_text: str) -> str | None:
    text = " ".join((user_text or "").split()).strip()
    if not text:
        return None
    low = text.lower()
    normalized = re.sub(r"[?.!]+$", "", low).strip()
    if re.fullmatch(r"(what do you remember( about me)?|what do you know about me|show (me )?my memories|list (my )?memories)", normalized):
        return describe_saved_memory()
    name_match = re.fullmatch(r"(forget|delete|remove) my name", normalized)
    if name_match:
        if _clear_name():
            return "Okay. I forgot your name."
        return "I didn't have your name saved."
    forget_match = re.fullmatch(r"(forget|delete|remove)( that)? (?P<fact>.+)", normalized)
    if forget_match:
        removed = _remove_fact_matches(forget_match.group("fact"))
        if removed:
            return f"Okay. I forgot {removed} saved memory item{'s' if removed != 1 else ''}."
        return "I couldn't find a saved memory matching that."
    remember_match = re.fullmatch(r"remember( that)? (?P<fact>.+)", text, flags=re.IGNORECASE)
    if remember_match:
        fact = remember_match.group("fact").strip().rstrip(".")
        if fact.lower().startswith("my name is "):
            _set_name(fact[11:].strip())
            return f"Okay. I'll remember that your name is {fact[11:].strip()}."
        _add_fact(fact)
        return "Okay. I'll remember that."
    return None


def capture_implicit_memory(user_text: str) -> list[str]:
    if not _saved_memory_enabled():
        return []
    text = " ".join((user_text or "").split()).strip()
    if not text:
        return []
    updates: list[str] = []
    name_patterns = [
        r"\bmy name is (?P<name>[A-Za-z][A-Za-z0-9' -]{0,60})",
        r"\bi am (?P<name>[A-Z][A-Za-z0-9' -]{0,60})\b",
        r"\bi'm (?P<name>[A-Z][A-Za-z0-9' -]{0,60})\b",
        r"\bcall me (?P<name>[A-Za-z][A-Za-z0-9' -]{0,60})",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group("name").strip(" .,!?:;")
        if len(name.split()) <= 4:
            _set_name(name)
            updates.append(f"name={name}")
            break
    return updates
