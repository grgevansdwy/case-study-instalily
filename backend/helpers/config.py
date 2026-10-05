"""Runtime configuration: a stdlib `.env` loader plus model names and loop limits."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into the environment without overriding set variables."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


load_env_file(REPO_ROOT / ".env")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
OPENAI_ROUTER_MODEL = os.environ.get("OPENAI_ROUTER_MODEL") or "gpt-4.1-mini"
CHAT_MAX_TURNS = _int_env("CHAT_MAX_TURNS", 12)
CHAT_TIME_BUDGET_S = _int_env("CHAT_TIME_BUDGET_S", 60)

# Per model call, further limited by the time left in the turn.
MODEL_CALL_TIMEOUT_S = 30
