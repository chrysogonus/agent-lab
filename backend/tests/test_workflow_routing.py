import pytest
from helpers import (
    answer,
    assert_trace_valid,
    ended,
    json_answer,
    lab_tools,
    make_tracer,
    taken_edges,
    tool_call,
)

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span, SpanKind
from agent_lab.workflows.routing import (
    AGENT_ID,
    Config,
    RouteSpec,
    RoutingWorkflow,
    build_graph,
    router_system,
)


async def run(
    script: list[ScriptItem], config: Config | None = None
) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    config = config or Config(model=llm.model)
    workflow = RoutingWorkflow(llm=llm, config=config, tracer=tracer, tools=lab_tools())
    outcome = await workflow.run("question")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([json_answer({"label": "general"}), answer("Paris")])

    assert (outcome.status, outcome.answer) == ("completed", "Paris")
    assert_trace_valid(build_graph(Config(model="m")), spans)
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
    assert_trace_valid(build_graph(Config(model="m")), spans)


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
    assert_trace_valid(build_graph(Config(model="m")), spans)


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
    assert_trace_valid(build_graph(Config(model="m")), spans)


@pytest.mark.anyio
async def test_invalid_label_falls_back_to_general() -> None:
    outcome, spans, _ = await run([json_answer({"label": "sports"}), answer("Go team")])

    assert (outcome.status, outcome.answer) == ("completed", "Go team")
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert route.error is not None and "sports" in route.error
    assert route.output is None
    assert ("router", "general") in taken_edges(spans)
    assert_trace_valid(build_graph(Config(model="m")), spans)


POEM = RouteSpec(name="poem", description="requests for a poem", prompt="Write a short poem.")


def with_routes(*extra: RouteSpec, fallback: str = "general") -> Config:
    base = Config(model="m")
    return base.model_copy(update={"routes": [*base.routes, *extra], "fallback": fallback})


def schema_labels(llm: FakeLLM) -> list[str]:
    response_format = llm.requests[0]["response_format"]
    assert response_format is not None
    return response_format["json_schema"]["schema"]["properties"]["label"]["enum"]


@pytest.mark.anyio
async def test_custom_route_poem() -> None:
    config = with_routes(POEM)
    outcome, spans, llm = await run([json_answer({"label": "poem"}), answer("Leaves fall")], config)

    assert (outcome.status, outcome.answer) == ("completed", "Leaves fall")
    assert taken_edges(spans) == {("start", "router"), ("router", "poem"), ("poem", "end")}
    assert llm.calls[1][0]["content"] == "Write a short poem."
    assert llm.requests[1]["tools"] == []
    assert_trace_valid(build_graph(config), spans)


@pytest.mark.anyio
async def test_route_schema_lists_custom_routes() -> None:
    _, _, llm = await run([json_answer({"label": "poem"}), answer("x")], with_routes(POEM))
    assert schema_labels(llm) == ["math", "weather", "poem", "general"]


@pytest.mark.anyio
async def test_default_route_schema_matches_m2() -> None:
    _, _, llm = await run([json_answer({"label": "general"}), answer("x")])
    assert llm.requests[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "route",
            "schema": {
                "properties": {
                    "label": {
                        "enum": ["math", "weather", "general"],
                        "title": "Label",
                        "type": "string",
                    }
                },
                "required": ["label"],
                "title": "Route",
                "type": "object",
            },
            "strict": True,
        },
    }


def test_router_prompt_lists_fallback_last() -> None:
    assert router_system(with_routes(POEM, fallback="math")) == (
        "Classify the user's question. general: anything else. weather: the weather or "
        "temperature in a city. poem: requests for a poem. math: arithmetic or a calculation."
    )
    assert router_system(Config(model="m")) == (
        "Classify the user's question. math: arithmetic or a calculation. weather: the weather "
        "or temperature in a city. general: anything else."
    )


@pytest.mark.anyio
async def test_shared_tool_is_one_node() -> None:
    sums = RouteSpec(name="sums", description="adding up", prompt="Add.", tool="calculator")
    config = with_routes(sums)
    graph = build_graph(config)
    assert [n.id for n in graph.nodes].count("tool:calculator") == 1
    edges = {(e.source, e.target) for e in graph.edges}
    assert {("sums", "tool:calculator"), ("tool:calculator", "sums")} <= edges
    assert {("math", "tool:calculator"), ("tool:calculator", "math")} <= edges

    script: list[ScriptItem] = [
        json_answer({"label": "sums"}),
        tool_call("calculator", '{"expression": "2+2"}'),
        answer("4"),
    ]
    outcome, spans, _ = await run(script, config)
    assert outcome.answer == "4"
    assert ("tool:calculator", "sums") in taken_edges(spans)
    assert_trace_valid(graph, spans)


@pytest.mark.anyio
async def test_invalid_label_uses_custom_fallback() -> None:
    config = with_routes(POEM, fallback="poem")
    outcome, spans, _ = await run([json_answer({"label": "sports"}), answer("A poem")], config)

    assert (outcome.status, outcome.answer) == ("completed", "A poem")
    assert ("router", "poem") in taken_edges(spans)
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert route.error is not None


@pytest.mark.anyio
@pytest.mark.parametrize("count", [2, 6])
async def test_two_and_six_routes(count: int) -> None:
    routes = [
        RouteSpec(name=f"r{i}", description=f"case {i}", prompt=f"Do {i}.") for i in range(count)
    ]
    config = Config(model="m", routes=routes, fallback="r0")
    last = f"r{count - 1}"
    outcome, spans, llm = await run([json_answer({"label": last}), answer("done")], config)

    assert outcome.status == "completed"
    assert schema_labels(llm) == [f"r{i}" for i in range(1, count)] + ["r0"]
    assert taken_edges(spans) == {("start", "router"), ("router", last), (last, "end")}
    assert_trace_valid(build_graph(config), spans)
