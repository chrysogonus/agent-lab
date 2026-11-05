"""HTTP and WebSocket API. Loopback only; see contracts/http-api.md."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, cast

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from agent_lab.agents.registry import (
    AGENTS,
    BLOCKS,
    KINDS,
    AgentSpec,
    config_tools,
    editable,
    pinned,
    validate_config,
)
from agent_lab.api_errors import field_error
from agent_lab.api_evaluations import add_evaluation_routes, copy_cases
from agent_lab.api_harness import add_harness_routes
from agent_lab.blocks.convert import to_blocks
from agent_lab.blocks.model import DEFAULT_BLOCKS, KIND_NAMES, LayoutError
from agent_lab.bus import Bus
from agent_lab.evaluation.runner import Evaluations
from agent_lab.graph import Graph
from agent_lab.harness.budget import DEFAULT_BUDGET, Budget, Harness
from agent_lab.harness.guard import RunGuard
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.models import LABELS, ModelRef, Models, UnavailableModel
from agent_lab.mcp import jsonrpc
from agent_lab.mcp.host import Host, ToolsUnavailable
from agent_lab.mcp.lab_server import LAB
from agent_lab.runs import UnknownAgent, execute_run, new_run
from agent_lab.store import LIVE_STATUSES, CustomAgent, NameInUse, Run, Store
from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span
from agent_lab.village.happening_runs import WhisperError
from agent_lab.village.health import reason_template
from agent_lab.village.health_view import day_ticks, days_health
from agent_lab.village.runner import CHANNEL, StepConflict, Village
from agent_lab.village.world import VILLAGERS, clock

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
    budget: Budget | None = None  # None: nothing limits its runs (templates always)
    ask_first: list[str] = []


class ModelInfo(BaseModel):
    provider: str
    provider_label: str
    model: str
    external: bool
    available: bool
    unavailable_reason: str | None
    default: bool


class ToolInfo(BaseModel):
    name: str  # the config name: calculator, get_weather or server/tool
    server: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments (a tool block's argument fields)


class AgentFields(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    sample_prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    config: dict[str, Any]
    model: ModelRef | None = None  # None: follow the default model
    budget: Budget | None = None  # absent: the default on a new agent, unchanged on an update


class NewAgent(AgentFields):
    template_id: str
    cases_from: str | None = None  # a template's examples or an agent's cases to start with


class GraphRequest(BaseModel):
    template_id: str
    config: dict[str, Any]


class WhisperRequest(BaseModel):
    text: str


class IntervalRequest(BaseModel):
    seconds: int = Field(ge=1, le=30)


class RunDetail(BaseModel):
    run: Run
    spans: list[Span]


def config_loc(loc: tuple[str | int, ...]) -> tuple[str | int, ...]:
    """A pydantic loc as a path into the config: drop the block kind it adds after an index."""
    return tuple(
        part
        for i, part in enumerate(loc)
        if not (i and isinstance(loc[i - 1], int) and part in KIND_NAMES)
    )


def _modern_version(message: object) -> str | None:
    """The protocol version a modern (2026-07-28) request carries in `_meta`, else None."""
    if not jsonrpc.is_request(message) and not jsonrpc.is_notification(message):
        return None
    params = cast(dict[str, Any], message).get("params")
    meta = cast(dict[str, Any], params).get("_meta") if isinstance(params, dict) else None
    version = (
        cast(dict[str, Any], meta).get(jsonrpc.VERSION_KEY) if isinstance(meta, dict) else None
    )
    return version if isinstance(version, str) else None


def _decoded(value: str | None) -> str | None:
    if value and value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[9:-2]).decode()
        except ValueError:
            return None
    return value


def _header_mismatch(message: dict[str, Any], version: str, headers: Any) -> str | None:
    """Why a modern request's headers disagree with its body, or None."""
    if headers.get("mcp-protocol-version") != version:
        return "the MCP-Protocol-Version header does not match the request"
    if headers.get("mcp-method") != message["method"]:
        return "the Mcp-Method header does not match the request"
    if message["method"] == "tools/call":
        name = cast(dict[str, Any], message.get("params") or {}).get("name")
        if _decoded(headers.get("mcp-name")) != name:
            return "the Mcp-Name header does not match the tool"
    return None


