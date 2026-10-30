import pytest
from helpers import answer, ended, make_agent, tool_call

from agent_lab.agents.react import ReActAgent, ReActConfig, config_version
from agent_lab.llm.base import LLMError
from agent_lab.llm.fake import FakeLLM
from agent_lab.tools.base import Tool
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer


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


def test_ungranted_scope_rejected() -> None:
    risky = Tool(
        name="read_file",
        description="",
        parameters={},
        fn=lambda: "",
        scopes=frozenset({"fs:read"}),
    )
    config = ReActConfig(model="m", tools=["read_file"])
    tracer = Tracer(run_id="r", agent_id="react", config_version="v", sink=lambda e, s: None)
    with pytest.raises(ValueError, match="ungranted scopes"):
        ReActAgent(llm=FakeLLM([]), tools=[risky], config=config, tracer=tracer)
