"""Asking the owner before a tool call (M17, FR-015 to FR-021, SC-005)."""

import asyncio
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import (
    answer,
    assert_trace_valid,
    branches_block,
    fake_models,
    lab_tools,
    model_block,
    tool_block,
    tool_call,
)
from test_api import BASE, ORIGIN, WS_BASE, read_until_run_ended

from agent_lab.api import create_app
from agent_lab.bus import Bus
from agent_lab.harness.approvals import Approvals, CaseDecider, Decider, OwnerDecider
from agent_lab.harness.budget import DEFAULT_BUDGET, Budget, Harness
from agent_lab.harness.guard import RunGuard
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.base import ChatResponse, ToolCall
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.mcp.client import CallResult
from agent_lab.mcp.host import Host, HostTool
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Store

ADD = '{"expression": "1+1"}'
ASK = Harness(ask_first=["calculator"])


def budget(**limits: Any) -> Budget:
    return DEFAULT_BUDGET.model_copy(update=limits)


class Counted:
    """The real calculator, counting the calls that actually go out."""

    def __init__(self, tool: HostTool) -> None:
        self.real = tool.connection
        self.protocol_version = tool.connection.protocol_version
        self.calls = 0

    async def call(self, name: str, arguments: dict[str, Any]) -> CallResult:
        self.calls += 1
        return await self.real.call(name, arguments)


class Lab:
    """One run under a guard, with its counted calculator and its open requests."""

    def __init__(
        self,
        tmp_path: Path,
        script: list[ScriptItem],
        *,
        harness: Harness = ASK,
        timeout: float = 30,
        secrets: tuple[str, ...] = (),
        decider: Decider | None = None,
        agent_id: str | None = None,
        store: Store | None = None,
    ) -> None:
        self.store = store or Store(tmp_path / "lab.db")
        self.llm = FakeLLM(script)
        self.approvals = Approvals(timeout=timeout)
        self.bus = Bus()
        self.run, config, spec, client = new_run(
            "Do it", agent_id or "react", fake_models(self.llm), self.store, secrets
        )
        self.store.create_run(self.run)
        self.events = self.bus.subscribe(self.run.run_id)
        tool = lab_tools("calculator")["calculator"]
        self.counted = Counted(tool)
        counted = dataclasses.replace(tool, connection=self.counted)  # pyright: ignore[reportArgumentType]
        statuses = self._status
        self.guard = RunGuard(
            harness,
            decider=decider
            or OwnerDecider(
                self.approvals,
                run_id=self.run.run_id,
                agent_name="Tested",
                prompt="Do it",
                secrets=secrets,
            ),
            on_status=statuses,
        )
        self.task = asyncio.create_task(
            execute_run(
                run=self.run,
                prompt="Do it",
                config=config,
                spec=spec,
                llm=client,
                store=self.store,
                bus=self.bus,
                secrets=secrets,
                tools={"calculator": counted, **lab_tools("get_weather")},
                guard=self.guard,
            )
        )

    def _status(self, status: Any) -> None:
        self.store.set_run_status(self.run.run_id, status)

    async def open_request(self) -> Any:
        for _ in range(200):
            found = self.approvals.open()
            if found:
                return found[0]
            await asyncio.sleep(0.005)
        raise AssertionError("no request opened")

    async def finished(self) -> Any:
        await asyncio.wait_for(self.task, 5)
        done = self.store.get_run(self.run.run_id)
        assert done is not None
        return done

    def spans(self) -> list[Any]:
        return self.store.get_spans(self.run.run_id)


def tool_spans(spans: list[Any]) -> list[Any]:
    return [s for s in spans if s.kind == "tool"]


def approval_spans(spans: list[Any]) -> list[Any]:
    return [s for s in spans if s.name.startswith("approval ")]


@pytest.mark.anyio
async def test_a_tool_marked_ask_first_waits_until_the_owner_approves(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("It is 2.")])

    request = await lab.open_request()
    assert request.tool == "calculator"
    assert request.server == "lab"
    assert request.arguments == {"expression": "1+1"}
    assert request.run_id == lab.run.run_id
    assert request.expires_at == pytest.approx(request.asked_at + 30)
    assert lab.counted.calls == 0
    stored = lab.store.get_run(lab.run.run_id)
    assert stored is not None
    assert stored.status == "waiting_approval"

    assert lab.approvals.answer(request.approval_id, approve=True, reason=None) is True
    done = await lab.finished()

    assert done.status == "completed"
    assert lab.counted.calls == 1
    spans = lab.spans()
    assert_trace_valid(done.graph, spans)
    decision = approval_spans(spans)[0]
    assert decision.attributes["lab.approval.decision"] == "approved"
    assert decision.attributes["lab.approval.by"] == "owner"
    assert decision.node_id == "tool:calculator"
    assert len(tool_spans(spans)) == 1


