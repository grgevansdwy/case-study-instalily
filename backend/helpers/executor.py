"""`run_tool`: the single path from the model to a registered tool."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

from backend.chat_schema import ToolCallLog
from backend.helpers import catalog, config
from pydantic import ValidationError

MODEL_VIEW_MAX_CHARS = 12_000
MODEL_VIEW_MAX_LIST_ITEMS = 20
MODEL_VIEW_MAX_STRING_CHARS = 2_000
ERROR_DETAIL_MAX_CHARS = 500

# An identical call (same tool, same arguments) may be invoked this many times.
MAX_IDENTICAL_CALLS = 2

# Result strings up to this length are split into tokens for grounding. Longer
# text (a message body, a file) is prose, and an address or ID that appears
# only inside it does not become a valid target for a write.
GROUNDING_MAX_STRING_CHARS = 300
_GROUNDING_SPLIT = re.compile(r"[\s<>(),;:\"'/\[\]]+")

# Result keys that carry no task information, dropped from the model's view.
_NOISE_KEYS = frozenset({"etag", "kind", "iconLink", "webViewLink", "historyId"})

LOAD_MORE_TOOLS = "load_more_tools"

# A meta-tool, not a registered tool: it changes which schemas the model sees
# and is never written to `tool_calls`.
LOAD_MORE_TOOLS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "name": LOAD_MORE_TOOLS,
    "description": (
        "Load more tools by exact name from the tool index so you can call them "
        "on your next step. Use it when the task needs a tool that is not loaded."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exact tool names from the tool index.",
            }
        },
        "required": ["names"],
        "additionalProperties": False,
    },
    "strict": True,
}


@dataclass
class TurnState:
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    grounded: set[str] = field(default_factory=set)
    conversation_text: str = ""
    last_user_text: str = ""
    call_counts: dict[str, int] = field(default_factory=dict)
    turn: int = 0
    deadline: float = 0.0
    stop_reason: str | None = None


@dataclass
class ToolOutcome:
    ok: bool
    model_view: str
    error_type: str | None = None
    retryable: bool = False
    invoked: bool = False


def run_tool(name: str, raw_args: str | dict[str, Any] | None, state: TurnState) -> ToolOutcome:
    """Validate, invoke and log one tool call, and build what the model sees."""
    # Imported here because backend.main imports backend.solution at module load.
    from backend.main import get_all_tool_specs

    specs = get_all_tool_specs()
    if name == LOAD_MORE_TOOLS:
        return _load_more_tools(raw_args, state, specs)
    if name not in specs:
        return _rejected(
            "unknown_tool",
            f"'{name}' is not a registered tool. Use an exact name from the tools you were given.",
        )
    if name not in state.active_tools:
        return _rejected(
            "tool_not_loaded",
            f"'{name}' is not loaded. Call {LOAD_MORE_TOOLS} with this name first.",
            retryable=True,
        )

    try:
        args = _parse_arguments(raw_args)
    except ValueError as exc:
        return _rejected("bad_arguments", str(exc), retryable=True)

    # Strict mode makes the model send null for every unused argument; dropping
    # them lets the tool's own default apply and keeps the log to what was passed.
    args = {key: value for key, value in args.items() if value is not None}

    call_key = f"{name} {json.dumps(args, sort_keys=True, default=str)}"
    if state.call_counts.get(call_key, 0) >= MAX_IDENTICAL_CALLS:
        return _rejected(
            "repeated_call",
            f"This exact call already ran {MAX_IDENTICAL_CALLS} times. Use its earlier "
            "result, change the arguments, or stop and tell the user what happened.",
        )

    tool_class = catalog.effective_class(name, args)
    if tool_class != catalog.READ:
        blocked = _semantic_error(name, args, state)
        if blocked:
            return _rejected(*blocked)

    # A read that fails unexpectedly is retried once here; a write is not,
    # because it may have landed.
    attempts = 2 if tool_class == catalog.READ else 1
    for attempt in range(1, attempts + 1):
        state.call_counts[call_key] = state.call_counts.get(call_key, 0) + 1
        try:
            result = specs[name].invoke(**args).model_dump(mode="json")["result"]
        except ValidationError as exc:  # subclasses ValueError, so it must come first
            return _failed(state, name, args, exc, "bad_arguments", retryable=True)
        except ValueError as exc:  # each service's *MockError
            error_type = "not_found" if _looks_like_not_found(str(exc)) else "tool_error"
            return _failed(state, name, args, exc, error_type, retryable=False)
        except Exception as exc:
            if attempt < attempts:
                _log_failure(state, name, args, exc)
                continue
            hint = (
                "A retry also failed. Tell the user this lookup did not work."
                if tool_class == catalog.READ
                else "The change may or may not have been applied. Check with a read "
                "tool before trying again, and retry only if it was not applied."
            )
            return _failed(state, name, args, exc, "unexpected_error", retryable=False, hint=hint)
        break

    state.tool_calls.append(ToolCallLog(name=name, arguments=args, result=result, error=None))
    _ground(result, state.grounded)
    return ToolOutcome(ok=True, model_view=_result_view(name, result), invoked=True)


def _semantic_error(name: str, args: dict[str, Any], state: TurnState) -> tuple[str, str] | None:
    """Checks on a write before it runs. Returns (error type, detail), or None to proceed."""
    return (
        _check_grounding(name, args, state)
        or _check_content(args)
        or _check_time_order(args)
        or _check_bulk(name, state)
    )


def _check_grounding(name: str, args: dict[str, Any], state: TurnState) -> tuple[str, str] | None:
    conversation = state.conversation_text.lower()
    for arg, value in _reference_values(name, args):
        key = _grounding_key(value)
        if key in catalog.GROUNDING_EXEMPT or key in state.grounded or key in conversation:
            continue
        return (
            "ungrounded_reference",
            f"The value {value!r} for '{arg}' did not come from the user or from a tool "
            "result in this turn. Look it up with a read tool first; if a lookup "
            "cannot settle it, ask the user. Do not guess.",
        )
    return None


def _reference_values(tool: str, args: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Every scalar held by a reference argument, including inside lists and objects."""

    def walk(arg: str, value: Any, is_reference: bool) -> Iterator[tuple[str, Any]]:
        if isinstance(value, dict):
            for key, item in value.items():
                yield from walk(key, item, catalog.is_reference_arg(tool, key))
        elif isinstance(value, list):
            for item in value:
                yield from walk(arg, item, is_reference)
        elif is_reference and isinstance(value, (str, int)) and not isinstance(value, bool):
            yield arg, value

    for arg, value in args.items():
        yield from walk(arg, value, catalog.is_reference_arg(tool, arg))


