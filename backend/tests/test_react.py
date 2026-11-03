import pytest
from helpers import (
    answer,
    assert_trace_valid,
    ended,
    lab_tools,
    make_agent,
    make_tracer,
    taken_edges,
    tool_call,
)

from agent_lab.agents.react import ReActAgent, ReActConfig, ReActState, build_graph
from agent_lab.agents.steps import config_version
from agent_lab.llm.base import LLMError
from agent_lab.llm.fake import FakeLLM
from agent_lab.tracing.span import Span, SpanKind


@pytest.mark.anyio
async def test_multi_step_tool_run() -> None:
    llm = FakeLLM(
        [
            tool_call("calculator", '{"expression": "17*23"}', "c1"),
            tool_call("get_weather", '{"city": "Berlin"}', "c2"),
            answer("391 and mild"),
        ]
    )
    agent, events = make_agent(llm)
    state = await agent.run("What is 17*23, and the weather in Berlin?")

    assert state.status == "completed"
    assert state.answer == "391 and mild"
    # The tool result reached the model on the next call.
    assert llm.calls[1][-1] == {"role": "tool", "tool_call_id": "c1", "content": "391"}

    spans = ended(events)
    by_id = {s.span_id: s for s in spans}
    assert [(s.kind, s.node_id, s.name) for s in spans] == [
        (SpanKind.STEP, "start", "invoke_agent react"),
        (SpanKind.STEP, "llm", "iteration 1"),
        (SpanKind.LLM, "llm", "chat fake-model"),
        (SpanKind.TOOL, "tool:calculator", "execute_tool calculator"),
        (SpanKind.STEP, "llm", "iteration 2"),
        (SpanKind.LLM, "llm", "chat fake-model"),
        (SpanKind.TOOL, "tool:get_weather", "execute_tool get_weather"),
        (SpanKind.STEP, "llm", "iteration 3"),
        (SpanKind.LLM, "llm", "chat fake-model"),
        (SpanKind.STEP, "end", "final answer"),
    ]
    # Nesting: iterations and the end span under the root; calls under their iteration.
    root = spans[0]
    assert root.parent_span_id is None
    assert {by_id[s.parent_span_id].name for s in spans[1:] if s.parent_span_id} == {
        "invoke_agent react",
        "iteration 1",
        "iteration 2",
        "iteration 3",
    }
    assert spans[2].parent_span_id == spans[1].span_id
    assert spans[3].parent_span_id == spans[1].span_id
    # Every span is complete, attributed and points at a declared node.
    graph_nodes = agent.graph.node_ids()
    for s in spans:
        assert s.node_id in graph_nodes
        assert s.ended_at is not None and s.ended_at >= s.started_at
        assert (s.run_id, s.agent_id) == ("run-1", "react")
        assert s.config_version == config_version(agent.config)
    assert len({s.trace_id for s in spans}) == 1
    llm_span = spans[2]
    assert llm_span.input[0]["role"] == "system"
    assert llm_span.input[1] == {"role": "user", "content": state.messages[1]["content"]}
    assert (llm_span.model, llm_span.tokens_in, llm_span.tokens_out) == ("fake-model", 10, 5)
    assert llm_span.attributes["gen_ai.usage.input_tokens"] == 10
    assert spans[3].output == "391"
    assert root.output == "391 and mild"
    assert spans[-1].output == "391 and mild"


def test_config_version_stable() -> None:
    config = ReActConfig(model="m", tools=["calculator"])
    assert config_version(config) == config_version(ReActConfig(model="m", tools=["calculator"]))
    assert config_version(config) != config_version(
        ReActConfig(model="m", tools=["calculator"], max_iterations=3)
    )


@pytest.mark.anyio
async def test_tool_error_fed_back() -> None:
    llm = FakeLLM([tool_call("calculator", '{"expression": "1/0"}'), answer("cannot divide")])
    agent, events = make_agent(llm)
    state = await agent.run("1/0?")

    assert state.status == "completed"
    tool_span = next(s for s in ended(events) if s.kind == SpanKind.TOOL)
    assert tool_span.error == "division by zero"
    assert tool_span.node_id == "tool:calculator"
    assert llm.calls[1][-1]["content"] == "error: division by zero"
    # The error stays on the tool span; its ancestors are not failed.
    assert [s.error for s in ended(events) if s.kind == SpanKind.STEP] == [None] * 4


@pytest.mark.anyio
async def test_unknown_tool_and_bad_args() -> None:
    llm = FakeLLM(
        [
            tool_call("rm_rf", "{}", "c1"),
            tool_call("calculator", "{not json", "c2"),
            tool_call("calculator", '{"expr": "1"}', "c3"),
            answer("gave up"),
        ]
    )
    agent, events = make_agent(llm)
    state = await agent.run("break things")

    assert state.status == "completed"
    tool_spans = [s for s in ended(events) if s.kind == SpanKind.TOOL]
    assert [s.node_id for s in tool_spans] == ["llm", "tool:calculator", "tool:calculator"]
    errors = [s.error or "" for s in tool_spans]
    assert errors[0] == "unknown tool 'rm_rf'"
    assert errors[1].startswith("arguments are not valid JSON")
    assert errors[2].startswith("invalid arguments")
    assert all(s.node_id in agent.graph.node_ids() for s in ended(events))
    # The unknown tool records no edge; the next turn continues on the llm node.
    assert_trace_valid(agent.graph, ended(events))
    iteration_2 = next(s for s in ended(events) if s.name == "iteration 2")
    assert "lab.came_from" not in iteration_2.attributes


