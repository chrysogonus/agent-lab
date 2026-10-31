"""The graph of a block agent, derived from its blocks (research.md §6)."""

from typing import Literal

from agent_lab.blocks.model import (
    Block,
    BlocksConfig,
    CheckBlock,
    LoopBlock,
    ModelBlock,
    ParallelBlock,
    RouterBlock,
    ToolBlock,
    children,
)
from agent_lab.graph import Edge, Graph, Node

COLUMN, ROW = 200, 110
NodeKind = Literal["start", "llm", "tool", "code", "end"]


def entries(block: Block) -> list[str]:
    """The nodes a block starts at."""
    if isinstance(block, ParallelBlock) and block.mode == "branches":
        return [n for _, blocks in children(block) for n in entries(blocks[0])]
    if isinstance(block, LoopBlock):
        return entries(block.body[0])
    return [block.name]


def exits(block: Block) -> list[str]:
    """The nodes a block can end at, which the next block is reached from."""
    if isinstance(block, RouterBlock | ParallelBlock):
        return [n for _, blocks in children(block) for n in exits(blocks[-1])]
    return [block.name]  # a loop ends at its exit node


def _size(block: Block) -> tuple[float, float]:
    """Width and height in grid cells."""
    if isinstance(block, ModelBlock):
        return 1, 2 if block.tools else 1
    lists = [_list_size(blocks) for _, blocks in children(block)]
    if isinstance(block, RouterBlock):
        return 1 + max(w for w, _ in lists), sum(h for _, h in lists)
    if isinstance(block, ParallelBlock):
        if block.mode == "branches":
            return max(w for w, _ in lists), sum(h for _, h in lists)
        return 1 + lists[0][0], lists[0][1]
    if isinstance(block, LoopBlock):
        return lists[0][0] + 1, lists[0][1]
    return 1, 1


def _list_size(blocks: list[Block]) -> tuple[float, float]:
    sizes = [_size(b) for b in blocks]
    return sum(w for w, _ in sizes), max(h for _, h in sizes)


def _label(block: Block) -> tuple[NodeKind, str]:
    """(node kind, label) of a block's own node."""
    if isinstance(block, ToolBlock):
        return "tool", f"{block.name} ({block.tool})"
    if isinstance(block, CheckBlock):
        return "code", f"{block.name} (check)"
    if isinstance(block, RouterBlock):
        return "llm", f"{block.name} (router)"
    if isinstance(block, ParallelBlock):
        return "llm", f"{block.name} (planner)"
    if isinstance(block, LoopBlock):
        return (
            ("llm", f"{block.name} (judge)")
            if block.exit == "judge"
            else (
                "code",
                f"{block.name} (check)",
            )
        )
    return "llm", f"{block.name} (LLM)"


def build_graph(config: BlocksConfig) -> Graph:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    def node(node_id: str, kind: NodeKind, label: str, x: float, y: float) -> None:
        if node_id not in nodes:  # a tool shared by two model calls is one node
            nodes[node_id] = Node(id=node_id, label=label, kind=kind, x=x * COLUMN, y=y * ROW)

    def edge(source: str, target: str) -> None:
        if Edge(source=source, target=target) not in edges:
            edges.append(Edge(source=source, target=target))

    def place_list(blocks: list[Block], x: float, y: float, height: float) -> None:
        for block in blocks:
            width, own = _size(block)
            place(block, x, y + (height - own) / 2)
            x += width

    def place(block: Block, x: float, y: float) -> None:
        height = _size(block)[1]
        if isinstance(block, ModelBlock):
            node(block.name, "llm", f"{block.name} (LLM)", x, y)
            for i, tool in enumerate(block.tools):
                node(f"tool:{tool}", "tool", tool, x + i * 0.6, y + 1)
            return
        lists = children(block)
        kind, label = _label(block)
        if isinstance(block, RouterBlock | ParallelBlock):
            stacked = isinstance(block, RouterBlock) or block.mode == "branches"
            first = 0 if isinstance(block, ParallelBlock) and block.mode == "branches" else 1
            if first:
                node(block.name, kind, label, x, y + (height - 1) / 2)
            row = y
            for _, blocks in lists:
                w, h = _list_size(blocks)
                place_list(blocks, x + first, row if stacked else y, h)
                row += h
            return
        if isinstance(block, LoopBlock):
            w, h = _list_size(block.body)
            place_list(block.body, x, y, h)
            node(block.name, kind, label, x + w, y + (height - 1) / 2)
            return
        node(block.name, kind, label, x, y)

    def wire_list(blocks: list[Block], came: list[str]) -> list[str]:
        for block in blocks:
            for source in came:
                for target in entries(block):
                    edge(source, target)
            wire(block)
            came = exits(block)
        return came

    def wire(block: Block) -> None:
        if isinstance(block, ModelBlock) and block.tools:
            for tool in block.tools:
                edge(block.name, f"tool:{tool}")
                edge(f"tool:{tool}", block.name)
            edge(block.name, "end")  # iteration cap
        elif isinstance(block, CheckBlock):
            edge(block.name, "end")  # failed check
        elif isinstance(block, RouterBlock):
            for route in block.routes:
                wire_list(route.blocks, [block.name])
        elif isinstance(block, ParallelBlock):
            if block.mode == "branches":
                for branch in block.branches or []:
                    wire_list(branch.blocks, [])  # entered from the blocks before the group
            else:
                wire_list(block.body or [], [block.name])
                edge(block.name, "end")  # unusable plan
        elif isinstance(block, LoopBlock):
            for source in wire_list(block.body, []):
                edge(source, block.name)
            for target in entries(block.body[0]):
                edge(block.name, target)  # another round
            edge(block.name, "end")  # round cap

    width, height = _list_size(config.blocks)
    node("start", "start", "start", 0, (height - 1) / 2)
    place_list(config.blocks, 1, 0, height)
    node("end", "end", "end", 1 + width, (height - 1) / 2)
    for source in wire_list(config.blocks, ["start"]):
        edge(source, "end")
    return Graph(nodes=list(nodes.values()), edges=edges)