def _grounding_key(value: Any) -> str:
    # "#general" and "@jordan" are the same references as "general" and "jordan".
    return str(value).strip().lstrip("#@").lower()


def _ground(result: Any, grounded: set[str]) -> None:
    """Record the values in a tool result that a later write may refer to."""
    if isinstance(result, dict):
        for item in result.values():
            _ground(item, grounded)
    elif isinstance(result, list):
        for item in result:
            _ground(item, grounded)
    elif isinstance(result, bool):
        return
    elif isinstance(result, int):
        grounded.add(str(result))
    elif isinstance(result, str) and len(result) <= GROUNDING_MAX_STRING_CHARS:
        grounded.add(_grounding_key(result))
        # Also the parts: "Jordan <jordan@corp.com>" and "acme/api" hold references.
        grounded.update(_grounding_key(part) for part in _GROUNDING_SPLIT.split(result) if part)


def _check_content(args: dict[str, Any]) -> tuple[str, str] | None:
    for arg in catalog.CONTENT_ARG_NAMES:
        value = args.get(arg)
        if isinstance(value, str) and not value.strip():
            return (
                "empty_content",
                f"'{arg}' is blank. Provide the text, or ask the user what it should say.",
            )
    return None


def _check_time_order(args: dict[str, Any]) -> tuple[str, str] | None:
    for start_arg, end_arg in catalog.TIME_RANGE_ARGS:
        start, end = args.get(start_arg), args.get(end_arg)
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            in_order = datetime.fromisoformat(end) > datetime.fromisoformat(start)
        except (ValueError, TypeError):  # unparseable, or mixed time zone awareness
            continue  # the tool validates its own formats
        if not in_order:
            return (
                "invalid_time_range",
                f"'{end_arg}' ({end}) must be after '{start_arg}' ({start}).",
            )
    return None


def _check_bulk(name: str, state: TurnState) -> tuple[str, str] | None:
    keyword_groups = catalog.BULK_KEYWORDS.get(name)
    if not keyword_groups:
        return None
    words = set(re.findall(r"[a-z]+", state.last_user_text.lower()))
    if any(all(keyword in words for keyword in group) for group in keyword_groups):
        return None
    return (
        "bulk_not_requested",
        f"{name} affects a whole collection and the user's last message did not ask "
        "for that. Ask the user to confirm before doing it.",
    )


def _load_more_tools(
    raw_args: str | dict[str, Any] | None, state: TurnState, specs: dict[str, Any]
) -> ToolOutcome:
    try:
        names = _parse_arguments(raw_args).get("names")
    except ValueError as exc:
        return _rejected("bad_arguments", str(exc), retryable=True)
    if not isinstance(names, list):
        return _rejected("bad_arguments", "'names' must be a list of tool names.", retryable=True)

    added: list[str] = []
    rejected: list[dict[str, str]] = []
    for name in names:
        if name in state.active_tools:
            continue
        if not isinstance(name, str) or name not in specs:
            rejected.append({"name": str(name), "reason": "not a registered tool name"})
        elif len(state.active_tools) >= config.CHAT_MAX_ACTIVE_TOOLS:
            rejected.append(
                {"name": name, "reason": f"limit of {config.CHAT_MAX_ACTIVE_TOOLS} loaded tools"}
            )
        else:
            state.active_tools.append(name)
            added.append(name)
    view = json.dumps({"added": added, "rejected": rejected, "active": state.active_tools})
    return ToolOutcome(ok=not rejected, model_view=view, invoked=False)


