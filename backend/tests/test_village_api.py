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
    assert events[1]["state"]["ticking"] is False  # the published state is after the tick


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


# --- US3: a villager's turns ---


def test_turns_per_villager(store: Store) -> None:
    plan: dict[str, list[str | Exception]] = {"Jonas": ['{"action": "move", "place": "harbour"}']}
    with client_for(store, plan, ticks=13) as client:
        for _ in range(13):  # more than ten events after the invalid answer
            client.post("/village/step")
        turns = client.get("/village/villagers/Jonas/turns").json()
        missing = client.get("/village/villagers/Bob/turns")
    assert missing.status_code == 404
    assert len(turns) == 13 and [t["village_tick"] for t in turns] == list(range(12, -1, -1))
    assert {t["villager"] for t in turns} == {"Jonas"}
    first = turns[-1]
    assert first["village_action"] == {"action": "wait", "reason": "unknown place 'harbour'"}
    assert first["prompt"].startswith("Day 1, 06:00, morning.")


def test_an_edit_applies_from_the_next_tick(store: Store) -> None:
    with client_for(store, ticks=2) as client:
        client.post("/village/step")
        agent_id = client.get("/village").json()["villagers"][0]["agent_id"]
        agent = next(a for a in client.get("/agents").json() if a["id"] == agent_id)
        config = agent["config"]
        config["blocks"][0]["system"] += " Always talk about the weather."
        fields = {k: agent[k] for k in ("name", "description", "sample_prompt", "model")}
        assert (
            client.put(f"/agents/{agent_id}", json={**fields, "config": config}).status_code == 200
        )
        client.post("/village/step")
        before, after = reversed(client.get("/village/villagers/Hilde/turns").json())
    assert before["config_version"] != after["config_version"]
    assert after["config"]["blocks"][0]["system"].endswith("Always talk about the weather.")


def test_turns_survive_a_replaced_agent(store: Store) -> None:
    with client_for(store, ticks=3) as client:
        client.post("/village/step")
        old_id = client.get("/village").json()["villagers"][1]["agent_id"]
        assert client.delete(f"/agents/{old_id}").status_code == 204
        client.post("/village/step")  # Jonas cannot act: his agent is gone
        jonas = client.get("/village").json()["villagers"][1]
        assert jonas["last_action"] == {"action": "wait", "reason": "turn failed: unknown agent"}
        client.post("/village/reset")
        new_id = client.get("/village").json()["villagers"][1]["agent_id"]
        client.post("/village/step")
        turns = client.get("/village/villagers/Jonas/turns").json()
    assert new_id and new_id != old_id
    assert {t["agent_id"] for t in turns} == {old_id, new_id}  # old and new turns listed
