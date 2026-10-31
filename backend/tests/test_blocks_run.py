"""Running block agents on the scripted model: every kind, nesting, stops (FR-002 to FR-011)."""

import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest
from helpers import (
    BlockDict,
    answer,
    assert_trace_valid,
    blocks_config,
    branches_block,
    check_block,
    ended,
    json_answer,
    loop_block,
    make_tracer,
    model_block,
    per_item_block,
    router_block,
    tool_block,
    tool_call,
)

from agent_lab.agents.steps import Outcome
from agent_lab.blocks.graph import build_graph
from agent_lab.blocks.run import BlockAgent
from agent_lab.llm.base import ChatResponse
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tools import catalog
from agent_lab.tools.calculator import CALCULATOR
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


# --- US2: control blocks ---


def echo(messages: list[Any]) -> ChatResponse:
    """Answers with the user message, so concurrent branches get predictable outputs."""
    return answer(f"done: {messages[-1]['content']}")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rule", "value", "text", "passes"),
    [
        ("min_bullets", 2, "- a\n- b", True),
        ("min_bullets", 3, "- a\n- b", False),
        ("max_words", 3, "one two three", True),
        ("max_words", 2, "one two three", False),
        ("contains", "391", "it is 391", True),
        ("contains", "391", "it is 390", False),
        ("valid_json", None, '{"a": 1}', True),
        ("valid_json", None, "not json", False),
    ],
)
async def test_check_rules(rule: str, value: Any, text: str, passes: bool) -> None:
    blocks = [model_block("draft"), check_block("enough", rule, value), model_block("after")]
    script = [answer(text), answer("final")] if passes else [answer(text)]
    outcome, spans, llm = await run_blocks(blocks, script)
    if passes:
        assert (outcome.status, outcome.answer) == ("completed", "final")
        assert user_message(llm.calls[1]) == text  # a passing check passes its input on
    else:
        assert (
            outcome.status == "error" and outcome.error and "check enough failed" in outcome.error
        )
        assert len(llm.calls) == 1 and end_from(spans) == ["enough"]


@pytest.mark.anyio
async def test_router_picks_a_route_of_two_blocks() -> None:
    routes = {
        "math": [model_block("m1"), model_block("m2", message="{m1}!")],
        "other": [model_block("o")],
    }
    blocks = [router_block("route", routes), model_block("say", message="{route}")]
    outcome, spans, llm = await run_blocks(
        blocks, [json_answer({"label": "math"}), answer("a"), answer("b"), answer("c")]
    )
    assert outcome.answer == "c"
    assert [user_message(c) for c in llm.calls[1:]] == [PROMPT, "a!", "b"]
    assert llm.requests[0]["response_format"]["json_schema"]["schema"]["properties"]["label"][
        "enum"
    ] == ["math", "other"]
    assert "o" not in {s.node_id for s in spans}


@pytest.mark.anyio
async def test_router_invalid_label_uses_fallback() -> None:
    routes = {"other": [model_block("o")], "math": [model_block("m")]}
    blocks = [router_block("route", routes, fallback="other")]
    outcome, spans, _ = await run_blocks(
        blocks, [json_answer({"label": "sports"}), answer("fallback")]
    )
    assert (outcome.status, outcome.answer) == ("completed", "fallback")
    route_span = next(s for s in spans if s.node_id == "route" and s.kind == "route")
    assert route_span.error  # the unusable decision stays visible


@pytest.mark.anyio
async def test_parallel_branches_run_together() -> None:
    blocks = [
        branches_block(
            "reviews",
            {"a": [model_block("ra")], "b": [model_block("rb")], "c": [model_block("rc")]},
        ),
        model_block("merge", message="{reviews}"),
    ]
    outcome, spans, llm = await run_blocks(blocks, [echo, echo, echo, echo], delay=0.05)
    reviews = [s for s in spans if s.node_id in ("ra", "rb", "rc")]
    assert max(s.started_at for s in reviews) < min(s.ended_at or 0 for s in reviews)  # overlap
    assert user_message(llm.calls[-1]) == "\n\n".join(f"{b}:\ndone: {PROMPT}" for b in "abc")
    assert next(s for s in spans if s.node_id == "merge").attributes["lab.came_from"] == [
        "ra",
        "rb",
        "rc",
    ]
    assert outcome.status == "completed"


@pytest.mark.anyio
async def test_failing_branch_ends_run_after_the_others_finish() -> None:
    blocks = [branches_block("p", {"a": [model_block("ok")], "b": [model_block("bad")]})]

    llm_script: list[ScriptItem] = [answer("fine"), RuntimeError("model down")]
    config = blocks_config(*blocks)
    llm = FakeLLM(llm_script, delay=0.02)
    tracer, events = make_tracer()
    with pytest.raises(RuntimeError):
        await BlockAgent(llm=llm, config=config, tracer=tracer).run(PROMPT)
    ended_nodes = {s.node_id for s in ended(events)}
    assert {"ok", "bad"} <= ended_nodes  # both branches finished and are in the trace


