"""`run_tool`: the single path from the model to a registered tool."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.chat_schema import ToolCallLog
from pydantic import ValidationError

MODEL_VIEW_MAX_CHARS = 12_000
ERROR_DETAIL_MAX_CHARS = 500


@dataclass
class TurnState:
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    grounded: set[str] = field(default_factory=set)
    conversation_text: str = ""
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
    if name not in specs:
        return _rejected(
            "unknown_tool",
            f"'{name}' is not a registered tool. Use an exact name from the tools you were given.",
        )
    if name not in state.active_tools:
        return _rejected("tool_not_loaded", f"'{name}' is not available in this turn.")

    try:
        args = _parse_arguments(raw_args)
    except ValueError as exc:
        return _rejected("bad_arguments", str(exc), retryable=True)

    # Strict mode makes the model send null for every unused argument; dropping
    # them lets the tool's own default apply and keeps the log to what was passed.
    args = {key: value for key, value in args.items() if value is not None}

    try:
        result = specs[name].invoke(**args).model_dump(mode="json")["result"]
    except ValidationError as exc:  # subclasses ValueError, so it must come first
        return _failed(state, name, args, exc, "bad_arguments", retryable=True)
    except ValueError as exc:  # each service's *MockError
        error_type = "not_found" if _looks_like_not_found(str(exc)) else "tool_error"
        return _failed(state, name, args, exc, error_type, retryable=False)
    except Exception as exc:
        return _failed(state, name, args, exc, "unexpected_error", retryable=True)

    state.tool_calls.append(ToolCallLog(name=name, arguments=args, result=result, error=None))
    return ToolOutcome(ok=True, model_view=_result_view(name, result), invoked=True)


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
) -> ToolOutcome:
    """A call that was invoked and raised: logged with the error and a null result."""
    message = str(exc) or type(exc).__name__
    state.tool_calls.append(ToolCallLog(name=name, arguments=args, result=None, error=message))
    return ToolOutcome(
        ok=False,
        model_view=_error_view(error_type, message, retryable),
        error_type=error_type,
        retryable=retryable,
        invoked=True,
    )


def _result_view(name: str, result: Any) -> str:
    body = json.dumps(result, ensure_ascii=False, default=str)
    if len(body) > MODEL_VIEW_MAX_CHARS:
        omitted = len(body) - MODEL_VIEW_MAX_CHARS
        body = f"{body[:MODEL_VIEW_MAX_CHARS]}… [{omitted} more characters not shown]"
    return f'<tool_result name="{name}" trust="data">{body}</tool_result>'
