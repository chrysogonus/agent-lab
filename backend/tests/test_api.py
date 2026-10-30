import threading
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from helpers import answer, json_answer, tool_call
from starlette.websockets import WebSocketDisconnect

from agent_lab.api import create_app
from agent_lab.llm.base import ChatResponse, LLMError, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"  # TestClient ignores base_url for WebSockets
ORIGIN = "http://127.0.0.1:3000"


class GatedLLM(FakeLLM):
    """Blocks every model call until the test opens the gate, so the run is observably live."""

    def __init__(self, script: list[ScriptItem], gate: threading.Event) -> None:
        super().__init__(script)
        self.gate = gate

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        await anyio.to_thread.run_sync(self.gate.wait)
        return await super().chat(
            messages, tools, response_format=response_format, reasoning=reasoning
        )


def read_until_run_ended(ws: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] == "run_ended":
            return events


def final_spans(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["span"]["span_id"]: e["span"] for e in events if e["type"] == "span_ended"}


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def test_live_stream(store: Store) -> None:
    gate = threading.Event()
    llm = GatedLLM([tool_call("calculator", '{"expression": "2+2"}'), answer("4")], gate)
    with TestClient(create_app(store=store, llm=llm), base_url=BASE) as client:
        response = client.post("/runs", json={"prompt": "2+2?"})
        assert response.status_code == 202
        run = response.json()
        assert run["status"] == "running"
        assert {n["id"] for n in run["graph"]["nodes"]} >= {"start", "llm", "end"}

        url = f"{WS_BASE}/runs/{run['run_id']}/stream"
        with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
            first = ws.receive_json()
            assert first["type"] == "span_started"  # the run is blocked on the model
            gate.set()
            events = [first, *read_until_run_ended(ws)]

    assert events[-1]["run"]["status"] == "completed"
    assert events[-1]["run"]["answer"] == "4"
    live = final_spans(events)
    stored = {s.span_id: s.model_dump(mode="json") for s in store.get_spans(run["run_id"])}
    assert live == stored
    assert len(stored) == 7  # root, 2 iterations, 2 llm, 1 tool, end


def test_rejects_empty_prompt(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        assert client.post("/runs", json={"prompt": ""}).status_code == 422


def test_unknown_run_ws(store: Store) -> None:
    client = TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE)
    with client.websocket_connect(f"{WS_BASE}/runs/nope/stream") as ws:
        assert ws.receive_json() == {"type": "error", "message": "unknown run"}
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_rejects_foreign_origin_ws(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect(
                f"{WS_BASE}/runs/x/stream", headers={"origin": "https://evil.test"}
            ),
        ):
            pass
        assert exc.value.code == 1008