@pytest.mark.anyio
async def test_a_denial_becomes_the_tools_result_and_the_run_goes_on(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("All right.")])

    request = await lab.open_request()
    lab.approvals.answer(request.approval_id, approve=False, reason="not now")
    done = await lab.finished()

    assert done.status == "completed"
    assert done.answer == "All right."
    assert lab.counted.calls == 0
    assert lab.llm.calls[1][-1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "denied by the owner: not now",
    }
    spans = lab.spans()
    assert tool_spans(spans) == []  # a tool span means the tool was called
    assert done.totals.tool_calls == 0
    decision = approval_spans(spans)[0]
    assert decision.attributes["lab.approval.decision"] == "denied"
    assert decision.attributes["lab.approval.reason"] == "not now"
    assert decision.output == "denied by the owner: not now"
    assert_trace_valid(done.graph, spans)


@pytest.mark.anyio
async def test_a_denial_without_a_reason_says_only_that(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("All right.")])
    request = await lab.open_request()
    lab.approvals.answer(request.approval_id, approve=False, reason=None)
    await lab.finished()
    assert lab.llm.calls[1][-1]["content"] == "denied by the owner"


@pytest.mark.anyio
async def test_no_answer_in_time_is_a_denial(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("All right.")], timeout=0.01)
    done = await lab.finished()

    assert done.status == "completed"
    assert lab.counted.calls == 0
    assert lab.llm.calls[1][-1]["content"] == "denied by the owner: no answer from the owner"
    decision = approval_spans(lab.spans())[0]
    assert decision.attributes["lab.approval.decision"] == "timed_out"
    assert decision.attributes["lab.approval.by"] == "timeout"
    assert lab.approvals.open() == []


@pytest.mark.anyio
async def test_a_tool_not_marked_goes_out_without_asking(tmp_path: Path) -> None:
    lab = Lab(
        tmp_path,
        [tool_call("calculator", ADD), answer("2")],
        harness=Harness(ask_first=["get_weather"]),
    )
    done = await lab.finished()
    assert done.status == "completed"
    assert lab.counted.calls == 1
    assert approval_spans(lab.spans()) == []


@pytest.mark.anyio
async def test_arguments_the_tool_could_not_read_ask_nobody(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", "not json"), answer("Sorry.")])
    done = await lab.finished()
    assert done.status == "completed"
    assert lab.counted.calls == 0
    assert approval_spans(lab.spans()) == []


@pytest.mark.anyio
async def test_two_calls_of_one_answer_are_decided_one_by_one_in_order(tmp_path: Path) -> None:
    calls = [
        ToolCall(id="a", name="calculator", arguments='{"expression": "1"}'),
        ToolCall(id="b", name="calculator", arguments='{"expression": "2"}'),
    ]
    script: list[ScriptItem] = [
        ChatResponse(tool_calls=calls, tokens_in=1, tokens_out=1),
        answer("done"),
    ]
    lab = Lab(tmp_path, script)

    first = await lab.open_request()
    assert first.arguments == {"expression": "1"}
    assert len(lab.approvals.open()) == 1  # the second is not asked yet
    lab.approvals.answer(first.approval_id, approve=False, reason=None)
    await asyncio.sleep(0.01)
    second = await lab.open_request()
    assert second.arguments == {"expression": "2"}
    assert lab.approvals.answer(second.approval_id, approve=True, reason=None) is True

    await lab.finished()
    assert lab.counted.calls == 1


@pytest.mark.anyio
async def test_a_tool_block_waits_and_passes_a_denial_on_as_its_output(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="blocks",
        name="Blocks",
        description="",
        sample_prompt="hi",
        config={
            "blocks": [
                tool_block("sum", expression="1+1"),
                model_block("say", message="It said: {previous}"),
            ]
        },
    )
    lab = Lab(tmp_path, [answer("done")], store=store, agent_id=agent.agent_id)

    request = await lab.open_request()
    assert lab.counted.calls == 0
    lab.approvals.answer(request.approval_id, approve=False, reason="not now")
    done = await lab.finished()

    assert done.status == "completed"
    assert lab.counted.calls == 0
    assert lab.llm.calls[0][-1]["content"] == "It said: denied by the owner: not now"
    decision = approval_spans(lab.spans())[0]
    assert decision.node_id == "sum"
    assert_trace_valid(done.graph, lab.spans())


@pytest.mark.anyio
async def test_time_waiting_for_the_owner_does_not_count(tmp_path: Path) -> None:
    lab = Lab(
        tmp_path,
        [tool_call("calculator", ADD), answer("2")],
        harness=Harness(budget=budget(seconds=0.2), ask_first=["calculator"]),
    )
    request = await lab.open_request()
    await asyncio.sleep(0.3)  # longer than the whole budget
    lab.approvals.answer(request.approval_id, approve=True, reason=None)
    done = await lab.finished()
    assert done.status == "completed"


@pytest.mark.anyio
async def test_a_run_over_budget_when_an_approval_comes_sends_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    fan = branches_block(
        "fan",
        {"ask": [tool_block("sum", expression="1+1")], "talk": [model_block("big")]},
    )
    agent = store.create_agent(
        template_id="blocks",
        name="Fan",
        description="",
        sample_prompt="hi",
        config={"blocks": [fan]},
    )
    expensive = ChatResponse(content="long", tokens_in=500, tokens_out=500)
    lab = Lab(
        tmp_path,
        [expensive],
        store=store,
        agent_id=agent.agent_id,
        harness=Harness(budget=budget(tokens=100), ask_first=["calculator"]),
    )
    request = await lab.open_request()
    for _ in range(100):  # the other branch goes past the token limit during the wait
        if lab.guard.over:
            break
        await asyncio.sleep(0.005)
    assert lab.guard.over == "tokens: 1,000 of 100"

    lab.approvals.answer(request.approval_id, approve=True, reason=None)
    done = await lab.finished()

    assert done.status == "over_budget"
    assert lab.counted.calls == 0
    assert tool_spans(lab.spans()) == []


@pytest.mark.anyio
async def test_stop_during_a_wait_ends_the_run_and_the_request(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("too late")])
    await lab.open_request()
    live = LiveRuns()
    live.add(lab.run.run_id, lab.task, lab.guard)

    began = time.monotonic()
    assert live.stop(lab.run.run_id) is True
    done = await lab.finished()

    assert time.monotonic() - began < 2
    assert done.status == "stopped"
    assert lab.counted.calls == 0
    assert lab.approvals.open() == []


