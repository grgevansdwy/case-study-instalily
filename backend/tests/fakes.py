"""Scripted stand-in for the OpenAI client, for deterministic loop tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable


def text_response(text: str) -> SimpleNamespace:
    """A final text reply from the model."""
    return SimpleNamespace(output=[SimpleNamespace(type="message")], output_text=text)


def calls_response(calls: list[tuple[str, Any]], *, prefix: str = "call") -> SimpleNamespace:
    """A response holding function calls. Arguments may be a dict or a raw string."""
    output = [
        SimpleNamespace(
            type="function_call",
            call_id=f"{prefix}_{index}",
            name=name,
            arguments=arguments if isinstance(arguments, str) else json.dumps(arguments),
        )
        for index, (name, arguments) in enumerate(calls)
    ]
    return SimpleNamespace(output=output, output_text="")


class ScriptedClient:
    """Records every request and replays scripted responses.

    `script` is a list consumed in order, or a function of the request index for
    an endless script. An item that is an exception is raised instead of returned.
    """

    def __init__(self, script: list[Any] | Callable[[int], Any]) -> None:
        self._script = script
        self.requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        index = len(self.requests)
        # The loop keeps appending to its input list, so snapshot it.
        self.requests.append({**kwargs, "input": list(kwargs.get("input", []))})
        if callable(self._script):
            item = self._script(index)
        elif index < len(self._script):
            item = self._script[index]
        else:
            raise AssertionError(f"ScriptedClient ran out of responses at request {index}")
        if isinstance(item, Exception):
            raise item
        return item
