"""Stopping a run: Stop reaches every branch and keeps the trace (M17, FR-012)."""

import asyncio
import dataclasses
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import answer, fake_models, lab_tools, tool_call
from test_api import BASE, ORIGIN, WS_BASE, read_until_run_ended

from agent_lab.agents.registry import config_tools
from agent_lab.api import create_app
from agent_lab.bus import Bus
from agent_lab.harness.budget import Harness
from agent_lab.harness.guard import RunGuard, current_guard
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.mcp.client import CallResult
from agent_lab.mcp.host import HostTool
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Run, Store


class HangsAfter(FakeLLM):
    """Answers its script, then never answers again: a model call that is under way."""

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        if not self._script:
            await asyncio.Event().wait()
        return await super().chat(
            messages, tools, response_format=response_format, reasoning=reasoning
        )


class HangingConnection:
    protocol_version = "2026-07-28"

    async def call(self, _tool: str, _arguments: dict[str, Any]) -> CallResult:
        await asyncio.Event().wait()
        raise AssertionError("never answers")


def start(
    store: Store,
    llm: FakeLLM,
    agent_id: str,
    guard: RunGuard | None,
    tools: dict[str, HostTool] | None = None,
) -> tuple[Run, asyncio.Task[None]]:
    run, config, spec, client = new_run("Do it", agent_id, fake_models(llm), store)
    store.create_run(run)
    resolved = tools if tools is not None else lab_tools(*config_tools(config))
    task = asyncio.create_task(
        execute_run(
            run=run,
            prompt="Do it",
            config=config,
            spec=spec,
            llm=client,
            store=store,
            bus=Bus(),
            tools=resolved if config_tools(config) else {},
            guard=guard,
        )
    )
    return run, task


@pytest.mark.anyio
async def test_stop_ends_parallel_branches_within_two_seconds_and_keeps_the_trace(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "lab.db")
    guard = RunGuard(Harness())
    live = LiveRuns()
    run, task = start(store, HangsAfter([]), "parallel", guard)
    live.add(run.run_id, task, guard)
    await asyncio.sleep(0.05)  # the branches are waiting for the model

    began = time.monotonic()
    assert live.stop(run.run_id) is True
    await task

    assert time.monotonic() - began < 2
    stored = store.get_run(run.run_id)
    assert stored is not None
    assert stored.status == "stopped"
    assert stored.stop_reason == "stopped by the owner"
    spans = store.get_spans(run.run_id)
    assert sum(s.kind == "llm" for s in spans) == 3  # the three branches stay in the trace
    assert all(s.ended_at is not None for s in spans)


@pytest.mark.anyio
async def test_a_stopped_run_keeps_the_text_it_had(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    guard = RunGuard(Harness())
    said = tool_call("calculator", '{"expression": "1+1"}').model_copy(
        update={"content": "Let me work that out."}
    )
    run, task = start(store, HangsAfter([said]), "react", guard)
    await asyncio.sleep(0.05)

    guard.stop_requested = True
    task.cancel()
    await task

    stored = store.get_run(run.run_id)
    assert stored is not None
    assert stored.answer == "Let me work that out."


@pytest.mark.anyio
async def test_stop_during_a_tool_call_says_the_answer_was_not_awaited(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    guard = RunGuard(Harness())
    hanging = dataclasses.replace(
        lab_tools("calculator")["calculator"],
        connection=HangingConnection(),  # pyright: ignore[reportArgumentType]
    )
    llm = FakeLLM([tool_call("calculator", '{"expression": "1+1"}')])
    tools = {"calculator": hanging, **lab_tools("get_weather")}
    run, task = start(store, llm, "react", guard, tools)
    await asyncio.sleep(0.05)

    guard.stop_requested = True
    task.cancel()
    await task

    stored = store.get_run(run.run_id)
    assert stored is not None
    assert stored.status == "stopped"
    tool = next(s for s in store.get_spans(run.run_id) if s.kind == "tool")
    assert tool.error == "stopped; the tool's answer was not awaited"


@pytest.mark.anyio
async def test_a_cancel_nobody_asked_for_still_cancels(tmp_path: Path) -> None:
    """A server shutting down must not see its task swallow the cancellation."""
    store = Store(tmp_path / "lab.db")
    run, task = start(store, HangsAfter([]), "react", RunGuard(Harness()))
    await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    stored = store.get_run(run.run_id)
    assert stored is not None
    assert stored.status == "running"


@pytest.mark.anyio
async def test_steps_see_the_runs_guard_and_a_run_without_one_sees_none(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    seen: list[RunGuard | None] = []

    def looks(_messages: list[Message]) -> ChatResponse:
        seen.append(current_guard.get())
        return answer("done")

    guard = RunGuard(Harness())
    script: list[ScriptItem] = [looks]
    _, task = start(store, FakeLLM(script), "react", guard)
    await task
    assert seen == [guard]
    assert current_guard.get() is None

    # A village run started while another guard is current must not inherit it.
    token = current_guard.set(guard)
    try:
        _, task = start(store, FakeLLM([looks]), "react", None)
        await task
    finally:
        current_guard.reset(token)
    assert seen == [guard, None]


@pytest.mark.anyio
async def test_only_a_live_run_can_be_stopped(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    guard = RunGuard(Harness())
    live = LiveRuns()
    assert live.stop("nobody") is False

    run, task = start(store, FakeLLM([answer("done")]), "react", guard)
    live.add(run.run_id, task, guard)
    await task
    live.remove(run.run_id)
    assert live.stop(run.run_id) is False


def test_the_owner_stops_a_live_run_through_the_api(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    app = create_app(store=store, models=fake_models(HangsAfter([])))
    with TestClient(app, base_url=BASE) as client:
        run = client.post("/runs", json={"prompt": "hi", "agent_id": "react"}).json()
        with client.websocket_connect(
            f"{WS_BASE}/runs/{run['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            assert ws.receive_json()["type"] == "span_started"  # it is under way
            began = time.monotonic()
            stopped = client.post(f"/runs/{run['run_id']}/stop")
            assert stopped.status_code == 202
            ended = read_until_run_ended(ws)[-1]["run"]
        assert time.monotonic() - began < 2
        assert ended["status"] == "stopped"
        assert ended["stop_reason"] == "stopped by the owner"
        assert client.post(f"/runs/{run['run_id']}/stop").status_code == 409  # already ended


def test_stopping_what_is_not_a_live_lab_run_is_refused(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    turn, _, _, _ = new_run("hi", "react", fake_models(FakeLLM([])), store, village_tick=3)
    store.create_run(turn)
    with TestClient(
        create_app(store=store, models=fake_models(FakeLLM([]))), base_url=BASE
    ) as client:
        assert client.post("/runs/nobody/stop").status_code == 404
        assert client.post(f"/runs/{turn.run_id}/stop").status_code == 409
