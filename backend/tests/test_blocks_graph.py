"""The graph derived from blocks: nodes, edges and layout per kind (FR-011, SC-006)."""

import time

from helpers import (
    BlockDict,
    blocks_config,
    branches_block,
    check_block,
    loop_block,
    model_block,
    per_item_block,
    router_block,
    tool_block,
)

from agent_lab.blocks.graph import build_graph
from agent_lab.blocks.model import layout_errors
from agent_lab.graph import Graph


def graph(*blocks: BlockDict) -> Graph:
    built = build_graph(blocks_config(*blocks))
    ids = [n.id for n in built.nodes]
    assert len(ids) == len(set(ids))
    assert {e.source for e in built.edges} | {e.target for e in built.edges} <= set(ids)
    return built


def edges(g: Graph) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in g.edges}


def kinds(g: Graph) -> dict[str, str]:
    return {n.id: n.kind for n in g.nodes}


# --- US1: sequences ---


def test_one_block() -> None:
    g = graph(model_block("answer"))
    assert kinds(g) == {"start": "start", "answer": "llm", "end": "end"}
    assert edges(g) == {("start", "answer"), ("answer", "end")}
    assert [n.x for n in g.nodes] == [0, 200, 400]


def test_model_tool_model() -> None:
    g = graph(model_block("expr"), tool_block("calc"), model_block("explain"))
    assert kinds(g)["calc"] == "tool"
    assert edges(g) == {
        ("start", "expr"),
        ("expr", "calc"),
        ("calc", "explain"),
        ("explain", "end"),
    }
    assert next(n for n in g.nodes if n.id == "calc").label == "calc (calculator)"


def test_model_with_tools_has_tool_nodes_and_a_cap_edge() -> None:
    g = graph(model_block("agent", tools=["calculator", "get_weather"]), model_block("say"))
    assert kinds(g)["tool:calculator"] == kinds(g)["tool:get_weather"] == "tool"
    assert {
        ("agent", "tool:calculator"),
        ("tool:calculator", "agent"),
        ("agent", "tool:get_weather"),
        ("tool:get_weather", "agent"),
        ("agent", "end"),  # the iteration cap stops the run here
        ("agent", "say"),
    } <= edges(g)
    tool = next(n for n in g.nodes if n.id == "tool:calculator")
    agent = next(n for n in g.nodes if n.id == "agent")
    assert tool.y > agent.y  # tools sit below their model


def test_shared_tool_is_one_node() -> None:
    g = graph(model_block("a", tools=["calculator"]), model_block("b", tools=["calculator"]))
    assert [n.id for n in g.nodes].count("tool:calculator") == 1
    assert {("a", "tool:calculator"), ("b", "tool:calculator")} <= edges(g)


# --- US2: control blocks ---


def test_check_has_a_failure_edge() -> None:
    g = graph(model_block("draft"), check_block("enough"), model_block("polish"))
    assert kinds(g)["enough"] == "code"
    assert {("draft", "enough"), ("enough", "polish"), ("enough", "end")} <= edges(g)


def test_router() -> None:
    g = graph(
        router_block(
            "route", {"math": [model_block("m"), tool_block("calc")], "other": [model_block("o")]}
        ),
        model_block("say"),
    )
    assert kinds(g)["route"] == "llm"
    assert edges(g) == {
        ("start", "route"),
        ("route", "m"),
        ("m", "calc"),
        ("route", "o"),
        ("calc", "say"),
        ("o", "say"),
        ("say", "end"),
    }
    y = {n.id: n.y for n in g.nodes}
    assert y["m"] != y["o"]  # routes stack in rows


def test_parallel_branches_have_no_node_of_their_own() -> None:
    g = graph(
        model_block("first"),
        branches_block("reviews", {"a": [model_block("ra")], "b": [model_block("rb")]}),
        model_block("merge"),
    )
    assert "reviews" not in kinds(g)
    assert edges(g) == {
        ("start", "first"),
        ("first", "ra"),
        ("first", "rb"),
        ("ra", "merge"),
        ("rb", "merge"),
        ("merge", "end"),
    }


def test_per_item_planner() -> None:
    g = graph(per_item_block("plan", [model_block("work")]), model_block("sum"))
    assert kinds(g)["plan"] == "llm"
    assert edges(g) == {
        ("start", "plan"),
        ("plan", "work"),
        ("plan", "end"),  # unusable plan
        ("work", "sum"),
        ("sum", "end"),
    }


def test_loop_with_judge_and_with_check() -> None:
    judged = graph(loop_block("improve", [model_block("gen")]), model_block("say"))
    assert kinds(judged)["improve"] == "llm"
    assert edges(judged) == {
        ("start", "gen"),
        ("gen", "improve"),
        ("improve", "gen"),  # another round
        ("improve", "say"),
        ("improve", "end"),  # round cap
        ("say", "end"),
    }
    checked = graph(
        loop_block("until", [model_block("gen")], exit="check", check={"rule": "valid_json"})
    )
    assert kinds(checked)["until"] == "code"


def test_three_levels() -> None:
    g = graph(
        branches_block("p", {"a": [loop_block("l", [model_block("m")])], "b": [model_block("x")]})
    )
    assert {
        ("start", "m"),
        ("start", "x"),
        ("m", "l"),
        ("l", "m"),
        ("l", "end"),
        ("x", "end"),
    } <= edges(g)


def big_layout() -> list[BlockDict]:
    """30 blocks, 3 levels deep."""

    def inner(prefix: str) -> list[BlockDict]:
        return [
            loop_block(f"{prefix}-loop", [model_block(f"{prefix}-m1"), model_block(f"{prefix}-m2")])
        ]

    group = branches_block("group", {f"b{i}": inner(f"b{i}") for i in range(6)})  # 1 + 6 * 3 blocks
    return [group, *(model_block(f"tail-{i}") for i in range(11))]


def test_largest_layout_builds_quickly() -> None:
    config = blocks_config(*big_layout())
    assert layout_errors(config) == []  # exactly at the limits
    start = time.perf_counter()
    built = build_graph(config)
    assert time.perf_counter() - start < 1  # SC-006 (the preview adds only an HTTP round trip)
    assert len([n for n in built.nodes if n.kind != "start" and n.kind != "end"]) == 29
