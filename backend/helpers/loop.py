"""`run_turn`: the bounded agent loop behind POST /chat."""

from __future__ import annotations

import time
from typing import Any

from backend.chat_schema import ChatMessage, ChatRequest, ChatResponse
from backend.helpers import config
from backend.helpers.catalog import READ, effective_class, get_index_text
from backend.helpers.executor import LOAD_MORE_TOOLS_SCHEMA, TurnState, run_tool
from backend.helpers.llm import ProviderError, call_model
from backend.helpers.prompts import LIMIT_SUMMARY_PROMPT, agent_instructions
from backend.helpers.router import select_tools

_LIMIT_LABELS = {
    "max_turns": "the step limit",
    "time_budget": "the time limit",
    "provider_error": "a model provider error",
}

# Below this much time left, a limit stop skips the model-written summary.
LIMIT_SUMMARY_MIN_SECONDS = 5

# Module-level alias so tests can patch the clock.
_now = time.monotonic


def run_turn(request: ChatRequest) -> ChatResponse:
    # Imported here because backend.main imports backend.solution at module load.
    from backend.main import get_openai_tools

    state = TurnState(
        conversation_text="\n".join(
            message.content
            for message in request.messages
            if message.role in ("user", "assistant")
        ),
        last_user_text=next(
            (m.content for m in reversed(request.messages) if m.role == "user"), ""
        ),
        deadline=_now() + config.CHAT_TIME_BUDGET_S,
    )
    model_input = [_input_message(message) for message in request.messages]
    state.active_tools = select_tools(model_input, lambda: state.deadline - _now())
    instructions = agent_instructions(get_index_text())
    reply = ""

    while True:
        if state.turn >= config.CHAT_MAX_TURNS:
            state.stop_reason = "max_turns"
            break
        remaining = state.deadline - _now()
        if remaining <= 0:
            state.stop_reason = "time_budget"
            break
        state.turn += 1

        try:
            response = call_model(
                model=config.OPENAI_MODEL,
                instructions=instructions,
                input=model_input,
                tools=_tool_schemas(state.active_tools, get_openai_tools),
                timeout=min(config.MODEL_CALL_TIMEOUT_S, remaining),
            )
        except ProviderError:
            if not state.tool_calls:
                raise
            state.stop_reason = "provider_error"
            break

        calls = [
            item
            for item in (getattr(response, "output", None) or [])
            if getattr(item, "type", None) == "function_call"
        ]
        if not calls:
            reply = (getattr(response, "output_text", "") or "").strip()
            state.stop_reason = "final"
            break

        # Calls in one batch run sequentially, in the order the model gave them.
        for call in calls:
            outcome = run_tool(call.name, call.arguments, state)
            model_input.append(
                {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            )
            model_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": outcome.model_view,
                }
            )

    if state.stop_reason in ("max_turns", "time_budget"):
        reply = _limit_summary(state, model_input) or _log_summary(state)
    elif state.stop_reason == "provider_error":
        reply = _log_summary(state)
    elif not reply:
        reply = "I could not produce a reply for this request."

    prefix = _final_answer_prefix(state)
    if prefix:
        reply = f"{prefix}\n\n{reply}"

    return ChatResponse(
        messages=[*request.messages, ChatMessage(role="assistant", content=reply)],
        tool_calls=state.tool_calls,
    )


def _tool_schemas(active_tools: list[str], get_openai_tools: Any) -> list[dict[str, Any]]:
    # get_openai_tools([]) returns all 191 schemas, so an empty selection must
    # never reach it.
    routed = get_openai_tools(active_tools) if active_tools else []
    return [*routed, LOAD_MORE_TOOLS_SCHEMA]


def _input_message(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        # The Responses API has no bare tool role; pass it as labelled data.
        return {
            "role": "user",
            "content": f'<tool_message trust="data">{message.content}</tool_message>',
        }
    return {"role": message.role, "content": message.content}


def _limit_summary(state: TurnState, model_input: list[dict[str, Any]]) -> str:
    """One last model call, with no tools, to say what was and was not done.

    Returns "" when there is too little time left or the call fails; the
    caller then falls back to the summary built from the log.
    """
    remaining = state.deadline - _now()
    if remaining < LIMIT_SUMMARY_MIN_SECONDS:
        return ""
    try:
        response = call_model(
            model=config.OPENAI_MODEL,
            instructions=LIMIT_SUMMARY_PROMPT,
            input=model_input,
            tools=[],
            timeout=min(config.MODEL_CALL_TIMEOUT_S, remaining),
        )
    except ProviderError:
        return ""
    return (getattr(response, "output_text", "") or "").strip()


def _log_summary(state: TurnState) -> str:
    """Fixed account of a turn that did not finish, built only from the log."""
    succeeded = [call.name for call in state.tool_calls if call.error is None]
    failed = [call.name for call in state.tool_calls if call.error is not None]
    parts = []
    if succeeded:
        parts.append(f"Tool calls that completed: {', '.join(succeeded)}.")
    if failed:
        parts.append(f"Tool calls that failed: {', '.join(failed)}.")
    if not state.tool_calls:
        parts.append("No tool calls were made.")
    return " ".join(parts)


def _final_answer_prefix(state: TurnState) -> str:
    """A fixed statement of what did not complete, taken from the log, not the model.

    It is added when the turn hit a limit, or when a write failed and no later
    call to the same tool succeeded. Empty when neither applies.
    """
    unfinished: list[str] = []
    for index, call in enumerate(state.tool_calls):
        if call.error is None or call.name in unfinished:
            continue
        if effective_class(call.name, call.arguments) == READ:
            continue
        succeeded_later = any(
            later.name == call.name and later.error is None
            for later in state.tool_calls[index + 1 :]
        )
        if not succeeded_later:
            unfinished.append(call.name)

    parts = []
    if state.stop_reason != "final":
        reason = _LIMIT_LABELS.get(state.stop_reason or "", "a limit")
        parts.append(
            f"I stopped before finishing this request because I reached {reason}. "
            "The task may be incomplete."
        )
    if unfinished:
        parts.append(f"These actions did not complete: {', '.join(unfinished)}.")
    return " ".join(parts)
