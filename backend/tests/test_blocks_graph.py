"""The graph derived from blocks: nodes, edges and layout per kind (FR-011, SC-006)."""

from helpers import BlockDict, blocks_config, model_block, tool_block

from agent_lab.blocks.graph import build_graph
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
