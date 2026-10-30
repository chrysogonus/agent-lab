"""Start a run and wire its spans to the store and the live bus."""

import logging
import time
import uuid

from pydantic import BaseModel

from agent_lab.agents.registry import AGENTS, AgentSpec, validate_config
from agent_lab.agents.steps import config_version
from agent_lab.bus import Bus
from agent_lab.llm.base import LLMClient
from agent_lab.store import Run, RunStatus, Store
from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span
from agent_lab.tracing.tracer import Tracer

log = logging.getLogger(__name__)


class UnknownAgent(Exception):
    pass


def resolve(agent_id: str, store: Store, llm: LLMClient) -> tuple[AgentSpec, BaseModel, str]:
    """A template, or a custom agent as (its template, its validated config, its name)."""
    if agent_id in AGENTS:
        spec = AGENTS[agent_id]
        return spec, spec.make_config(llm), spec.name
    agent = store.get_agent(agent_id)
    if agent is None:
        raise UnknownAgent(agent_id)
    config = validate_config(agent.template_id, agent.config, llm.model)
    return AGENTS[agent.template_id], config, agent.name


def new_run(
    prompt: str, agent_id: str, llm: LLMClient, store: Store, secrets: tuple[str, ...] = ()
) -> tuple[Run, BaseModel, AgentSpec]:
    spec, config, name = resolve(agent_id, store, llm)
    run = Run(
        run_id=uuid.uuid4().hex,
        agent_id=agent_id,
        config_version=config_version(config),
        prompt=redact(prompt, secrets),
        status="running",
        graph=spec.graph(config),
        config=redact(config.model_dump(), secrets),
        started_at=time.time(),
        agent_name=name,
        template_id=spec.id,
    )
    return run, config, spec


async def execute_run(
    *,
    run: Run,
    prompt: str,
    config: BaseModel,
    spec: AgentSpec,
    llm: LLMClient,
    store: Store,
    bus: Bus,
    secrets: tuple[str, ...] = (),
) -> None:
    def sink(event: str, span: Span) -> None:
        store.save_span(span)
        bus.publish(run.run_id, {"type": event, "span": span.model_dump(mode="json")})

    tracer = Tracer(
        run_id=run.run_id,
        agent_id=run.agent_id,
        config_version=run.config_version,
        sink=sink,
        secrets=secrets,
    )
    agent = spec.create(llm, config, tracer)
    status: RunStatus = "error"
    answer: str | None = None
    try:
        result = await agent.run(prompt)
        status, answer = result.status, result.answer
    except Exception:
        # Already recorded on the open spans; keep the server alive for the next run.
        log.exception("run %s failed", run.run_id)
    store.finish_run(run.run_id, status, redact(answer, secrets), time.time())
    finished = store.get_run(run.run_id)
    assert finished is not None
    bus.publish(run.run_id, {"type": "run_ended", "run": finished.model_dump(mode="json")})
