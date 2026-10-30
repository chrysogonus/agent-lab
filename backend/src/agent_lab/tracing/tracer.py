"""Span creation. Every LLM and tool call in an agent goes through `Tracer.span`."""

import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from secrets import token_hex
from typing import Any

from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span, SpanKind

# Called with ("span_started" | "span_ended", redacted span).
SpanSink = Callable[[str, Span], None]

_current: ContextVar[Span | None] = ContextVar("current_span", default=None)


class Tracer:
    def __init__(
        self,
        *,
        run_id: str,
        agent_id: str,
        config_version: str,
        sink: SpanSink,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.run_id = run_id
        self.agent_id = agent_id
        self.config_version = config_version
        self.trace_id = token_hex(16)
        self._sink = sink
        self._secrets = secrets

    @asynccontextmanager
    async def span(
        self,
        kind: SpanKind,
        name: str,
        *,
        node_id: str,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Open a child of the current span. Set `output`, `error`, tokens on the yielded span.

        An exception escaping the block is recorded as the span's error and re-raised.
        """
        parent = _current.get()
        span = Span(
            trace_id=self.trace_id,
            span_id=token_hex(8),
            parent_span_id=parent.span_id if parent else None,
            run_id=self.run_id,
            agent_id=self.agent_id,
            node_id=node_id,
            config_version=self.config_version,
            kind=kind,
            name=name,
            input=input,
            started_at=time.time(),
            attributes={"gen_ai.agent.id": self.agent_id, **(attributes or {})},
        )
        token = _current.set(span)
        self._emit("span_started", span)
        try:
            yield span
        except BaseException as exc:
            span.error = span.error or f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _current.reset(token)
            span.ended_at = time.time()
            self._emit("span_ended", span)

    def _emit(self, event: str, span: Span) -> None:
        data = redact(span.model_dump(mode="json"), self._secrets)
        self._sink(event, Span.model_validate(data))
