import pytest

from agent_lab.tracing.redact import REDACTED, redact
from agent_lab.tracing.span import Span, SpanKind
from agent_lab.tracing.tracer import Tracer


def make_tracer(events: list[tuple[str, Span]], secrets: tuple[str, ...] = ()) -> Tracer:
    return Tracer(
        run_id="r1",
        agent_id="a1",
        config_version="v1",
        sink=lambda event, span: events.append((event, span)),
        secrets=secrets,
    )


@pytest.mark.anyio
async def test_nesting_and_events() -> None:
    events: list[tuple[str, Span]] = []
    tracer = make_tracer(events)
    async with (
        tracer.span(SpanKind.STEP, "outer", node_id="n1") as outer,
        tracer.span(SpanKind.LLM, "inner", node_id="n2") as inner,
    ):
        inner.output = "hi"

    assert [(e, s.name) for e, s in events] == [
        ("span_started", "outer"),
        ("span_started", "inner"),
        ("span_ended", "inner"),
        ("span_ended", "outer"),
    ]
    ended_inner = events[2][1]
    assert ended_inner.parent_span_id == outer.span_id
    assert ended_inner.trace_id == outer.trace_id
    assert ended_inner.output == "hi"
    assert ended_inner.ended_at is not None
    assert events[0][1].parent_span_id is None
    assert events[0][1].ended_at is None


@pytest.mark.anyio
async def test_exception_recorded_and_reraised() -> None:
    events: list[tuple[str, Span]] = []
    tracer = make_tracer(events)
    with pytest.raises(RuntimeError):
        async with (
            tracer.span(SpanKind.STEP, "outer", node_id="n1"),
            tracer.span(SpanKind.LLM, "inner", node_id="n2"),
        ):
            raise RuntimeError("boom")
    ended = [s for e, s in events if e == "span_ended"]
    assert [s.error for s in ended] == ["RuntimeError: boom", "RuntimeError: boom"]


@pytest.mark.anyio
async def test_sink_receives_redacted_copy() -> None:
    events: list[tuple[str, Span]] = []
    tracer = make_tracer(events, secrets=("hunter2-secret",))
    async with tracer.span(
        SpanKind.LLM, "call", node_id="n", input={"headers": {"Authorization": "Bearer abc"}}
    ) as span:
        span.output = "key is hunter2-secret"
    ended = events[-1][1]
    assert ended.input == {"headers": {"Authorization": REDACTED}}
    assert ended.output == f"key is {REDACTED}"
    assert span.output == "key is hunter2-secret"  # the live object is untouched


def test_redact_keys_case_and_dash_insensitive() -> None:
    data = {"X-Api-Key": "k", "API_KEY": "k", "nested": [{"password": "p", "ok": "fine"}]}
    assert redact(data) == {
        "X-Api-Key": REDACTED,
        "API_KEY": REDACTED,
        "nested": [{"password": REDACTED, "ok": "fine"}],
    }


def test_redact_patterns_in_text() -> None:
    text = "use Bearer eyJhbGciOi.abc-def and sk-abcdefghijklmnopqrstu please"
    assert redact(text) == f"use {REDACTED} and {REDACTED} please"


def test_redact_leaves_non_secrets() -> None:
    data = {"tokens_in": 12, "content": "What is 2+2?", "model": None}
    assert redact(data) == data
