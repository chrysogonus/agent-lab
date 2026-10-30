"""HTTP and WebSocket API. Loopback only; see contracts/http-api.md."""

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from agent_lab.bus import Bus
from agent_lab.llm.base import LLMClient
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Run, Store
from agent_lab.tracing.span import Span

ALLOWED_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class RunDetail(BaseModel):
    run: Run
    spans: list[Span]


def create_app(*, store: Store, llm: LLMClient, secrets: tuple[str, ...] = ()) -> FastAPI:
    app = FastAPI(title="Agent Lab")
    # Rejects DNS-rebinding requests that reach the loopback port under a foreign Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    bus = Bus()
    tasks: set[asyncio.Task[None]] = set()  # strong refs so running runs are not collected

    @app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(body: RunRequest) -> Run:
        run, config = new_run(body.prompt, llm, secrets)
        store.create_run(run)
        task = asyncio.create_task(
            execute_run(
                run=run,
                prompt=body.prompt,
                config=config,
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
