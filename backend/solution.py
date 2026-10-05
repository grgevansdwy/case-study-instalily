from __future__ import annotations

from backend.chat_schema import ChatRequest, ChatResponse
from backend.helpers.llm import ProviderError
from backend.helpers.loop import run_turn
from fastapi import HTTPException


def chat(request: ChatRequest) -> ChatResponse:
    """Run one chat turn: pick tools, run the agent loop, return the reply and log.

    The loop lives in `backend.helpers.loop.run_turn`. A provider failure before
    any tool ran is the only case that is not a 200.
    """
    try:
        return run_turn(request)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503, detail=f"Model provider unavailable: {exc}"
        ) from exc
