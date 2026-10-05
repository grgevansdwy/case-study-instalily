"""`select_tools`: one model call picks tool names from the index; code validates them."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from backend.helpers import catalog, config
from backend.helpers.llm import ProviderError, call_model
from backend.helpers.prompts import ROUTER_PROMPT

ROUTER_ATTEMPTS = 2

# Keyword fallback, used only when the router call fails twice.
_SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "slack": ("slack", "channel"),
    "gmail": ("gmail", "email", "emails", "inbox", "mail", "draft"),
    "googlecalendar": ("calendar", "meeting", "meetings", "event", "events", "schedule"),
    "googledrive": ("drive", "file", "files", "folder", "folders"),
    "linear": ("linear", "issue", "issues", "ticket", "tickets"),
    "github": (
        "github",
        "pull request",
        "pull requests",
        "pr",
        "prs",
        "repo",
        "repos",
        "repository",
        "commit",
        "commits",
        "branch",
        "issue",
        "issues",
    ),
    "perplexity": ("perplexity", "web", "online", "research"),
}


def select_tools(model_input: list[dict[str, Any]], time_left: Callable[[], float]) -> list[str]:
    """Return up to `CHAT_ROUTER_MAX_TOOLS` registered tool names for this conversation."""
    instructions = f"{ROUTER_PROMPT}\nTool index:\n{catalog.get_index_text()}"
    for _ in range(ROUTER_ATTEMPTS):
        remaining = time_left()
        if remaining <= 0:
            break
        try:
            response = call_model(
                model=config.OPENAI_ROUTER_MODEL,
                instructions=instructions,
                input=model_input,
                tools=[],
                timeout=min(config.MODEL_CALL_TIMEOUT_S, remaining),
                text=_output_format(),
            )
            names = _parse_names(getattr(response, "output_text", "") or "")
        except (ProviderError, ValueError):
            continue
        return validate_names(names)
    return keyword_fallback(_last_user_text(model_input))


def validate_names(names: list[Any]) -> list[str]:
    """Keep registered names with exact casing, drop duplicates, cap the count."""
    kept: list[str] = []
    for name in names:
        if isinstance(name, str) and catalog.get_info(name) and name not in kept:
            kept.append(name)
    return kept[: config.CHAT_ROUTER_MAX_TOOLS]


def keyword_fallback(text: str) -> list[str]:
    """Read tools of every service the text names, shared evenly up to the cap."""
    lowered = text.lower()
    per_service = [
        [
            name
            for name in catalog.names_for_service(service)
            if catalog.TOOL_CLASSES.get(name) == catalog.READ
        ]
        for service, keywords in _SERVICE_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords)
    ]
    picked: list[str] = []
    depth = 0
    while len(picked) < config.CHAT_ROUTER_MAX_TOOLS and any(
        depth < len(names) for names in per_service
    ):
        for names in per_service:
            if depth < len(names) and len(picked) < config.CHAT_ROUTER_MAX_TOOLS:
                picked.append(names[depth])
        depth += 1
    return picked


def _output_format() -> dict[str, Any]:
    # The enum makes the model return exact registered casing.
    return {
        "format": {
            "type": "json_schema",
            "name": "tool_selection",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tools"],
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {"type": "string", "enum": catalog.all_names()},
                    }
                },
            },
        }
    }


def _parse_names(output_text: str) -> list[Any]:
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tools"), list):
        raise ValueError("Router output did not match the schema.")
    return parsed["tools"]


def _last_user_text(model_input: list[dict[str, Any]]) -> str:
    for item in reversed(model_input):
        content = item.get("content")
        # Tool-role messages are sent as labelled user data; they are not the request.
        if (
            item.get("role") == "user"
            and isinstance(content, str)
            and not content.startswith("<tool_message")
        ):
            return content
    return ""
