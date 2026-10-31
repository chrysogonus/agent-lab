"""Running block agents on the scripted model: every kind, nesting, stops (FR-002 to FR-011)."""

import json
from collections.abc import Sequence
from typing import Any

import pytest
from helpers import (
    BlockDict,
    answer,
    assert_trace_valid,
    blocks_config,
    ended,
    make_tracer,
    model_block,
    tool_block,
    tool_call,
)

from agent_lab.agents.steps import Outcome
from agent_lab.blocks.graph import build_graph
from agent_lab.blocks.run import BlockAgent
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span

PROMPT = "What is 17 times 23?"


async def run_blocks(
    blocks: list[BlockDict], script: Sequence[ScriptItem], prompt: str = PROMPT, delay: float = 0
) -> tuple[Outcome, list[Span], FakeLLM]:
    """Run the blocks and check every span lies on the derived graph (SC-003)."""
    config = blocks_config(*blocks)
    llm = FakeLLM(list(script), delay=delay)
    tracer, events = make_tracer("custom-1")
    outcome = await BlockAgent(llm=llm, config=config, tracer=tracer).run(prompt)
    spans = ended(events)
    assert_trace_valid(build_graph(config), spans)
    return outcome, spans, llm


def user_message(call: list[Any]) -> str:
    return call[1]["content"]


def end_from(spans: list[Span]) -> list[str]:
    end = next(s for s in spans if s.node_id == "end")
    return end.attributes.get("lab.came_from", [])


# --- US1: sequences of model and tool blocks ---


@pytest.mark.anyio
async def test_model_tool_model_sequence() -> None:
    blocks = [
        model_block("expr", system="Reply with only the arithmetic expression."),
        tool_block("calc", expression="{previous}"),
        model_block(
            "explain", system="Explain the result.", message="Question: {input}\nResult: {calc}"
        ),
    ]
    outcome, spans, llm = await run_blocks(blocks, [answer("17*23"), answer("It is 391.")])

    assert (outcome.status, outcome.answer) == ("completed", "It is 391.")
    assert user_message(llm.calls[0]) == PROMPT  # the first block's {previous} is the input
    assert llm.calls[0][0]["content"] == "Reply with only the arithmetic expression."
    assert user_message(llm.calls[1]) == f"Question: {PROMPT}\nResult: 391"
    tool = next(s for s in spans if s.kind == "tool")
    assert (tool.node_id, json.loads(tool.input), tool.output) == (
        "calc",
        {"expression": "17*23"},
        "391",
    )
    assert [s.node_id for s in spans if s.kind in ("llm", "tool")] == ["expr", "calc", "explain"]


@pytest.mark.anyio
async def test_tool_error_is_the_output() -> None:
    blocks = [tool_block("calc", expression="{input}"), model_block("say", message="{calc}")]
    outcome, spans, llm = await run_blocks(blocks, [answer("sorry")], prompt="two plus two")
    tool = next(s for s in spans if s.node_id == "calc")
    assert tool.error and user_message(llm.calls[0]).startswith("error: ")
    assert outcome.status == "completed"


@pytest.mark.anyio
async def test_model_block_with_tools_loops() -> None:
    blocks = [model_block("agent", tools=["calculator"], max_iterations=10)]
    script = [tool_call("calculator", '{"expression": "17*23"}'), answer("391")]
    outcome, spans, llm = await run_blocks(blocks, script)
    assert (outcome.status, outcome.answer) == ("completed", "391")
    assert llm.requests[0]["tools"][0]["function"]["name"] == "calculator"
    assert llm.calls[1][-1] == {"role": "tool", "tool_call_id": "c1", "content": "391"}
    assert [s.node_id for s in spans if s.kind in ("llm", "tool")] == [
        "agent",
        "tool:calculator",
        "agent",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("cap", [1, 10])
async def test_tool_loop_cap_stops_the_run(cap: int) -> None:
    blocks = [model_block("agent", tools=["calculator"], max_iterations=cap), model_block("next")]
    script = [tool_call("calculator", '{"expression": "1+1"}') for _ in range(cap)]
    outcome, spans, llm = await run_blocks(blocks, script)
    assert (outcome.status, outcome.answer) == ("max_iterations", None)
    assert len(llm.calls) == cap  # the next block never ran
    assert end_from(spans) == ["agent"]  # a declared terminal edge, though not the last block


@pytest.mark.anyio
async def test_reasoning_setting_reaches_every_call() -> None:
    config = blocks_config(model_block("a"), model_block("b"), reasoning=True)
    llm = FakeLLM([answer("x"), answer("y")])
    tracer, _ = make_tracer()
    await BlockAgent(llm=llm, config=config, tracer=tracer).run("hi")
    assert [r["reasoning"] for r in llm.requests] == [True, True]
