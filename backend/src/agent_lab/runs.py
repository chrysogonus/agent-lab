"""Start a run and wire its spans to the store and the live bus."""

import logging
import time
import uuid

from agent_lab.agents.react import AGENT_ID, ReActAgent, ReActConfig, build_graph, config_version
from agent_lab.bus import Bus
from agent_lab.llm.base import LLMClient
from agent_lab.store import Run, RunStatus, Store
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER
from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span
from agent_lab.tracing.tracer import Tracer

log = logging.getLogger(__name__)

TOOLS = [CALCULATOR, WEATHER]


def new_run(prompt: str, llm: LLMClient, secrets: tuple[str, ...] = ()) -> tuple[Run, ReActConfig]:
    config = ReActConfig(model=llm.model, tools=[t.name for t in TOOLS])
    run = Run(
        run_id=uuid.uuid4().hex,
        agent_id=AGENT_ID,
        config_version=config_version(config),
        prompt=redact(prompt, secrets),
        status="running",
        graph=build_graph(config.tools),
        config=config.model_dump(),
        started_at=time.time(),
    )
    return run, config


async def execute_run(
    *,
    run: Run,
    prompt: str,
    config: ReActConfig,
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
    agent = ReActAgent(llm=llm, tools=TOOLS, config=config, tracer=tracer)
    status: RunStatus = "error"
    answer: str | None = None
    try:
        state = await agent.run(prompt)
        status, answer = state.status, state.answer
    except Exception:
        # Already recorded on the open spans; keep the server alive for the next run.
        log.exception("run %s failed", run.run_id)
    store.finish_run(run.run_id, status, redact(answer, secrets), time.time())
    finished = store.get_run(run.run_id)
    assert finished is not None
    bus.publish(run.run_id, {"type": "run_ended", "run": finished.model_dump(mode="json")})
