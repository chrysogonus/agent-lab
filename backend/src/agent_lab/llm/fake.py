"""Scripted model for tests: replays responses (or raises exceptions) in order."""

import asyncio
import copy
from collections.abc import Callable
from typing import Any

from agent_lab.llm.base import ChatResponse, Message

# A callable answers from the messages it gets: concurrent branches pop items in any order.
ScriptItem = ChatResponse | Exception | Callable[[list[Message]], ChatResponse | Exception]


class FakeLLM:
    provider = "fake"

    def __init__(
        self, script: list[ScriptItem], model: str = "fake-model", delay: float = 0
    ) -> None:
        self.model = model
        self.delay = delay  # seconds per call, so concurrent calls overlap measurably
        self._script = list(script)
        self.calls: list[list[Message]] = []
        self.requests: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        self.calls.append(copy.deepcopy(messages))
        self.requests.append(
            {"response_format": response_format, "reasoning": reasoning, "tools": tools}
        )
        if not self._script:
            raise AssertionError("FakeLLM script exhausted")
        item = self._script.pop(0)
        if self.delay:
            await asyncio.sleep(self.delay)
        if callable(item):
            item = item(messages)
        if isinstance(item, Exception):
            raise item
        return item
