from __future__ import annotations

import base64
import os
from pathlib import Path

from ..config import settings

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

PROFILE_TEXT_KEY = "USER_PROFILE_TEXT_B64"
LIBRARY_SUMMARY_TEXT_KEY = "USER_LIBRARY_SUMMARY_B64"

MAX_PROFILE_TEXT_CHARS = 20000


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    return key.strip(), value


def clean_single_line(value: str) -> str:
    return value.replace("\r", "").replace("\n", "").strip()


def read_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}

    env_map: dict[str, str] = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            env_map[key] = value
    return env_map


def update_env_file(changes: dict[str, str | None]) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    handled: set[str] = set()
    output_lines: list[str] = []

    for line in lines:
        parsed = parse_env_line(line)
        if parsed is None:
            output_lines.append(line)
            continue

        key, _ = parsed
        if key not in changes:
            output_lines.append(line)
            continue

        handled.add(key)
        new_value = changes[key]
        if new_value is None:
            continue
        output_lines.append(f"{key}={new_value}\n")

    for key, value in changes.items():
        if key in handled or value is None:
            continue
        output_lines.append(f"{key}={value}\n")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(output_lines)


def apply_runtime_values(changes: dict[str, str | None]) -> None:
    for key, value in changes.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    if "LLM_BASE_URL" in changes and changes["LLM_BASE_URL"] is not None:
        settings.llm_base_url = changes["LLM_BASE_URL"]
    if "LLM_MODEL" in changes and changes["LLM_MODEL"] is not None:
        settings.llm_model = changes["LLM_MODEL"]
    if "LLM_API_KEY" in changes:
        settings.llm_api_key = (changes["LLM_API_KEY"] or "").strip()


def encode_text_to_b64(value: str, max_chars: int = MAX_PROFILE_TEXT_CHARS) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars]
    return base64.b64encode(normalized.encode("utf-8")).decode("ascii")


def decode_text_from_b64(value: str) -> str:
    if not value:
        return ""
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
        return decoded.decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def read_profile_state() -> dict[str, str | bool]:
    env_map = read_env_map()

    raw_profile = env_map.get(PROFILE_TEXT_KEY, os.getenv(PROFILE_TEXT_KEY, ""))
    raw_library_summary = env_map.get(LIBRARY_SUMMARY_TEXT_KEY, os.getenv(LIBRARY_SUMMARY_TEXT_KEY, ""))

    profile_text = decode_text_from_b64(raw_profile)
    library_summary_text = decode_text_from_b64(raw_library_summary)

    return {
        "profile_text": profile_text,
        "library_summary_text": library_summary_text,
        "has_profile": bool(profile_text.strip()),
        "has_library_summary": bool(library_summary_text.strip()),
    }
