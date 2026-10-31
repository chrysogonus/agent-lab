"""The six templates as blocks behave like the templates on the same script (FR-013, SC-002)."""

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from helpers import answer, ended, json_answer, make_tracer, taken_edges, tool_call
from test_templates import CASES

from agent_lab.agents.registry import AGENTS, validate_config
from agent_lab.blocks.convert import to_blocks
from agent_lab.blocks.graph import build_graph
from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.blocks.run import BlockAgent
from agent_lab.graph import Graph
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelRef
from agent_lab.tracing.tracer import Tracer

DEFAULT = ModelRef(provider="local", model="fake-model")

# Malformed decisions on top of the golden cases (research.md §7).
EXTRA: dict[str, tuple[str, str, list[ScriptItem]]] = {
    "orchestrator-plan-too-long": (
        "orchestrator",
        "Plan a trip",
        [json_answer({"subtasks": [f"part {i}" for i in range(5)]})],  # the template allows 4
    ),
    "routing-tool-twice": (  # the handler's second call offers no tool: it answers
        "routing",
        "2**10?",
        [
            json_answer({"label": "math"}),
            tool_call("calculator", '{"expression": "2**10"}'),
            tool_call("calculator", '{"expression": "2**10"}'),
        ],
    ),
    "evaluator-unreadable-verdict": (
        "evaluator",
        "A lamp",
        [
            answer("Bright lamp"),
            answer("not a verdict"),
            answer("Lamp: light your way"),
            json_answer({"approved": True, "feedback": ""}),
        ],
    ),
}


def converted(template_id: str, stored: dict[str, Any] | None = None) -> tuple[Any, BlocksConfig]:
    template = validate_config(template_id, stored or {}, DEFAULT)
    blocks = BlocksConfig.model_validate(
        {"model": "fake-model", **to_blocks(template_id, template)}
    )
    assert layout_errors(blocks) == []
    return template, blocks


async def run(
    agent: Callable[[FakeLLM, Tracer], Any], script: Sequence[ScriptItem], prompt: str
) -> dict[str, Any]:
    llm = FakeLLM(list(script))
    tracer, events = make_tracer("custom-1")
    outcome = await agent(llm, tracer).run(prompt)
    spans = ended(events)
    return {
        "status": outcome.status,
        "answer": outcome.answer,
        "model_calls": len(llm.calls),
        "tool_calls": len([s for s in spans if s.kind == "tool"]),
        "edges": taken_edges(spans),
    }


def edge_set(graph: Graph) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in graph.edges}


def call_nodes(graph: Graph) -> set[str]:
    return {n.id for n in graph.nodes if n.kind in ("llm", "tool", "code")}


@pytest.mark.anyio
@pytest.mark.parametrize("case", [*CASES, *EXTRA])
async def test_converted_template_behaves_the_same(case: str) -> None:
    template_id, prompt, script = {**CASES, **EXTRA}[case]
    template, blocks = converted(template_id)
    spec = AGENTS[template_id]

    want = await run(lambda llm, tracer: spec.create(llm, template, tracer), script, prompt)
    got = await run(
        lambda llm, tracer: BlockAgent(llm=llm, config=blocks, tracer=tracer), script, prompt
    )

    assert got == want, case
    template_graph, blocks_graph = spec.graph(template), build_graph(blocks)
    assert call_nodes(blocks_graph) == call_nodes(template_graph)
    assert edge_set(blocks_graph) <= edge_set(template_graph)


def test_custom_agent_edits_are_kept() -> None:
    _, blocks = converted("routing", {"router_prompt": "Pick a desk.", "fallback": "math"})
    router = blocks.blocks[0]
    assert router.kind == "router" and router.prompt == "Pick a desk." and router.fallback == "math"


def test_reserved_step_name_is_renamed() -> None:
    steps = [{"name": "input", "prompt": "Outline."}, {"name": "draft", "prompt": "Draft."}]
    _, blocks = converted("chain", {"steps": steps, "gate": False})
    assert [b.name for b in blocks.blocks] == ["input-2", "draft"]


def test_aspect_named_reviews_moves_the_group() -> None:
    _, blocks = converted("parallel", {"aspects": {"reviews": "Are the reviews fair?"}})
    group, merge = blocks.blocks
    assert group.name == "reviews-2"
    assert merge.kind == "model" and "{reviews-2}" in merge.message


def test_model_and_reasoning_are_kept() -> None:
    template = validate_config("react", {}, ModelRef(provider="openai", model="gpt-6-luna"))
    assert to_blocks("react", template)["reasoning"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("outline", ["- a\n- b\n- c", "no bullets"])
async def test_single_step_chain_keeps_its_gate(outline: str) -> None:
    stored = {"steps": [{"name": "outline", "prompt": "Outline it."}], "gate": True}
    template, blocks = converted("chain", stored)
    want = await run(
        lambda llm, tracer: AGENTS["chain"].create(llm, template, tracer), [answer(outline)], "x"
    )
    got = await run(
        lambda llm, tracer: BlockAgent(llm=llm, config=blocks, tracer=tracer),
        [answer(outline)],
        "x",
    )
    assert got == want
    assert got["status"] == ("completed" if outline.startswith("-") else "error")


@pytest.mark.anyio
async def test_converted_judge_sees_the_request() -> None:
    _, blocks = converted("evaluator")
    llm = FakeLLM([answer("Bright lamp"), json_answer({"approved": True, "feedback": ""})])
    tracer, _ = make_tracer()
    await BlockAgent(llm=llm, config=blocks, tracer=tracer).run("A lamp called Glow")
    judge = llm.calls[1]
    assert (
        "Product: A lamp called Glow" in judge[0]["content"]
        and judge[1]["content"] == "Bright lamp"
    )
