"""The village through the API: controls, stream, agents (US1); turns per villager (US3)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import fake_models
from starlette.websockets import WebSocketDisconnect
from test_api import BASE, WS_BASE
from test_village_runner import WAIT, responder

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def client_for(
    store: Store, plan: dict[str, list[str | Exception]] | None = None, ticks: int = 3
) -> TestClient:
    script: list[ScriptItem] = [responder(plan or {})] * (4 * ticks)
    return TestClient(create_app(store=store, models=fake_models(FakeLLM(script))), base_url=BASE)


def village_agents(client: TestClient) -> list[dict[str, Any]]:
    return [a for a in client.get("/agents").json() if a["description"].endswith("in the village.")]


def test_state_and_controls(store: Store) -> None:
    with client_for(store) as client:
        state = client.get("/village").json()
        assert (state["tick"], state["running"], state["time"], state["period"]) == (
            0,
            False,
            "06:00",
            "morning",
        )
        assert len(state["map"]["rows"]) == 15 and len(state["map"]["places"]) == 6
        assert [v["initial"] for v in state["villagers"]] == ["H", "J", "G", "L"]

        stepped = client.post("/village/step").json()
        assert stepped["tick"] == 1 and stepped["villagers"][0]["last_action"] == {"action": "wait"}

        assert client.put("/village/interval", json={"seconds": 0}).status_code == 422
        assert client.put("/village/interval", json={"seconds": 31}).status_code == 422
        assert client.put("/village/interval", json={"seconds": 2}).json()["interval"] == 2

        started = client.post("/village/start").json()
        assert started["running"] is True
        assert client.post("/village/step").status_code == 409  # never while running
        paused = client.post("/village/pause").json()
        assert (paused["running"], paused["paused_reason"]) == (False, "owner")

        reset = client.post("/village/reset").json()
        assert (reset["tick"], reset["running"]) == (0, False)


def test_start_creates_the_villager_agents_once(store: Store) -> None:
    with client_for(store) as client:
        client.post("/village/start")
        client.post("/village/pause")
        client.post("/village/start")
        client.post("/village/pause")
        agents = village_agents(client)
    assert sorted(a["name"] for a in agents) == [
        "Greta the farmer",
        "Jonas the fisher",
        "Lina the flower girl",
        "Mayor Hilde",
    ]
    assert {a["template_id"] for a in agents} == {"blocks"}


def test_stream_sends_state_on_connect_and_after_a_step(store: Store) -> None:
    client = client_for(store)
    with client, client.websocket_connect(f"{WS_BASE}/village/stream") as ws:
        assert ws.receive_json()["type"] == "state"
        client.post("/village/step")
        events = [ws.receive_json() for _ in range(2)]
    assert events[0] == {"type": "tick_started", "tick": 0}
    assert events[1]["type"] == "state" and events[1]["state"]["tick"] == 1


def test_stream_refuses_foreign_origin(store: Store) -> None:
    client = client_for(store)
    foreign = {"origin": "http://evil.test"}
    with (
        client,
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(f"{WS_BASE}/village/stream", headers=foreign) as ws,
    ):
        ws.receive_json()
    assert exc.value.code == 1008


def test_turns_stay_out_of_the_main_list(store: Store) -> None:
    with client_for(store, {"Hilde": [WAIT]}) as client:
        client.post("/village/step")
        runs = client.get("/runs").json()
    assert runs == []