def _parse_arguments(raw_args: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw_args is None or raw_args == "":
        return {}
    if isinstance(raw_args, dict):
        return dict(raw_args)
    try:
        parsed = json.loads(raw_args)
    except (TypeError, ValueError) as exc:
        raise ValueError("Arguments were not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Arguments must be a JSON object.")
    return parsed


def _looks_like_not_found(message: str) -> bool:
    lowered = message.lower()
    return (
        lowered.startswith("unknown")
        or "not found" in lowered
        or "does not exist" in lowered
    )


def _error_view(error_type: str, detail: str, retryable: bool) -> str:
    return json.dumps(
        {
            "error": error_type,
            "detail": detail[:ERROR_DETAIL_MAX_CHARS],
            "retryable": retryable,
        }
    )


def _rejected(error_type: str, detail: str, *, retryable: bool = False) -> ToolOutcome:
    """A call stopped before invocation: nothing ran, so nothing is logged."""
    return ToolOutcome(
        ok=False,
        model_view=_error_view(error_type, detail, retryable),
        error_type=error_type,
        retryable=retryable,
        invoked=False,
    )


def _failed(
    state: TurnState,
    name: str,
    args: dict[str, Any],
    exc: Exception,
    error_type: str,
    *,
    retryable: bool,
    hint: str = "",
) -> ToolOutcome:
    """A call that was invoked and raised: logged with the error and a null result."""
    message = _log_failure(state, name, args, exc)
    # Cut the message, not the hint, so the instruction always reaches the model.
    detail = f"{message[: ERROR_DETAIL_MAX_CHARS - len(hint)]} {hint}".strip()
    return ToolOutcome(
        ok=False,
        model_view=_error_view(error_type, detail, retryable),
        error_type=error_type,
        retryable=retryable,
        invoked=True,
    )


def _log_failure(state: TurnState, name: str, args: dict[str, Any], exc: Exception) -> str:
    message = str(exc) or type(exc).__name__
    state.tool_calls.append(ToolCallLog(name=name, arguments=args, result=None, error=message))
    return message


def _result_view(name: str, result: Any) -> str:
    """What the model reads: the result with noise removed and sizes capped.

    The log always keeps the full result; only this view is trimmed.
    """
    if result is None or result == "" or result == [] or result == {}:
        body = "No results."
    else:
        try:
            trimmed = _trim(result, decode_data=name.startswith("GMAIL_"))
        except Exception:
            trimmed = result  # the character cap below still applies
        body = json.dumps(trimmed, ensure_ascii=False, default=str)
    if len(body) > MODEL_VIEW_MAX_CHARS:
        omitted = len(body) - MODEL_VIEW_MAX_CHARS
        body = f"{body[:MODEL_VIEW_MAX_CHARS]}… [{omitted} more characters not shown]"
    return f'<tool_result name="{name}" trust="data">{body}</tool_result>'


def _trim(value: Any, *, decode_data: bool) -> Any:
    if isinstance(value, dict):
        trimmed: dict[str, Any] = {}
        for key, item in value.items():
            if key in _NOISE_KEYS or "color" in key.lower():
                continue
            if decode_data and key == "data" and isinstance(item, str):
                item = _decode_base64_text(item)
            trimmed[key] = _trim(item, decode_data=decode_data)
        return trimmed
    if isinstance(value, list):
        kept = [_trim(item, decode_data=decode_data) for item in value[:MODEL_VIEW_MAX_LIST_ITEMS]]
        if len(value) > MODEL_VIEW_MAX_LIST_ITEMS:
            omitted = len(value) - MODEL_VIEW_MAX_LIST_ITEMS
            kept.append(f"… {omitted} more not shown; narrow the query or page")
        return kept
    if isinstance(value, str) and len(value) > MODEL_VIEW_MAX_STRING_CHARS:
        omitted = len(value) - MODEL_VIEW_MAX_STRING_CHARS
        return f"{value[:MODEL_VIEW_MAX_STRING_CHARS]}… [{omitted} more characters not shown]"
    return value


def _decode_base64_text(value: str) -> str:
    """Gmail body data as text, so the model can read it; unchanged if it is not text."""
    try:
        padded = value.replace("-", "+").replace("_", "/") + "=" * (-len(value) % 4)
        return base64.b64decode(padded, validate=True).decode("utf-8")
    except ValueError:  # covers binascii.Error and UnicodeDecodeError
        return value
