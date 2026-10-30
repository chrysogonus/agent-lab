import pytest
from helpers import (
    answer,
    assert_trace_valid,
    ended,
    json_answer,
    make_tracer,
    taken_edges,
    tool_call,
)

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span, SpanKind
from agent_lab.workflows.routing import AGENT_ID, Config, RoutingWorkflow, build_graph


async def run(script: list[ScriptItem]) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    workflow = RoutingWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("question")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([json_answer({"label": "general"}), answer("Paris")])

    assert (outcome.status, outcome.answer) == ("completed", "Paris")
    assert_trace_valid(build_graph(), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert route.output == {"label": "general"}
    assert taken_edges(spans) == {("start", "router"), ("router", "general"), ("general", "end")}


@pytest.mark.anyio
async def test_route_math() -> None:
    outcome, spans, llm = await run(
        [
            json_answer({"label": "math"}),
            tool_call("calculator", '{"expression": "2**10 - 24"}'),
            answer("1000"),
        ]
    )

    assert (outcome.status, outcome.answer) == ("completed", "1000")
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert (route.name, route.output) == ("route", {"label": "math"})
    assert route.input["schema"]["properties"]["label"]["enum"] == ["math", "weather", "general"]
    tool = next(s for s in spans if s.kind == SpanKind.TOOL)
    assert (tool.node_id, tool.output) == ("tool:calculator", "1000")
    # The math handler is offered only its own tool, and the answer call none.
    assert [t["function"]["name"] for t in llm.requests[1]["tools"]] == ["calculator"]
    assert llm.requests[2]["tools"] == []
    assert taken_edges(spans) == {
        ("start", "router"),
        ("router", "math"),
        ("math", "tool:calculator"),
        ("tool:calculator", "math"),
        ("math", "end"),
    }
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_route_weather() -> None:
    outcome, spans, _ = await run(
        [
            json_answer({"label": "weather"}),
            tool_call("get_weather", '{"city": "Oslo"}'),
            answer("cold"),
        ]
    )

    assert outcome.answer == "cold"
    assert {s.node_id for s in spans} == {"start", "router", "weather", "tool:get_weather", "end"}
    assert taken_edges(spans) == {
        ("start", "router"),
        ("router", "weather"),
        ("weather", "tool:get_weather"),
        ("tool:get_weather", "weather"),
        ("weather", "end"),
    }
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_handler_answers_without_tool() -> None:
    outcome, spans, llm = await run([json_answer({"label": "math"}), answer("2")])

    assert outcome.answer == "2"
    assert len(llm.calls) == 2
    assert taken_edges(spans) == {("start", "router"), ("router", "math"), ("math", "end")}


@pytest.mark.anyio
async def test_handler_unknown_tool_records_no_edge() -> None:
    _, spans, _ = await run(
        [
            json_answer({"label": "math"}),
            tool_call("get_weather", '{"city": "Oslo"}'),  # not offered to math
            answer("cannot"),
        ]
    )

    tool = next(s for s in spans if s.kind == SpanKind.TOOL)
    assert (tool.node_id, tool.error) == ("math", "unknown tool 'get_weather'")
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_invalid_label_falls_back_to_general() -> None:
    outcome, spans, _ = await run([json_answer({"label": "sports"}), answer("Go team")])

    assert (outcome.status, outcome.answer) == ("completed", "Go team")
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert route.error is not None and "sports" in route.error
    assert route.output is None
    assert ("router", "general") in taken_edges(spans)
    assert_trace_valid(build_graph(), spans)