@pytest.mark.anyio
async def test_a_servers_secret_never_reaches_the_owners_screen_or_the_trace(
    tmp_path: Path,
) -> None:
    secret = "sk-very-secret"  # noqa: S105
    arguments = json.dumps({"expression": secret})
    lab = Lab(tmp_path, [tool_call("calculator", arguments), answer("ok")], secrets=(secret,))
    request = await lab.open_request()
    assert secret not in json.dumps(request.model_dump())
    lab.approvals.answer(request.approval_id, approve=False, reason=None)
    await lab.finished()
    assert secret not in json.dumps([s.model_dump(mode="json") for s in lab.spans()])


@pytest.mark.anyio
async def test_a_case_decides_at_once_and_the_trace_says_so(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("ok")], decider=CaseDecider("deny"))
    done = await lab.finished()
    assert done.status == "completed"
    assert lab.counted.calls == 0
    assert lab.llm.calls[1][-1]["content"] == "denied by the test case"
    decision = approval_spans(lab.spans())[0]
    assert decision.attributes["lab.approval.by"] == "case"
    assert lab.approvals.open() == []


@pytest.mark.anyio
async def test_a_case_that_approves_sends_the_call(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("2")], decider=CaseDecider("approve"))
    await lab.finished()
    assert lab.counted.calls == 1


@pytest.mark.anyio
async def test_answering_twice_or_too_late_does_nothing(tmp_path: Path) -> None:
    lab = Lab(tmp_path, [tool_call("calculator", ADD), answer("2")])
    request = await lab.open_request()
    assert lab.approvals.answer("nobody", approve=True, reason=None) is False
    assert lab.approvals.answer(request.approval_id, approve=False, reason=None) is True
    assert lab.approvals.answer(request.approval_id, approve=True, reason=None) is False
    await lab.finished()
    assert lab.counted.calls == 0


# --- through the API ---


def notes_host(tmp_path: Path) -> Host:
    servers = tmp_path / "mcp.json"
    folder = tmp_path / "notes"
    servers.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "notes": {
                        "command": sys.executable,
                        "args": ["-m", "agent_lab.mcp.notes", "--folder", str(folder)],
                    }
                }
            }
        )
    )
    return Host(servers)


def wait_for_request(client: TestClient) -> dict[str, Any]:
    for _ in range(400):
        found = client.get("/approvals").json()
        if found:
            return found[0]
        time.sleep(0.01)
    raise AssertionError("no request opened")


