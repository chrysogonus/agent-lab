"""Every runnable agent and workflow by id; `POST /runs` picks one with `agent_id`."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from agent_lab.agents import react
from agent_lab.agents.config_fields import LOCAL
from agent_lab.blocks.graph import build_graph as blocks_graph
from agent_lab.blocks.model import BlocksConfig, LayoutError, layout_errors
from agent_lab.blocks.run import BlockAgent
from agent_lab.graph import Graph
from agent_lab.llm.base import LLMClient
from agent_lab.llm.models import ModelRef
from agent_lab.store import RunStatus
from agent_lab.tools.catalog import TOOLS
from agent_lab.tracing.tracer import Tracer
from agent_lab.workflows import chain, evaluator, orchestrator, parallel, routing


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
    config_model: type[BaseModel]  # the shape, its defaults (the template) and limits
    # Config is each agent's own model; Any keeps these callables assignable.
    graph: Callable[[Any], Graph]
    create: Callable[[LLMClient, Any, Tracer], Runnable]


_SPECS = [
    AgentSpec(
        id=react.AGENT_ID,
        name="ReAct agent",
        description="Reason, call tools, read their results and repeat until it can answer.",
        sample_prompt="What is 17*23 plus the current temperature in Berlin?",
        config_model=react.ReActConfig,
        graph=lambda config: react.build_graph(config.tools),
        create=lambda llm, config, tracer: react.ReActAgent(
            llm=llm, tools=[TOOLS[t] for t in config.tools], config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=chain.AGENT_ID,
        name=chain.NAME,
        description=chain.DESCRIPTION,
        sample_prompt=chain.SAMPLE_PROMPT,
        config_model=chain.Config,
        graph=chain.build_graph,
        create=lambda llm, config, tracer: chain.ChainWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=routing.AGENT_ID,
        name=routing.NAME,
        description=routing.DESCRIPTION,
        sample_prompt=routing.SAMPLE_PROMPT,
        config_model=routing.Config,
        graph=routing.build_graph,
        create=lambda llm, config, tracer: routing.RoutingWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
    AgentSpec(
        id=parallel.AGENT_ID,
        name=parallel.NAME,
        description=parallel.DESCRIPTION,
        sample_prompt=parallel.SAMPLE_PROMPT,
        config_model=parallel.Config,
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
        config_model=orchestrator.Config,
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
        config_model=evaluator.Config,
        graph=lambda config: evaluator.build_graph(),
        create=lambda llm, config, tracer: evaluator.EvaluatorWorkflow(
            llm=llm, config=config, tracer=tracer
        ),
    ),
]

AGENTS: dict[str, AgentSpec] = {spec.id: spec for spec in _SPECS}

# Not a template: block agents are custom agents of this kind (specs/005-block-builder).
BLOCKS = AgentSpec(
    id="blocks",
    name="Block agent",
    description="An agent built from blocks: model calls, tools, checks, routers, groups, loops.",
    sample_prompt="What is 17 times 23?",
    config_model=BlocksConfig,
    graph=blocks_graph,
    create=lambda llm, config, tracer: BlockAgent(llm=llm, config=config, tracer=tracer),
)
KINDS: dict[str, AgentSpec] = {**AGENTS, BLOCKS.id: BLOCKS}  # what a custom agent can be


def validate_config(template_id: str, stored: dict[str, Any], default: ModelRef) -> BaseModel:
    """A template (`stored` empty) or custom agent config; without a pinned model, the default."""
    fields = {"model": default.model, "provider": default.provider, **stored}
    config = KINDS[template_id].config_model.model_validate(fields)
    if isinstance(config, BlocksConfig) and (errors := layout_errors(config)):
        raise LayoutError(errors)
    return config


def editable(config: BaseModel) -> dict[str, Any]:
    """The fields the builder edits: everything but the model."""
    return config.model_dump(exclude={"model", "provider"})


def pinned(stored: dict[str, Any]) -> ModelRef | None:
    """The model a custom agent is pinned to; None means it follows the default."""
    if "model" not in stored:
        return None
    return ModelRef(provider=stored.get("provider", LOCAL), model=stored["model"])


def model_of(config: BaseModel) -> ModelRef:
    """The model a validated config runs on (its dump leaves out a local provider)."""
    ref = pinned(config.model_dump())
    assert ref is not None, "every config has a model"
    return ref
