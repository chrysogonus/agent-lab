"""Shared builders for scripted runs."""

import json
from typing import Any

from agent_lab.agents.react import ReActAgent, ReActConfig
from agent_lab.agents.steps import StepContext, config_version
from agent_lab.blocks.model import BlocksConfig
from agent_lab.graph import Graph
from agent_lab.llm.base import ChatResponse, ToolCall
from agent_lab.llm.fake import FakeLLM
from agent_lab.llm.models import ModelEntry, ModelRef, Models
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


def fake_models(
    local: FakeLLM,
    openai: FakeLLM | None = None,
    *,
    openai_key: bool = True,
    default: ModelRef | None = None,
) -> Models:
    """A catalog of fake models: `local` (the default unless given) and optionally `openai`."""
    local.provider = "local"  # spans report the provider as in production
    entries = [ModelEntry(ModelRef(provider="local", model=local.model), False, None, local)]
    if openai is not None:
        openai.provider = "openai"
        unavailable = None if openai_key else "no API key"
        ref = ModelRef(provider="openai", model=openai.model)
        entries.append(ModelEntry(ref, True, unavailable, openai))
    return Models(entries, default or entries[0].ref)


# --- Block agents (M5): dict builders, as the API receives blocks ---

BlockDict = dict[str, Any]


def model_block(name: str, system: str = "You help.", **fields: Any) -> BlockDict:
    return {"kind": "model", "name": name, "system": system, **fields}


def tool_block(name: str, tool: str = "calculator", **arguments: str) -> BlockDict:
    arguments = arguments or {"expression": "{previous}"}
    return {"kind": "tool", "name": name, "tool": tool, "arguments": arguments}


def check_block(name: str, rule: str = "min_bullets", value: Any = 3) -> BlockDict:
    return {"kind": "check", "name": name, "rule": rule, "value": value}


def router_block(
    name: str, routes: dict[str, list[BlockDict]], fallback: str | None = None, **fields: Any
) -> BlockDict:
    return {
        "kind": "router",
        "name": name,
        "prompt": "Classify the question.",
        "routes": [
            {"name": r, "description": f"{r} questions", "blocks": b} for r, b in routes.items()
        ],
        "fallback": fallback or list(routes)[-1],
        **fields,
    }


def branches_block(name: str, branches: dict[str, list[BlockDict]]) -> BlockDict:
    branch_list = [{"name": b, "blocks": blocks} for b, blocks in branches.items()]
    return {"kind": "parallel", "name": name, "mode": "branches", "branches": branch_list}


def per_item_block(name: str, body: list[BlockDict], max_items: int = 3) -> BlockDict:
    return {
        "kind": "parallel",
        "name": name,
        "mode": "per_item",
        "planner": "Split the request into parts.",
        "max_items": max_items,
        "body": body,
    }


def loop_block(name: str, body: list[BlockDict], max_rounds: int = 3, **exit: Any) -> BlockDict:
    exit = exit or {"exit": "judge", "judge": "Approve if good."}
    return {"kind": "loop", "name": name, "body": body, "max_rounds": max_rounds, **exit}


def blocks_config(*blocks: BlockDict, reasoning: bool = False) -> BlocksConfig:
    return BlocksConfig.model_validate(
        {"model": "fake-model", "reasoning": reasoning, "blocks": list(blocks)}
    )
