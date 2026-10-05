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


def router_response(names: list[str]) -> SimpleNamespace:
    """The router's structured output: a JSON object holding tool names."""
    return text_response(json.dumps({"tools": names}))


class ScriptedClient:
    """Records every request and replays scripted responses.

    `script` drives the agent calls: a list consumed in order, or a function of
    the request index for an endless script. An item that is an exception is
    raised instead of returned.

    `router` drives the router calls (the requests that carry a `text` format):
    a list of tool names returned every time, or a function of the router
    request index returning a response or an exception. The default selects no
    tools. Agent requests are kept in `requests`, router requests in
    `router_requests`.
    """

    def __init__(
        self,
        script: list[Any] | Callable[[int], Any],
        router: list[str] | Callable[[int], Any] | None = None,
    ) -> None:
        self._script = script
        self._router = router
        self.requests: list[dict[str, Any]] = []
        self.router_requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        # The loop keeps appending to its input list, so snapshot it.
        request = {**kwargs, "input": list(kwargs.get("input", []))}
        if "text" in kwargs:
            index = len(self.router_requests)
            self.router_requests.append(request)
            if callable(self._router):
                item = self._router(index)
            else:
                item = router_response(list(self._router or []))
        else:
            index = len(self.requests)
            self.requests.append(request)
            if callable(self._script):
                item = self._script(index)
            elif index < len(self._script):
                item = self._script[index]
            else:
                raise AssertionError(f"ScriptedClient ran out of responses at request {index}")
        if isinstance(item, Exception):
            raise item
        return item