@pytest.mark.anyio
@pytest.mark.parametrize("items", [1, 6])
async def test_per_item_runs_body_once_per_item(items: int) -> None:
    parts = [f"part {i}" for i in range(items)]
    blocks = [
        per_item_block("plan", [model_block("work", message="{input} / {item}")], max_items=items),
        model_block("sum"),
    ]
    script: list[ScriptItem] = [
        json_answer({"subtasks": parts}),
        *([echo] * items),
        answer("summary"),
    ]
    outcome, spans, llm = await run_blocks(blocks, script, delay=0.01)
    assert outcome.answer == "summary"
    assert sorted(user_message(c) for c in llm.calls[1:-1]) == sorted(
        f"{PROMPT} / {p}" for p in parts
    )
    assert user_message(llm.calls[-1]) == "\n\n".join(f"{p}:\ndone: {PROMPT} / {p}" for p in parts)
    assert len([s for s in spans if s.node_id == "work"]) == items


@pytest.mark.anyio
async def test_plan_above_the_limit_stops_from_the_planner() -> None:
    blocks = [per_item_block("plan", [model_block("work")], max_items=2)]
    outcome, spans, _ = await run_blocks(blocks, [json_answer({"subtasks": ["a", "b", "c"]})])
    assert outcome.status == "error" and end_from(spans) == ["plan"]


@pytest.mark.anyio
async def test_loop_feedback_reaches_the_next_round() -> None:
    blocks = [
        loop_block("improve", [model_block("gen", message="{input}|{feedback}")], max_rounds=3)
    ]
    script: list[ScriptItem] = [
        answer("v1"),
        json_answer({"approved": False, "feedback": "shorter"}),
        answer("v2"),
        json_answer({"approved": True, "feedback": ""}),
    ]
    outcome, _, llm = await run_blocks(blocks, script)
    assert (outcome.status, outcome.answer) == ("completed", "v2")
    assert user_message(llm.calls[0]) == f"{PROMPT}|"
    assert user_message(llm.calls[2]) == f"{PROMPT}|Previous answer:\nv1\n\nFeedback:\nshorter"
    assert user_message(llm.calls[1]) == "v1"  # the judge reads the body's output


@pytest.mark.anyio
async def test_unreadable_verdict_counts_as_rejection() -> None:
    blocks = [loop_block("improve", [model_block("gen", message="{feedback}")])]
    script: list[ScriptItem] = [
        answer("v1"),
        answer("not json"),
        answer("v2"),
        json_answer({"approved": True, "feedback": ""}),
    ]
    outcome, _, llm = await run_blocks(blocks, script)
    assert (outcome.status, outcome.answer) == ("completed", "v2")
    assert "invalid verdict" in user_message(llm.calls[2])  # its error became the feedback


@pytest.mark.anyio
@pytest.mark.parametrize("rounds", [1, 5])
async def test_loop_round_cap(rounds: int) -> None:
    blocks = [loop_block("improve", [model_block("gen")], max_rounds=rounds), model_block("after")]
    script: list[ScriptItem] = []
    for i in range(rounds):
        script += [answer(f"v{i}"), json_answer({"approved": False, "feedback": "again"})]
    outcome, spans, _ = await run_blocks(blocks, script)
    assert (outcome.status, outcome.answer) == ("max_iterations", f"v{rounds - 1}")
    assert end_from(spans) == ["improve"]


@pytest.mark.anyio
async def test_loop_with_check_exit() -> None:
    blocks = [loop_block("until", [model_block("gen")], exit="check", check={"rule": "valid_json"})]
    outcome, _, llm = await run_blocks(blocks, [answer("nope"), answer('{"ok": true}')])
    assert (outcome.status, outcome.answer) == ("completed", '{"ok": true}')
    assert len(llm.calls) == 2  # the failed check sent the body round again


@pytest.mark.anyio
async def test_stop_inside_a_nested_container() -> None:
    inner = [model_block("gen"), check_block("short", "max_words", 1)]
    blocks = [branches_block("p", {"a": [loop_block("l", inner)]}), model_block("never")]
    outcome, spans, llm = await run_blocks(blocks, [answer("far too many words")])
    assert outcome.status == "error" and end_from(spans) == ["short"]
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_answer_on_last_call_offers_no_tools() -> None:
    blocks = [
        model_block("handler", tools=["calculator"], max_iterations=2, answer_on_last_call=True)
    ]
    script = [
        tool_call("calculator", '{"expression": "2"}'),
        tool_call("calculator", '{"expression": "3"}'),
    ]
    outcome, spans, llm = await run_blocks(blocks, script)
    assert outcome.status == "completed"  # the second call could not run a tool
    assert [bool(r["tools"]) for r in llm.requests] == [True, False]
    assert len([s for s in spans if s.kind == "tool"]) == 1


def test_ungranted_tool_scopes_rejected() -> None:
    saved = dict(catalog.TOOLS)
    catalog.TOOLS["calculator"] = replace(CALCULATOR, scopes=frozenset({"fs:read"}))
    try:
        config = blocks_config(model_block("a"), tool_block("calc"))
        with pytest.raises(ValueError, match="ungranted scopes"):
            BlockAgent(llm=FakeLLM([]), config=config, tracer=make_tracer()[0])
        granted = frozenset({"fs:read"})
        BlockAgent(llm=FakeLLM([]), config=config, tracer=make_tracer()[0], granted_scopes=granted)
    finally:
        catalog.TOOLS.clear()
        catalog.TOOLS.update(saved)