def create_app(
    *, store: Store, models: Models, secrets: tuple[str, ...] = (), host: Host | None = None
) -> FastAPI:
    """`host` defaults to one with only the lab's own server."""
    host = host or Host()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        # Nothing can finish what the last process left live (FR-022).
        store.mark_interrupted()
        store.mark_evaluations_interrupted()
        await host.start()
        yield
        await host.close()

    app = FastAPI(title="Glasshouse", lifespan=lifespan)
    # Rejects DNS-rebinding requests that reach the loopback port under a foreign Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type"],
    )
    bus = Bus()
    village = Village(store=store, models=models, bus=bus, secrets=secrets, host=host)
    app.state.village = village  # for tests that set up a scene
    live = LiveRuns()
    evaluations = Evaluations(
        store=store, models=models, host=host, bus=bus, secrets=secrets, live=live
    )
    add_evaluation_routes(app, store, evaluations, village)
    add_harness_routes(app, store, live)
    tasks: set[asyncio.Task[None]] = set()  # strong refs so running runs are not collected

    def checked_config(template_id: str, raw: dict[str, Any]) -> BaseModel:
        """The template's model validates the config; the client never sets model or graph."""
        if template_id not in KINDS:
            raise field_error(("body", "template_id"), f"unknown template {template_id!r}")
        for key in ("model", "provider"):
            if key in raw:
                raise field_error(("body", "config", key), "set the model with the model field")
        try:
            return validate_config(template_id, raw, models.default)
        except ValidationError as exc:
            blocks = template_id == BLOCKS.id  # only block configs carry union tags
            errors = [
                {
                    "loc": ("body", "config", *(config_loc(e["loc"]) if blocks else e["loc"])),
                    "msg": e["msg"],
                    "type": e["type"],
                }
                for e in exc.errors()
            ]
            raise RequestValidationError(errors) from None
        except LayoutError as exc:
            errors = [
                {"loc": ("body", "config", *loc), "msg": msg, "type": "value_error"}
                for loc, msg in exc.errors
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

    def harness_of(agent: CustomAgent | None) -> Harness:
        return Harness.model_validate(agent.harness if agent and agent.harness else {})

    def custom_info(agent: CustomAgent) -> AgentInfo:
        config = validate_config(agent.template_id, agent.config, models.default)
        harness = harness_of(agent)
        return AgentInfo(
            id=agent.agent_id,
            kind="custom",
            template_id=agent.template_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config=editable(config),
            model=pinned(agent.config),
            graph=KINDS[agent.template_id].graph(config),
            budget=harness.budget,
            ask_first=harness.ask_first,
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
        await host.start()
        return [ToolInfo.model_validate(t) for t in host.tools()]

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        """The lab's own MCP server for outside clients (research §9); no sessions, no streams."""
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status.HTTP_403_FORBIDDEN)
        try:
            message = json.loads(await request.body())
        except ValueError:
            error = jsonrpc.error(None, jsonrpc.PARSE_ERROR, "parse error")
            return JSONResponse(error, status.HTTP_400_BAD_REQUEST)
        if not isinstance(message, dict):  # batches went away in 2025-06-18
            error = jsonrpc.error(None, jsonrpc.INVALID_REQUEST, "expected one JSON-RPC message")
            return JSONResponse(error, status.HTTP_400_BAD_REQUEST)
        message = cast(dict[str, Any], message)
        modern = _modern_version(message)
        if modern and (mismatch := _header_mismatch(message, modern, request.headers)):
            error = jsonrpc.error(message.get("id"), jsonrpc.HEADER_MISMATCH, mismatch)
            return JSONResponse(error, status.HTTP_400_BAD_REQUEST)
        answer = LAB.handle(message)
        if answer is None:
            return Response(status_code=status.HTTP_202_ACCEPTED)
        unknown = answer.get("error", {}).get("code") == jsonrpc.METHOD_NOT_FOUND
        # A legacy client may read 404 as "session expired"; it gets the error with a 200.
        code = status.HTTP_404_NOT_FOUND if modern and unknown else status.HTTP_200_OK
        return JSONResponse(answer, code)

    @app.api_route("/mcp", methods=["GET", "DELETE"])
    async def mcp_no_stream() -> Response:
        return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})

    @app.get("/mcp/servers")
    async def list_servers() -> dict[str, Any]:
        await host.start()
        return host.servers()

    @app.post("/mcp/servers/{name}/reconnect", status_code=status.HTTP_202_ACCEPTED)
    async def reconnect_server(name: str) -> dict[str, Any]:
        await host.start()
        try:
            host.reconnect(name)
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no server {name!r}") from None
        return host.server(name)

    @app.post("/mcp/reload", status_code=status.HTTP_202_ACCEPTED)
    async def reload_servers() -> dict[str, Any]:
        await host.start()
        await host.reload()
        return host.servers()

    @app.get("/blocks/new")
    async def new_block_agent() -> AgentInfo:
        """An unsaved block agent with one model block, for the builder to edit."""
        config = validate_config(
            BLOCKS.id, {"blocks": [b.model_dump() for b in DEFAULT_BLOCKS]}, models.default
        )
        return AgentInfo(
            id="",
            kind="custom",
            template_id=BLOCKS.id,
            name="Block agent",
            description="",
            sample_prompt=BLOCKS.sample_prompt,
            config=editable(config),
            model=None,
            graph=BLOCKS.graph(config),
            budget=DEFAULT_BUDGET,
        )

    @app.get("/agents/{agent_id}/blocks")
    async def open_as_blocks(agent_id: str) -> AgentInfo:
        """An unsaved block copy of a template or template-based agent ("Open as blocks")."""
        harness = Harness(budget=DEFAULT_BUDGET)  # what a new agent starts with
        if agent_id in AGENTS:
            spec = AGENTS[agent_id]
            stored: dict[str, Any] = {}
            name, description, sample_prompt = spec.name, spec.description, spec.sample_prompt
        else:
            agent = store.get_agent(agent_id)
            if agent is None:
                raise HTTPException(status_code=404, detail="unknown agent")
            if agent.template_id == BLOCKS.id:
                raise HTTPException(status_code=409, detail="already a block agent")
            spec, stored = AGENTS[agent.template_id], agent.config
            name, description, sample_prompt = agent.name, agent.description, agent.sample_prompt
            harness = harness_of(agent)
        model = pinned(stored)
        source = validate_config(spec.id, stored, models.default)
        pinned_keys = {"model": model.model, "provider": model.provider} if model else {}
        try:
            config = validate_config(
                BLOCKS.id, {**to_blocks(spec.id, source), **pinned_keys}, models.default
            )
        except LayoutError as exc:
            # e.g. a prompt with literal "{city}", which a block agent reads as a reference
            raise field_error(("path", "agent_id"), f"can't open as blocks: {exc}") from None
        return AgentInfo(
            id="",
            kind="custom",
            template_id=BLOCKS.id,
            name=name,
            description=description,
            sample_prompt=sample_prompt,
            config=editable(config),
            model=model,
            graph=BLOCKS.graph(config),
            budget=harness.budget,
            ask_first=harness.ask_first,
        )

    @app.post("/agents", status_code=status.HTTP_201_CREATED)
    async def create_agent(body: NewAgent) -> AgentInfo:
        config = checked_config(body.template_id, body.config)
        source = body.cases_from
        if source and source not in AGENTS and store.get_agent(source) is None:
            raise field_error(("body", "cases_from"), f"unknown agent {source!r}")
        budget = body.budget if "budget" in body.model_fields_set else DEFAULT_BUDGET
        try:
            agent = store.create_agent(
                template_id=body.template_id,
                name=body.name,
                description=body.description,
                sample_prompt=body.sample_prompt,
                config=stored_config(config, body.model),
                harness=Harness(budget=budget).model_dump(),
            )
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None
        if source:
            copy_cases(store, source, agent.agent_id)
        return saved(agent)

    @app.put("/agents/{agent_id}")
    async def update_agent(agent_id: str, body: AgentFields) -> AgentInfo:
        current = store.get_agent(agent_id)  # templates are not stored: 404
        if current is None:
            raise HTTPException(status_code=404, detail="unknown custom agent")
        config = checked_config(current.template_id, body.config)
        harness = harness_of(current)
        if "budget" in body.model_fields_set:
            harness = harness.model_copy(update={"budget": body.budget})
        try:
            return saved(
                store.update_agent(
                    agent_id,
                    name=body.name,
                    description=body.description,
                    sample_prompt=body.sample_prompt,
                    config=stored_config(config, body.model),
                    harness=harness.model_dump(),
                )
            )
        except NameInUse:
            raise field_error(("body", "name"), "name already in use") from None

    @app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_agent(agent_id: str) -> None:
        """Runs of the agent keep their own snapshot (name, config, graph) and stay listed."""
        if evaluations.running_for(agent_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "an evaluation of it is running")
        if not store.delete_agent(agent_id):
            raise HTTPException(status_code=404, detail="unknown custom agent")

    @app.post("/graph")
    async def preview_graph(body: GraphRequest) -> Graph:
        """The graph the server derives from an unsaved config (the builder's live preview)."""
        config = checked_config(body.template_id, body.config)
        return KINDS[body.template_id].graph(config)

    @app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(body: RunRequest) -> Run:
        try:
            run, config, spec, llm = new_run(body.prompt, body.agent_id, models, store, secrets)
        except UnknownAgent:
            raise field_error(("body", "agent_id"), f"unknown agent {body.agent_id!r}") from None
        except UnavailableModel as exc:
            raise field_error(("body", "agent_id"), str(exc)) from None
        except (LayoutError, ValidationError) as exc:
            # A stored agent that no longer validates, e.g. after a rule changed.
            raise field_error(
                ("body", "agent_id"), f"the agent is no longer valid: {exc}"
            ) from None
        await host.start()
        try:
            tools = host.resolve(config_tools(config))
        except ToolsUnavailable as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        run_secrets = (*secrets, *host.secrets())  # the servers file's keys too
        run.prompt = redact(run.prompt, run_secrets)
        run.config = redact(run.config, run_secrets)
        harness = harness_of(store.get_agent(body.agent_id))
        run.harness = {**harness.model_dump(), "default_budget": False}
        store.create_run(run)
        guard = RunGuard(harness)
        task = asyncio.create_task(
            execute_run(
                run=run,
                prompt=body.prompt,
                config=config,
                spec=spec,
                llm=llm,
                store=store,
                bus=bus,
                secrets=run_secrets,
                tools=tools,
                guard=guard,
            )
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        live.add(run.run_id, task, guard)
        task.add_done_callback(lambda _: live.remove(run.run_id))
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
            if run is not None and run.status not in LIVE_STATUSES:
                await ws.send_json({"type": "run_ended", "run": run.model_dump(mode="json")})
            else:
                if run is not None and run.status != "running":
                    await ws.send_json(
                        {"type": "run_status", "run_id": run_id, "status": run.status}
                    )
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

    # --- the village (specs/006-village/ and specs/007-village-life/contracts/http-api.md) ---

    @app.get("/village")
    async def get_village() -> dict[str, Any]:
        return village.state()

    @app.post("/village/start")
    async def start_village() -> dict[str, Any]:
        village.start()
        return village.state()

    @app.post("/village/pause")
    async def pause_village() -> dict[str, Any]:
        village.pause()
        return village.state()

    @app.post("/village/step")
    async def step_village() -> dict[str, Any]:
        try:
            await village.step()
        except StepConflict:
            raise HTTPException(
                status_code=409, detail="the village is running or a step is in progress"
            ) from None
        return village.state()

    @app.put("/village/interval")
    async def set_village_interval(body: IntervalRequest) -> dict[str, Any]:
        await village.set_interval(body.seconds)
        return village.state()

    @app.post("/village/reset")
    async def reset_village() -> dict[str, Any]:
        await village.reset()
        return village.state()

    @app.get("/village/villagers/{name}/turns")
    async def villager_turns(name: str) -> list[Run]:
        """Every turn of a villager, newest first, whichever agent played it."""
        if name not in VILLAGERS:
            raise HTTPException(status_code=404, detail="unknown villager")
        return store.list_turns(name)

    @app.post("/village/villagers/{name}/whisper")
    async def whisper_to_villager(name: str, body: WhisperRequest) -> dict[str, bool]:
        """The owner's line to one villager, heard as a claim from "a voice" (M15)."""
        try:
            return {"heard": village.whisper(name, body.text)}
        except WhisperError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from None

    @app.get("/village/health")
    async def village_health(days: int = Query(14, ge=1, le=28)) -> dict[str, Any]:
        """Village health of the recent days, newest first (specs/013-measuring-the-village/)."""
        return {"days": days_health(store, village.world, days)}

    @app.get("/village/health/{day}/turns")
    async def village_health_turns(day: int, reason: str) -> list[Run]:
        """The decisions of a day that waited for one kind of reason, newest first."""
        if not 1 <= day <= clock(village.world["tick"])[0]:
            raise field_error(("path", "day"), "no such village day")
        first, last = day_ticks(day)
        born = float(village.world.get("born", 0.0))
        found: list[str] = []
        for r in store.village_runs(first, last, born):
            action: dict[str, Any] = r["village_action"] or {}
            if (
                action.get("action") == "wait"
                and reason_template(action.get("reason") or "") == reason
            ):
                found.append(r["run_id"])
        return [run for run in map(store.get_run, reversed(found)) if run is not None]

    @app.websocket("/village/stream")
    async def village_stream(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        queue = bus.subscribe(CHANNEL)
        village.viewer_joined()
        try:
            await ws.accept()
            await ws.send_json({"type": "state", "state": village.state()})
            # Wait for village events and for the client closing, whichever comes first, so a
            # closed tab counts as gone even while nothing is published (the idle pause).
            receive = asyncio.create_task(ws.receive())
            while True:
                event = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({event, receive}, return_when=asyncio.FIRST_COMPLETED)
                if event in done:
                    await ws.send_json(event.result())
                else:
                    event.cancel()
                if receive in done:
                    if receive.result()["type"] == "websocket.disconnect":
                        break
                    receive = asyncio.create_task(ws.receive())  # ignore anything the client sends
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(CHANNEL, queue)
            village.viewer_left()

    return app
