"""HTTP and WebSocket API. Loopback only; see contracts/http-api.md."""

import asyncio
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from agent_lab.agents.registry import AGENTS, AgentSpec, editable, pinned, validate_config
from agent_lab.bus import Bus
from agent_lab.graph import Graph
from agent_lab.llm.models import LABELS, ModelRef, Models, UnavailableModel
from agent_lab.runs import UnknownAgent, execute_run, new_run
from agent_lab.store import CustomAgent, NameInUse, Run, Store
from agent_lab.tools.catalog import TOOLS
from agent_lab.tracing.span import Span

ALLOWED_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    agent_id: str = "react"  # a template id or a custom agent's id


class AgentInfo(BaseModel):
    id: str
    kind: Literal["template", "custom"]
    template_id: str
    name: str
    description: str
    sample_prompt: str
    config: dict[str, Any]  # the editable fields, without the model
    model: ModelRef | None  # None: follows the default model (templates always)
    graph: Graph


class ModelInfo(BaseModel):
    provider: str
    provider_label: str
    model: str
    external: bool
    available: bool
    unavailable_reason: str | None
    default: bool


class ToolInfo(BaseModel):
    name: str
    description: str


class AgentFields(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    sample_prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    config: dict[str, Any]
    model: ModelRef | None = None  # None: follow the default model


class NewAgent(AgentFields):
    template_id: str


class GraphRequest(BaseModel):
    template_id: str
    config: dict[str, Any]


class RunDetail(BaseModel):
    run: Run
    spans: list[Span]


def field_error(loc: tuple[str | int, ...], msg: str) -> RequestValidationError:
    """A 422 in FastAPI's own shape, so every rejection names its field the same way."""
    return RequestValidationError([{"loc": loc, "msg": msg, "type": "value_error"}])


def create_app(*, store: Store, models: Models, secrets: tuple[str, ...] = ()) -> FastAPI:
    app = FastAPI(title="Agent Lab")
    # Rejects DNS-rebinding requests that reach the loopback port under a foreign Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type"],
    )
    bus = Bus()
    tasks: set[asyncio.Task[None]] = set()  # strong refs so running runs are not collected

    def checked_config(template_id: str, raw: dict[str, Any]) -> BaseModel:
        """The template's model validates the config; the client never sets model or graph."""
        if template_id not in AGENTS:
            raise field_error(("body", "template_id"), f"unknown template {template_id!r}")
        for key in ("model", "provider"):
            if key in raw:
                raise field_error(("body", "config", key), "set the model with the model field")
        try:
            return validate_config(template_id, raw, models.default)
        except ValidationError as exc:
            errors = [
                {"loc": ("body", "config", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
            raise RequestValidationError(errors) from None

    def stored_config(config: BaseModel, model: ModelRef | None) -> dict[str, Any]:
        """What a custom agent stores: its editable fields, plus its model only when pinned."""
        if model is None:
            return editable(config)
        try:
            models.client(model)
        except UnavailableModel as exc:
            raise field_error(("body", "model"), str(exc)) from None
        return {**editable(config), "model": model.model, "provider": model.provider}

    def custom_info(agent: CustomAgent) -> AgentInfo:
        config = validate_config(agent.template_id, agent.config, models.default)
        return AgentInfo(
            id=agent.agent_id,
            kind="custom",
            template_id=agent.template_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config=editable(config),
            model=pinned(agent.config),
            graph=AGENTS[agent.template_id].graph(config),
        )

    def saved(agent: CustomAgent | None) -> AgentInfo:
        if agent is None:
            raise HTTPException(status_code=404, detail="unknown custom agent")
        return custom_info(agent)

    def template_info(spec: AgentSpec) -> AgentInfo:
        config = validate_config(spec.id, {}, models.default)
        return AgentInfo(
            id=spec.id,
            kind="template",
            template_id=spec.id,
            name=spec.name,
            description=spec.description,
            sample_prompt=spec.sample_prompt,
            config=editable(config),
            model=None,
            graph=spec.graph(config),
        )

    @app.get("/agents")
    async def list_agents() -> list[AgentInfo]:
        templates = [template_info(spec) for spec in AGENTS.values()]
        return templates + [custom_info(a) for a in store.list_agents()]

    @app.get("/models")
    async def list_models() -> list[ModelInfo]:
        return [
            ModelInfo(
                provider=e.ref.provider,
                provider_label=LABELS[e.ref.provider],
                model=e.ref.model,
                external=e.external,
                available=e.unavailable is None,
                unavailable_reason=e.unavailable,
                default=e.ref == models.default,
            )
            for e in models.entries
        ]

    @app.get("/tools")
    async def list_tools() -> list[ToolInfo]:
        return [ToolInfo(name=t.name, description=t.description) for t in TOOLS.values()]

    @app.post("/agents", status_code=status.HTTP_201_CREATED)
    async def create_agent(body: NewAgent) -> AgentInfo:
        config = checked_config(body.template_id, body.config)
        try:
            return saved(
                store.create_agent(
                    template_id=body.template_id,
                    name=body.name,
                    description=body.description,
                    sample_prompt=body.sample_prompt,
                    config=stored_config(config, body.model),
                )
            )
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None

    @app.put("/agents/{agent_id}")
    async def update_agent(agent_id: str, body: AgentFields) -> AgentInfo:
        current = store.get_agent(agent_id)  # templates are not stored: 404
        if current is None:
            raise HTTPException(status_code=404, detail="unknown custom agent")
        config = checked_config(current.template_id, body.config)
        try:
            return saved(
                store.update_agent(
                    agent_id,
                    name=body.name,
                    description=body.description,
                    sample_prompt=body.sample_prompt,
                    config=stored_config(config, body.model),
                )
            )
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None

    @app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_agent(agent_id: str) -> None:
        """Runs of the agent keep their own snapshot (name, config, graph) and stay listed."""
        if not store.delete_agent(agent_id):
            raise HTTPException(status_code=404, detail="unknown custom agent")

    @app.post("/graph")
    async def preview_graph(body: GraphRequest) -> Graph:
        """The graph the server derives from an unsaved config (the builder's live preview)."""
        return AGENTS[body.template_id].graph(checked_config(body.template_id, body.config))

    @app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(body: RunRequest) -> Run:
        try:
            run, config, spec, llm = new_run(body.prompt, body.agent_id, models, store, secrets)
        except UnknownAgent:
            raise field_error(("body", "agent_id"), f"unknown agent {body.agent_id!r}") from None
        except UnavailableModel as exc:
            raise field_error(("body", "agent_id"), str(exc)) from None
        store.create_run(run)
        task = asyncio.create_task(
            execute_run(
                run=run,
                prompt=body.prompt,
                config=config,
                spec=spec,
                llm=llm,
                store=store,
                bus=bus,
                secrets=secrets,
            )
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return run

    @app.get("/runs")
    async def list_runs() -> list[Run]:
        return store.list_runs()

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> RunDetail:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return RunDetail(run=run, spans=store.get_spans(run_id))

    @app.websocket("/runs/{run_id}/stream")
    async def stream_run(ws: WebSocket, run_id: str) -> None:
        # Browsers do not apply CORS to WebSockets; a missing Origin means a non-browser client.
        origin = ws.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if store.get_run(run_id) is None:
            await ws.accept()
            await ws.send_json({"type": "error", "message": "unknown run"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        # Subscribe before the snapshot so no event falls in between; clients upsert by span_id.
        queue = bus.subscribe(run_id)
        try:
            await ws.accept()
            for span in store.get_spans(run_id):
                kind = "span_started" if span.ended_at is None else "span_ended"
                await ws.send_json({"type": kind, "span": span.model_dump(mode="json")})
            run = store.get_run(run_id)
            if run is not None and run.status != "running":
                await ws.send_json({"type": "run_ended", "run": run.model_dump(mode="json")})
            else:
                while True:
                    event = await queue.get()
                    await ws.send_json(event)
                    if event["type"] == "run_ended":
                        break
            await ws.close()
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(run_id, queue)

    return app
