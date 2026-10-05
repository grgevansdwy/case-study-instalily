"""`run_turn`: the bounded agent loop behind POST /chat."""

from __future__ import annotations

import time
from typing import Any

from backend.chat_schema import ChatMessage, ChatRequest, ChatResponse
from backend.helpers import config
from backend.helpers.executor import TurnState, run_tool
from backend.helpers.llm import ProviderError, call_model
from backend.helpers.prompts import AGENT_PROMPT

# M1 only: a fixed subset until the router (M2) selects tools per request.
FIXED_TOOLS = [
    "slack_conversations_history",
    "slack_get_full_conversation",
    "slack_get_thread",
    "slack_health_check",
    "slack_list_conversations",
    "slack_list_users",
    "slack_search_messages",
    "slack_send_message",
    "slack_token_status",
    "slack_users_info",
    "GMAIL_FETCH_EMAILS",
    "GOOGLECALENDAR_GET_CURRENT_DATE_TIME",
]

_LIMIT_LABELS = {
    "max_turns": "the step limit",
    "time_budget": "the time limit",
    "provider_error": "a model provider error",
}

# Module-level alias so tests can patch the clock.
_now = time.monotonic


def run_turn(request: ChatRequest) -> ChatResponse:
    # Imported here because backend.main imports backend.solution at module load.
    from backend.main import get_openai_tools

    state = TurnState(
        active_tools=list(FIXED_TOOLS),
        conversation_text="\n".join(
            message.content
            for message in request.messages
            if message.role in ("user", "assistant")
        ),
        deadline=_now() + config.CHAT_TIME_BUDGET_S,
    )
    model_input = [_input_message(message) for message in request.messages]
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
                instructions=AGENT_PROMPT,
                input=model_input,
                tools=get_openai_tools(state.active_tools),
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

    if state.stop_reason != "final":
        reply = _limit_message(state)
    elif not reply:
        reply = "I could not produce a reply for this request."

    return ChatResponse(
        messages=[*request.messages, ChatMessage(role="assistant", content=reply)],
        tool_calls=state.tool_calls,
    )


def _input_message(message: ChatMessage) -> dict[str, Any]:
    if message.role == "tool":
        # The Responses API has no bare tool role; pass it as labelled data.
        return {
            "role": "user",
            "content": f'<tool_message trust="data">{message.content}</tool_message>',
        }
    return {"role": message.role, "content": message.content}


def _limit_message(state: TurnState) -> str:
    """Fixed reply for a turn that did not finish, built only from the log."""
    reason = _LIMIT_LABELS.get(state.stop_reason or "", "a limit")
    succeeded = [call.name for call in state.tool_calls if call.error is None]
    failed = [call.name for call in state.tool_calls if call.error is not None]
    parts = [f"I stopped before finishing this request because I reached {reason}."]
    if succeeded:
        parts.append(f"Tool calls that completed: {', '.join(succeeded)}.")
    if failed:
        parts.append(f"Tool calls that failed: {', '.join(failed)}.")
    if not state.tool_calls:
        parts.append("No tool calls were made.")
    parts.append("The task may be incomplete.")
    return " ".join(parts)
