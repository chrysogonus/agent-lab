"""Scripted model for tests: replays responses (or raises exceptions) in order."""

import copy
from typing import Any

from agent_lab.llm.base import ChatResponse, Message


class FakeLLM:
    provider = "fake"

    def __init__(self, script: list[ChatResponse | Exception], model: str = "fake-model") -> None:
        self.model = model
        self._script = list(script)
        self.calls: list[list[Message]] = []

    async def chat(self, messages: list[Message], tools: list[dict[str, Any]]) -> ChatResponse:
        self.calls.append(copy.deepcopy(messages))
        if not self._script:
            raise AssertionError("FakeLLM script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
