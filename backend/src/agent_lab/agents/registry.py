"""Every runnable agent and workflow by id; `POST /runs` picks one with `agent_id`."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from agent_lab.agents import react
from agent_lab.graph import Graph
from agent_lab.llm.base import LLMClient
from agent_lab.store import RunStatus
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER
from agent_lab.tracing.tracer import Tracer
from agent_lab.workflows import chain, evaluator, orchestrator, parallel, routing

REACT_TOOLS = [CALCULATOR, WEATHER]


class Result(Protocol):
    status: RunStatus
    answer: str | None


class Runnable(Protocol):
    async def run(self, prompt: str) -> Result: ...


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    description: str
    sample_prompt: str
    make_config: Callable[[LLMClient], BaseModel]
    # Config is each agent's own model; Any keeps these callables assignable.
    graph: Callable[[Any], Graph]
    create: Callable[[LLMClient, Any, Tracer], Runnable]


_SPECS = [
    AgentSpec(
        id=react.AGENT_ID,
        name="ReAct agent",
        description="Reason, call tools, read their results and repeat until it can answer.",
        sample_prompt="What is 17*23 plus the current temperature in Berlin?",
        make_config=lambda llm: react.ReActConfig(
            model=llm.model, tools=[t.name for t in REACT_TOOLS]
        ),
        graph=lambda config: react.build_graph(config.tools),
        create=lambda llm, config, tracer: react.ReActAgent(
            llm=llm, tools=REACT_TOOLS, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=chain.AGENT_ID,
        name=chain.NAME,
        description=chain.DESCRIPTION,
        sample_prompt=chain.SAMPLE_PROMPT,
        make_config=lambda llm: chain.Config(model=llm.model),
        graph=lambda config: chain.build_graph(),
        create=lambda llm, config, tracer: chain.ChainWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=routing.AGENT_ID,
        name=routing.NAME,
        description=routing.DESCRIPTION,
        sample_prompt=routing.SAMPLE_PROMPT,
        make_config=lambda llm: routing.Config(model=llm.model),
        graph=lambda config: routing.build_graph(),
        create=lambda llm, config, tracer: routing.RoutingWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=parallel.AGENT_ID,
        name=parallel.NAME,
        description=parallel.DESCRIPTION,
        sample_prompt=parallel.SAMPLE_PROMPT,
        make_config=lambda llm: parallel.Config(model=llm.model),
        graph=parallel.build_graph,
        create=lambda llm, config, tracer: parallel.ParallelWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=orchestrator.AGENT_ID,
        name=orchestrator.NAME,
        description=orchestrator.DESCRIPTION,
        sample_prompt=orchestrator.SAMPLE_PROMPT,
        make_config=lambda llm: orchestrator.Config(model=llm.model),
        graph=lambda config: orchestrator.build_graph(),
        create=lambda llm, config, tracer: orchestrator.OrchestratorWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=evaluator.AGENT_ID,
        name=evaluator.NAME,
        description=evaluator.DESCRIPTION,
        sample_prompt=evaluator.SAMPLE_PROMPT,
        make_config=lambda llm: evaluator.Config(model=llm.model),
        graph=lambda config: evaluator.build_graph(),
        create=lambda llm, config, tracer: evaluator.EvaluatorWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
]

AGENTS: dict[str, AgentSpec] = {spec.id: spec for spec in _SPECS}