@pytest.mark.anyio
async def test_max_iterations_cap() -> None:
    llm = FakeLLM([tool_call("get_weather", '{"city": "Rome"}')] * 10)
    agent, events = make_agent(llm, max_iterations=3)
    state = await agent.run("loop forever")

    assert state.status == "max_iterations"
    assert state.answer is None
    assert len(llm.calls) == 3
    spans = ended(events)
    end = spans[-1]
    assert (end.node_id, end.error) == ("end", "max iterations (3) reached")
    assert spans[0].error == "max iterations (3) reached"
    assert sum(1 for s in spans if s.kind == SpanKind.LLM) == 3


@pytest.mark.anyio
async def test_model_error_fails_run() -> None:
    llm = FakeLLM([LLMError("HTTP 500: boom")])
    agent, events = make_agent(llm)
    with pytest.raises(LLMError):
        await agent.run("hi")
    spans = ended(events)
    assert [s.name for s in spans] == ["invoke_agent react", "iteration 1", "chat fake-model"]
    assert all(s.error == "LLMError: HTTP 500: boom" for s in spans)


@pytest.mark.anyio
async def test_reasoning_traced_not_resent() -> None:
    thinking = tool_call("calculator", '{"expression": "2+3"}')
    thinking.reasoning = "I should use the calculator."
    llm = FakeLLM([thinking, answer("5")])
    agent, events = make_agent(llm)
    await agent.run("2+3?")

    first_llm = next(s for s in ended(events) if s.kind == SpanKind.LLM)
    assert first_llm.output["reasoning"] == "I should use the calculator."
    # The model's history holds the assistant message without the reasoning.
    assert all("reasoning" not in m for m in llm.calls[1])


@pytest.mark.anyio
async def test_reasoning_on_by_default() -> None:
    llm = FakeLLM([answer("hi")])
    agent, _ = make_agent(llm)
    await agent.run("hi")
    assert agent.config.reasoning is True
    assert llm.requests[0]["reasoning"] is True


@pytest.mark.anyio
async def test_react_came_from_edges() -> None:
    llm = FakeLLM(
        [
            tool_call("calculator", '{"expression": "1+1"}', "c1"),
            tool_call("get_weather", '{"city": "Rome"}', "c2"),
            answer("done"),
        ]
    )
    agent, events = make_agent(llm)
    await agent.run("go")

    spans = ended(events)
    assert_trace_valid(agent.graph, spans)
    assert taken_edges(spans) == {
        ("start", "llm"),
        ("llm", "tool:calculator"),
        ("tool:calculator", "llm"),
        ("llm", "tool:get_weather"),
        ("tool:get_weather", "llm"),
        ("llm", "end"),
    }


async def run_with(
    config: ReActConfig, llm: FakeLLM, prompt: str = "q"
) -> tuple[ReActState, list[Span]]:
    """Runs the agent as the registry builds it: tools come from the config's names."""
    tracer, events = make_tracer("react")
    agent = ReActAgent(llm=llm, tools=lab_tools(), config=config, tracer=tracer)
    return await agent.run(prompt), ended(events)


@pytest.mark.anyio
async def test_no_tools() -> None:
    config = ReActConfig(model="m", tools=[])
    llm = FakeLLM([answer("hi")])
    state, spans = await run_with(config, llm)

    assert state.status == "completed"
    assert build_graph(config.tools).node_ids() == {"start", "llm", "end"}
    assert llm.requests[0]["tools"] == []
    assert_trace_valid(build_graph(config.tools), spans)


@pytest.mark.anyio
async def test_calculator_only() -> None:
    config = ReActConfig(model="m", tools=["calculator"])
    llm = FakeLLM([tool_call("calculator", '{"expression": "2+2"}'), answer("4")])
    state, spans = await run_with(config, llm)

    assert state.answer == "4"
    assert [t["function"]["name"] for t in llm.requests[0]["tools"]] == ["calculator"]
    assert "tool:get_weather" not in build_graph(config.tools).node_ids()
    assert_trace_valid(build_graph(config.tools), spans)


@pytest.mark.anyio
async def test_iteration_limits() -> None:
    calc = tool_call("calculator", '{"expression": "1+1"}')
    direct, _ = await run_with(ReActConfig(model="m", max_iterations=1), FakeLLM([answer("ok")]))
    capped, spans = await run_with(ReActConfig(model="m", max_iterations=1), FakeLLM([calc]))
    longest, long_spans = await run_with(
        ReActConfig(model="m", max_iterations=10), FakeLLM([*[calc] * 9, answer("done")])
    )

    assert direct.status == "completed"
    assert capped.status == "max_iterations"
    assert (longest.status, longest.iteration) == ("completed", 10)
    graph = build_graph(["calculator", "get_weather"])
    assert_trace_valid(graph, spans)
    assert_trace_valid(graph, long_spans)


@pytest.mark.anyio
async def test_the_sample_calls_the_labs_server_over_mcp() -> None:
    llm = FakeLLM(
        [
            tool_call("calculator", '{"expression": "17*23"}', "c1"),
            tool_call("get_weather", '{"city": "Berlin"}', "c2"),
            answer("done"),
        ]
    )
    agent, events = make_agent(llm)
    await agent.run("What is 17*23 plus the current temperature in Berlin?")
    tools = [s for s in ended(events) if s.kind == SpanKind.TOOL]
    assert [s.attributes["lab.mcp.server"] for s in tools] == ["lab", "lab"]
    assert [s.attributes["lab.mcp.request"]["params"]["name"] for s in tools] == [
        "calculator",
        "get_weather",
    ]
    assert tools[0].attributes["lab.mcp.response"]["result"]["content"][0]["text"] == "391"
