"""One run's limits and its stop mark, which `agents/steps.py` consults on every call.

A `ContextVar`, like the current span in `tracing/tracer.py`: `asyncio.gather` copies the context,
so parallel branches share one guard, and no agent has to pass it along. No guard (the village,
direct agent tests) means `steps` behaves as if the harness did not exist.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from agent_lab.harness.approvals import CaseDecider, Decider, Decision
from agent_lab.harness.budget import Harness, OverBudget
from agent_lab.llm.base import ChatResponse, PassingLLMError

_ATTEMPTS = 3  # a model call and up to 2 retries
_WAITS = (2, 8)  # seconds before each retry, longer each time
_LONGEST_HINT = 30  # the most a provider's own wait hint is honoured


class RunGuard:
    """Counts on the event loop, with no await between a check and its count: parallel branches
    cannot both take the last call. The first limit reached stays reached."""

    def __init__(
        self,
        harness: Harness,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        decider: Decider | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.harness = harness
        self.sleep = sleep  # injected so that tests of retry waits do not wait
        self.decider: Decider = decider or CaseDecider("deny")  # nobody to ask: do not call it
        self.on_status = on_status  # told when the run starts and stops waiting for the owner
        self.stop_requested = False
        self.last_text: str | None = None  # what the run has said so far, if it ends early
        self.over: str | None = None  # the limit reached, once one is
        self.model_calls = 0
        self.tool_calls = 0
        self.tokens = 0
        self._clock: asyncio.Timeout | None = None
        self._paused = 0  # waits open; the clock runs again when the last one ends
        self._left = 0.0  # seconds left when the clock was paused

    def _raise_if_over(self) -> None:
        budget = self.harness.budget
        if budget and self.over is None and self.tokens >= budget.tokens:
            self.over = OverBudget.of("tokens", self.tokens, budget.tokens).reason
        if self.over:
            raise OverBudget(self.over)

    def before_model_call(self) -> None:
        self._raise_if_over()
        budget = self.harness.budget
        if budget and self.model_calls >= budget.model_calls:
            self.over = OverBudget.of("model calls", self.model_calls, budget.model_calls).reason
            raise OverBudget(self.over)
        self.model_calls += 1

    def after_model_call(self, response: ChatResponse) -> None:
        if response.content:
            self.last_text = response.content
        self.tokens += (response.tokens_in or 0) + (response.tokens_out or 0)
        budget = self.harness.budget
        if budget and self.over is None and self.tokens > budget.tokens:
            self.over = OverBudget.of("tokens", self.tokens, budget.tokens).reason

    def before_tool_call(self) -> None:
        self._raise_if_over()
        budget = self.harness.budget
        if budget and self.tool_calls >= budget.tool_calls:
            self.over = OverBudget.of("tool calls", self.tool_calls, budget.tool_calls).reason
            raise OverBudget(self.over)
        self.tool_calls += 1

    def retry_wait(self, error: PassingLLMError, attempt: int) -> float | None:
        """Seconds before trying again, or None to give up. A wait past the time budget ends the
        run instead of being waited out."""
        if attempt >= _ATTEMPTS:
            return None
        wait = (
            _WAITS[attempt - 1] if error.wait_hint is None else min(error.wait_hint, _LONGEST_HINT)
        )
        budget = self.harness.budget
        left = self._clock.when() if self._clock else None
        if budget and left is not None and wait > left - asyncio.get_running_loop().time():
            self.over = self.over or OverBudget.of_time(budget.seconds).reason
            raise OverBudget(self.over)
        return wait

    def asks_first(self, tool: str) -> bool:
        return tool in self.harness.ask_first

    async def decide(self, tool: str, server: str, arguments: dict[str, Any]) -> Decision:
        """Whether a tool marked ask first may be called. Parallel branches may wait at once."""
        self._raise_if_over()
        if self.decider.immediate:
            return await self.decider.decide(tool, server, arguments)
        self.pause_clock()
        if self._paused == 1 and self.on_status:
            self.on_status("waiting_approval")
        try:
            return await self.decider.decide(tool, server, arguments)
        finally:
            self.resume_clock()
            if self._paused == 0 and self.on_status:
                self.on_status("running")

    def bind_clock(self, clock: asyncio.Timeout) -> None:
        self._clock = clock

    def pause_clock(self) -> None:
        """Time with a question open to the owner does not count, whatever other branches do."""
        self._paused += 1
        if self._paused == 1 and self._clock and (when := self._clock.when()) is not None:
            self._left = when - asyncio.get_running_loop().time()
            self._clock.reschedule(None)

    def resume_clock(self) -> None:
        self._paused -= 1
        if self._paused == 0 and self._clock and self.harness.budget:
            self._clock.reschedule(asyncio.get_running_loop().time() + self._left)


current_guard: ContextVar[RunGuard | None] = ContextVar("current_guard", default=None)