def test_rejects_foreign_host(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        response = client.post("/runs", json={"prompt": "hi"}, headers={"host": "evil.test"})
        assert response.status_code == 400


def test_cors(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        preflight = {"access-control-request-method": "POST"}
        ok = client.options("/runs", headers={"origin": ORIGIN, **preflight})
        assert ok.headers["access-control-allow-origin"] == ORIGIN
        bad = client.options("/runs", headers={"origin": "https://evil.test", **preflight})
        assert "access-control-allow-origin" not in bad.headers


def test_replay_matches_live(tmp_path: Path) -> None:
    path = tmp_path / "lab.db"
    llm = FakeLLM([tool_call("get_weather", '{"city": "Oslo"}'), answer("cold")])
    with TestClient(create_app(store=Store(path), llm=llm), base_url=BASE) as client:
        run_id = client.post("/runs", json={"prompt": "Oslo?"}).json()["run_id"]
        with client.websocket_connect(f"{WS_BASE}/runs/{run_id}/stream") as ws:
            live = final_spans(read_until_run_ended(ws))

    # A fresh store on the same file stands in for a backend restart.
    with TestClient(create_app(store=Store(path), llm=FakeLLM([])), base_url=BASE) as client:
        detail = client.get(f"/runs/{run_id}").json()
        assert detail["run"]["status"] == "completed"
        assert {s["span_id"]: s for s in detail["spans"]} == live
        with client.websocket_connect(f"{WS_BASE}/runs/{run_id}/stream") as ws:
            replay = read_until_run_ended(ws)
        assert final_spans(replay) == live
        assert replay[-1]["run"]["answer"] == "cold"
        assert client.get("/runs/nope").status_code == 404


def test_list_runs(store: Store) -> None:
    llm = FakeLLM([answer("a"), answer("b")])
    with TestClient(create_app(store=store, llm=llm), base_url=BASE) as client:
        first = client.post("/runs", json={"prompt": "one"}).json()["run_id"]
        second = client.post("/runs", json={"prompt": "two"}).json()["run_id"]
        listed = [r["run_id"] for r in client.get("/runs").json()]
        assert listed == [second, first]


def test_list_agents(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        agents = client.get("/agents").json()
    assert [a["id"] for a in agents] == [
        "react",
        "chain",
        "routing",
        "parallel",
        "orchestrator",
        "evaluator",
    ]
    for agent in agents:
        assert agent["name"] and agent["description"] and agent["sample_prompt"]
        assert {"start", "end"} <= {n["id"] for n in agent["graph"]["nodes"]}


def test_post_run_defaults_to_react(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([answer("hi")])), base_url=BASE) as client:
        run = client.post("/runs", json={"prompt": "hi"}).json()
    assert run["agent_id"] == "react"
    assert run["config"]["reasoning"] is True


def test_unknown_agent_id_422(store: Store) -> None:
    with TestClient(create_app(store=store, llm=FakeLLM([])), base_url=BASE) as client:
        response = client.post("/runs", json={"prompt": "hi", "agent_id": "nope"})
    assert response.status_code == 422


def test_workflow_run_streams(store: Store) -> None:
    llm = FakeLLM([json_answer({"label": "general"}), answer("Paris")])
    with TestClient(create_app(store=store, llm=llm), base_url=BASE) as client:
        run = client.post("/runs", json={"prompt": "Capital of France?", "agent_id": "routing"})
        run = run.json()
        with client.websocket_connect(f"{WS_BASE}/runs/{run['run_id']}/stream") as ws:
            events = read_until_run_ended(ws)

    ended_run = events[-1]["run"]
    assert (ended_run["status"], ended_run["answer"]) == ("completed", "Paris")
    assert (run["agent_id"], run["config"]["reasoning"]) == ("routing", False)
    nodes = {n["id"] for n in run["graph"]["nodes"]}
    spans = final_spans(events).values()
    assert {s["node_id"] for s in spans} <= nodes
    assert {(s["agent_id"], s["config_version"]) for s in spans} == {
        ("routing", run["config_version"])
    }


def test_workflow_llm_error_ends_run(store: Store) -> None:
    llm = FakeLLM([LLMError("HTTP 500: boom")])
    with TestClient(create_app(store=store, llm=llm), base_url=BASE) as client:
        run_id = client.post("/runs", json={"prompt": "bottle", "agent_id": "chain"}).json()
        with client.websocket_connect(f"{WS_BASE}/runs/{run_id['run_id']}/stream") as ws:
            events = read_until_run_ended(ws)

    assert events[-1]["run"]["status"] == "error"
    spans = list(final_spans(events).values())
    assert all(s["ended_at"] is not None for s in spans)
    assert {s["error"] for s in spans} == {"LLMError: HTTP 500: boom"}


def respond(messages: list[Message]) -> ChatResponse:
    """Answers any call of the routing or parallel workflow, in whatever order they come."""
    system = messages[0]["content"]
    if system.startswith("Classify"):
        return json_answer({"label": "general"})
    return answer(system[:20])


def test_two_workflow_runs_stream_independently(store: Store) -> None:
    llm = FakeLLM([respond] * 6, delay=0.02)  # routing: 2 calls, parallel: 3 reviews + merge
    with TestClient(create_app(store=store, llm=llm), base_url=BASE) as client:
        runs = [
            client.post("/runs", json={"prompt": "hi", "agent_id": agent}).json()
            for agent in ("routing", "parallel")
        ]
        streams: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            with client.websocket_connect(f"{WS_BASE}/runs/{run['run_id']}/stream") as ws:
                streams[run["run_id"]] = read_until_run_ended(ws)

    for run in runs:
        events = streams[run["run_id"]]
        assert events[-1]["run"]["status"] == "completed"
        spans = final_spans(events).values()
        assert {(s["run_id"], s["agent_id"]) for s in spans} == {(run["run_id"], run["agent_id"])}
