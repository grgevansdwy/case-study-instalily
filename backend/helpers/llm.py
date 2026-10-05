"""The only place that talks to the model provider."""

from __future__ import annotations

import os
from typing import Any

import openai
from backend.helpers import config  # noqa: F401  (loads .env before the key is read)


class ProviderError(Exception):
    """The model provider could not be reached or rejected the request."""


def get_client() -> openai.OpenAI:
    """Return the OpenAI client. Tests patch this function with a scripted fake."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise ProviderError("OPENAI_API_KEY is not set.")
    return openai.OpenAI(max_retries=1)


def call_model(
    *,
    model: str,
    instructions: str,
    input: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    timeout: float,
    text: dict[str, Any] | None = None,
) -> Any:
    """One Responses API call. The caller owns the input list (`store=False`).

    `text` is the structured-output format; only the router passes it.
    """
    client = get_client()
    extra = {"text": text} if text is not None else {}
    try:
        return client.responses.create(
            model=model,
            instructions=instructions,
            input=input,
            tools=tools,
            store=False,
            temperature=0,
            timeout=timeout,
            **extra,
        )
    except openai.OpenAIError as exc:
        raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
