"""One run's limits and its stop mark, which `agents/steps.py` consults on every call.

A `ContextVar`, like the current span in `tracing/tracer.py`: `asyncio.gather` copies the context,
so parallel branches share one guard, and no agent has to pass it along. No guard (the village,
direct agent tests) means `steps` behaves as if the harness did not exist.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from agent_lab.harness.budget import Harness
from agent_lab.llm.base import ChatResponse


class RunGuard:
    def __init__(
        self, harness: Harness, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    ) -> None:
        self.harness = harness
        self.sleep = sleep  # injected so that tests of retry waits do not wait
        self.stop_requested = False
        self.last_text: str | None = None  # what the run has said so far, if it ends early

    def after_model_call(self, response: ChatResponse) -> None:
        if response.content:
            self.last_text = response.content


current_guard: ContextVar[RunGuard | None] = ContextVar("current_guard", default=None)
