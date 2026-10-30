import pytest
from helpers import answer, ended, make_agent, tool_call

from agent_lab.agents.react import ReActConfig, config_version
from agent_lab.llm.fake import FakeLLM
from agent_lab.tracing.span import SpanKind


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
