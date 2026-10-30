"""Shared builders for scripted runs."""

import json
from typing import Any

from agent_lab.agents.react import ReActAgent, ReActConfig
from agent_lab.agents.steps import StepContext, config_version
from agent_lab.graph import Graph
from agent_lab.llm.base import ChatResponse, ToolCall
from agent_lab.llm.fake import FakeLLM
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER
from agent_lab.tracing.span import Span
from agent_lab.tracing.tracer import Tracer

TOOLS = [CALCULATOR, WEATHER]


def tool_call(name: str, arguments: str, call_id: str = "c1") -> ChatResponse:
    return ChatResponse(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        tokens_in=10,
        tokens_out=5,
    )


def answer(text: str) -> ChatResponse:
    return ChatResponse(content=text, tokens_in=20, tokens_out=3)


def make_agent(llm: FakeLLM, max_iterations: int = 6) -> tuple[ReActAgent, list[tuple[str, Span]]]:
    events: list[tuple[str, Span]] = []
    config = ReActConfig(
        model=llm.model, tools=[t.name for t in TOOLS], max_iterations=max_iterations
    )
    tracer = Tracer(
        run_id="run-1",
        agent_id="react",
        config_version=config_version(config),
        sink=lambda event, span: events.append((event, span)),
    )
    return ReActAgent(llm=llm, tools=TOOLS, config=config, tracer=tracer), events


def ended(events: list[tuple[str, Span]]) -> list[Span]:
    """Final state of every span, in start order."""
    final = {s.span_id: s for e, s in events if e == "span_ended"}
    order = [s.span_id for e, s in events if e == "span_started"]
    return [final[i] for i in order]


def json_answer(obj: Any) -> ChatResponse:
    """A structured-output reply, as the model returns it for a decision."""
    return answer(json.dumps(obj))


def make_tracer(agent_id: str = "test") -> tuple[Tracer, list[tuple[str, Span]]]:
    events: list[tuple[str, Span]] = []
    tracer = Tracer(
        run_id="run-1",
        agent_id=agent_id,
        config_version="v1",
        sink=lambda event, span: events.append((event, span)),
    )
    return tracer, events


def make_ctx(llm: FakeLLM, reasoning: bool = False) -> tuple[StepContext, list[tuple[str, Span]]]:
    tracer, events = make_tracer()
    return StepContext(llm=llm, tracer=tracer, reasoning=reasoning), events


def taken_edges(spans: list[Span]) -> set[tuple[str, str]]:
    """Edges recorded by `lab.came_from`."""
    return {(src, s.node_id) for s in spans for src in s.attributes.get("lab.came_from", [])}


def assert_trace_valid(graph: Graph, spans: list[Span]) -> None:
    """Every span is on a declared node and every recorded edge is declared (SC-002)."""
    nodes = graph.node_ids()
    assert {s.node_id for s in spans} <= nodes
    declared = {(e.source, e.target) for e in graph.edges}
    assert taken_edges(spans) <= declared, taken_edges(spans) - declared
