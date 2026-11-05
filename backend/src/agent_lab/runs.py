"""Start a run and wire its spans to the store and the live bus."""

import asyncio
import logging
import time
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from agent_lab.agents.registry import AGENTS, KINDS, AgentSpec, model_of, validate_config
from agent_lab.agents.steps import config_version
from agent_lab.bus import Bus
from agent_lab.harness.guard import RunGuard, current_guard
from agent_lab.llm.base import LLMClient
from agent_lab.llm.models import ModelRef, Models
from agent_lab.mcp.host import HostTool
from agent_lab.store import Run, RunStatus, Store
from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span
from agent_lab.tracing.tracer import Tracer

log = logging.getLogger(__name__)


class UnknownAgent(Exception):
    pass


def resolve(
    agent_id: str, store: Store, models: Models, model: ModelRef | None = None
) -> tuple[AgentSpec, BaseModel, str, LLMClient]:
    """(template, validated config, name, client of the config's model) for an agent id.

    `model` replaces the config's. Raises `UnknownAgent`, or `UnavailableModel` for a model that
    cannot be used.
    """
    stored: dict[str, Any]
    if agent_id in AGENTS:
        spec, stored, name = AGENTS[agent_id], {}, AGENTS[agent_id].name
    else:
        agent = store.get_agent(agent_id)
        if agent is None:
            raise UnknownAgent(agent_id)
        spec, stored, name = KINDS[agent.template_id], agent.config, agent.name
    if model is not None:
        stored = {**stored, "model": model.model, "provider": model.provider}
    config = validate_config(spec.id, stored, models.default)
    client = models.client(model_of(config))
    return spec, config, name, client


def new_run(
    prompt: str,
    agent_id: str,
    models: Models,
    store: Store,
    secrets: tuple[str, ...] = (),
    *,
    village_tick: int | None = None,
    villager: str | None = None,
    eval_id: str | None = None,
    model: ModelRef | None = None,
) -> tuple[Run, BaseModel, AgentSpec, LLMClient]:
    spec, config, name, client = resolve(agent_id, store, models, model)
    run = build_run(
        prompt,
        agent_id,
        spec,
        config,
        name,
        secrets,
        village_tick=village_tick,
        villager=villager,
        eval_id=eval_id,
    )
    return run, config, spec, client


def build_run(
    prompt: str,
    agent_id: str,
    spec: AgentSpec,
    config: BaseModel,
    name: str,
    secrets: tuple[str, ...] = (),
    *,
    village_tick: int | None = None,
    villager: str | None = None,
    eval_id: str | None = None,
) -> Run:
    """A run record from a validated config, such as an evaluation's copy."""
    return Run(
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
        village_tick=village_tick,
        villager=villager,
        eval_id=eval_id,
    )


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
    tools: Mapping[str, HostTool] | None = None,
    guard: RunGuard | None = None,
) -> None:
    """`tools` are the config's tools, resolved by the host (`registry.config_tools`).

    `guard` holds the run's limits; the village passes none, so nothing limits its runs (FR-023).
    """

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
    status: RunStatus = "error"
    answer: str | None = None
    stop_reason: str | None = None
    token = current_guard.set(guard)  # also to None: a village run never inherits a guard
    try:
        agent = spec.create(llm, config, tracer, tools or {})
        result = await agent.run(prompt)
        status, answer = result.status, result.answer
    except asyncio.CancelledError:
        if guard is None or not guard.stop_requested:
            raise  # not the owner's Stop: a shutting-down server must see its task end
        task = asyncio.current_task()
        assert task is not None
        task.uncancel()
        status, answer, stop_reason = "stopped", guard.last_text, "stopped by the owner"
    except Exception:
        # Already recorded on the open spans; keep the server alive for the next run.
        log.exception("run %s failed", run.run_id)
    finally:
        current_guard.reset(token)
    store.finish_run(
        run.run_id, status, redact(answer, secrets), tracer.now(), stop_reason=stop_reason
    )
    finished = store.get_run(run.run_id)
    assert finished is not None
    bus.publish(run.run_id, {"type": "run_ended", "run": finished.model_dump(mode="json")})
