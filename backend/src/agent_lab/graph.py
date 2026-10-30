"""Static agent graphs, declared as data (core contract 2)."""

from typing import Literal

from pydantic import BaseModel


class Node(BaseModel):
    id: str
    label: str
    kind: Literal["start", "llm", "tool", "code", "end"]  # code: a step without a model call
    # Hand-set layout for the UI, so no layout library is needed.
    x: float
    y: float


class Edge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}