def test_the_independent_test_of_the_story_with_the_real_notes_server(tmp_path: Path) -> None:
    write = '{"name": "fact", "text": "Berlin is in Germany."}'
    script: list[ScriptItem] = [
        tool_call("write_note", write),
        answer("Not written."),
        tool_call("write_note", write),
        answer("Written."),
    ]
    store = Store(tmp_path / "lab.db")
    app = create_app(store=store, models=fake_models(FakeLLM(script)), host=notes_host(tmp_path))
    folder = tmp_path / "notes"
    with TestClient(app, base_url=BASE) as client:
        for _ in range(400):
            if any(t["name"] == "notes/write_note" for t in client.get("/tools").json()):
                break
            time.sleep(0.01)
        agent = client.post(
            "/agents",
            json={
                "template_id": "react",
                "name": "Noter",
                "sample_prompt": "hi",
                "config": {"reasoning": False, "tools": ["notes/write_note"]},
                "ask_first": ["notes/write_note"],
            },
        ).json()
        assert agent["ask_first"] == ["notes/write_note"]

        denied = client.post("/runs", json={"prompt": "Note it", "agent_id": agent["id"]}).json()
        request = wait_for_request(client)
        assert request["run_id"] == denied["run_id"]
        assert request["tool"] == "notes/write_note"
        assert request["server"] == "notes"
        assert request["agent_name"] == "Noter"
        assert not list(folder.glob("*"))
        answered = client.post(
            f"/approvals/{request['approval_id']}",
            json={"decision": "deny", "reason": "not now"},
            headers={"origin": ORIGIN},
        )
        assert answered.status_code == 204
        with client.websocket_connect(
            f"{WS_BASE}/runs/{denied['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            assert read_until_run_ended(ws)[-1]["run"]["answer"] == "Not written."
        assert not list(folder.glob("*"))

        approved = client.post("/runs", json={"prompt": "Note it", "agent_id": agent["id"]}).json()
        request = wait_for_request(client)
        client.post(f"/approvals/{request['approval_id']}", json={"decision": "approve"})
        with client.websocket_connect(
            f"{WS_BASE}/runs/{approved['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            assert read_until_run_ended(ws)[-1]["run"]["answer"] == "Written."
        assert [p.read_text() for p in folder.glob("*")] == ["Berlin is in Germany."]


def test_a_waiting_run_tells_its_stream(tmp_path: Path) -> None:
    script: list[ScriptItem] = [tool_call("calculator", ADD), answer("2")]
    app = create_app(store=Store(tmp_path / "lab.db"), models=fake_models(FakeLLM(script)))
    with TestClient(app, base_url=BASE) as client:
        agent = client.post(
            "/agents",
            json={
                "template_id": "react",
                "name": "Asks",
                "sample_prompt": "hi",
                "config": {"reasoning": False},
                "ask_first": ["calculator"],
            },
        ).json()
        run = client.post("/runs", json={"prompt": "Add", "agent_id": agent["id"]}).json()
        request = wait_for_request(client)
        with client.websocket_connect(
            f"{WS_BASE}/runs/{run['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            while True:  # stored spans come first, then the status
                event = ws.receive_json()
                if event["type"] == "run_status":
                    break
            assert event["status"] == "waiting_approval"
            client.post(f"/approvals/{request['approval_id']}", json={"decision": "approve"})
            events = read_until_run_ended(ws)
        statuses = [e["status"] for e in events if e["type"] == "run_status"]
        assert statuses == ["running"]
        assert events[-1]["run"]["status"] == "completed"


def test_a_foreign_page_cannot_let_a_tool_through(tmp_path: Path) -> None:
    script: list[ScriptItem] = [tool_call("calculator", ADD), answer("2")]
    app = create_app(store=Store(tmp_path / "lab.db"), models=fake_models(FakeLLM(script)))
    with TestClient(app, base_url=BASE) as client:
        agent = client.post(
            "/agents",
            json={
                "template_id": "react",
                "name": "Asks",
                "sample_prompt": "hi",
                "config": {"reasoning": False},
                "ask_first": ["calculator"],
            },
        ).json()
        client.post("/runs", json={"prompt": "Add", "agent_id": agent["id"]})
        request = wait_for_request(client)
        url = f"/approvals/{request['approval_id']}"

        evil = client.post(
            url, json={"decision": "approve"}, headers={"origin": "http://evil.example"}
        )
        assert evil.status_code == 403
        assert client.get("/approvals").json() != []  # still open

        assert client.post(url, json={"decision": "maybe"}).status_code == 422
        assert client.post(url, json={"decision": "deny", "reason": "x" * 501}).status_code == 422
        assert client.post(url, json={"decision": "deny"}).status_code == 204
        assert client.post(url, json={"decision": "deny"}).status_code == 404  # no longer open
