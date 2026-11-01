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


def client_for(store: Store, plan: dict[str, list[str | Exception]] | None = None) -> TestClient:
    script: list[ScriptItem] = [responder(plan or {})] * 200
    return TestClient(create_app(store=store, models=fake_models(FakeLLM(script))), base_url=BASE)


def steps(client: TestClient, n: int) -> None:
    for _ in range(n):
        assert client.post("/village/step").status_code == 200


def village_agents(client: TestClient) -> list[dict[str, Any]]:
    return [a for a in client.get("/agents").json() if a["description"].endswith("in the village.")]


def test_state_and_controls(store: Store) -> None:
    with client_for(store) as client:
        state = client.get("/village").json()
        assert (state["tick"], state["running"], state["time"], state["period"]) == (
            0,
            False,
            "04:30",
            "night",
        )
        assert len(state["map"]["rows"]) == 22 and len(state["map"]["places"]) == 6
        assert [h["villager"] for h in state["map"]["homes"]] == ["Hilde", "Jonas", "Greta", "Lina"]
        assert [v["initial"] for v in state["villagers"]] == ["H", "J", "G", "L"]
        jonas = state["villagers"][1]
        assert (jonas["state"], jonas["wake"], jonas["bed"]) == ("asleep", "05:00", "21:00")
        assert {b["villager"] for b in jonas["beliefs"]} == {"Hilde", "Greta", "Lina"}
        assert state["log"] == [] and "inbox" not in jonas and "conversations" not in state
        assert state["calendar"] == {
            "year": 1,
            "season": "spring",
            "day_of_season": 1,
            "festival_in": None,
        }
        assert state["weather"] in ("sun", "clouds", "rain") and state["snow_cover"] is False
        assert (state["sky"], state["dark"]) == ("night", True)
        assert state["growth"] == {
            "fields": {"stage": "resting", "neglected": False},
            "flower_garden": {"stage": "budding"},
        }
        assert state["chronicle"] == []
        for internal in ("tended", "day_record", "festival", "chronicler_agent_id"):
            assert internal not in state

        steps(client, 3)  # 05:00: Jonas wakes and decides
        stepped = client.get("/village").json()
        assert stepped["tick"] == 3 and stepped["villagers"][1]["last_action"] == {"action": "wait"}
        assert stepped["villagers"][1]["state"] == "idle"

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
        listed = client.get("/agents").json()
        reflection = [a for a in listed if a["name"] == "Village reflection"]
        chronicler = [a for a in listed if a["name"] == "Village chronicler"]
    assert len(reflection) == 1 and reflection[0]["template_id"] == "blocks"
    assert len(chronicler) == 1 and chronicler[0]["template_id"] == "blocks"
    assert sorted(a["name"] for a in agents) == [
        "Greta the farmer",
        "Jonas the fisher",
        "Lina the flower girl",
        "Mayor Hilde",
    ]
    assert {a["template_id"] for a in agents} == {"blocks"}


def test_stream_sends_state_on_connect_and_decisions_as_they_start(store: Store) -> None:
    client = client_for(store)
    with client, client.websocket_connect(f"{WS_BASE}/village/stream") as ws:
        assert ws.receive_json()["type"] == "state"
        steps(client, 3)
        # Steps 1 and 2: the state after the step and after Step. Step 3 adds Jonas's decision:
        # its start, and the state once it is applied.
        events = [ws.receive_json() for _ in range(8)]
    started = [e for e in events if e["type"] == "decision_started"]
    assert [e["villager"] for e in started] == ["Jonas"] and started[0]["run_id"]
    assert [e["type"] for e in events].count("state") == 7
    assert events[-1]["state"]["tick"] == 3 and events[-1]["state"]["ticking"] is False


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
    with client_for(store, {"Jonas": [WAIT]}) as client:
        steps(client, 3)
        runs = client.get("/runs").json()
        turns = client.get("/village/villagers/Jonas/turns").json()
    assert runs == [] and len(turns) == 1


# --- a villager's turns ---


def test_turns_per_villager(store: Store) -> None:
    plan: dict[str, list[str | Exception]] = {"Jonas": ['{"action": "move", "place": "harbour"}']}
    with client_for(store, plan) as client:
        steps(client, 39)  # Jonas decides at 05:00 and every 30 minutes after: 13 turns
        turns = client.get("/village/villagers/Jonas/turns").json()
        missing = client.get("/village/villagers/Bob/turns")
    assert missing.status_code == 404
    assert [t["village_tick"] for t in turns] == list(range(39, 2, -3))
    assert {t["villager"] for t in turns} == {"Jonas"}
    first = turns[-1]
    assert first["village_action"] == {"action": "wait", "reason": "unknown place 'harbour'"}
    assert first["prompt"].startswith("Day 1 (day 1 of spring, year 1), 05:00, morning.")
    assert "\nYou are at your home's door." in first["prompt"]


def test_an_edit_applies_from_the_next_decision(store: Store) -> None:
    with client_for(store) as client:
        steps(client, 3)
        agent_id = client.get("/village").json()["villagers"][1]["agent_id"]
        agent = next(a for a in client.get("/agents").json() if a["id"] == agent_id)
        config = agent["config"]
        config["blocks"][0]["system"] += " Always talk about the weather."
        fields = {k: agent[k] for k in ("name", "description", "sample_prompt", "model")}
        assert (
            client.put(f"/agents/{agent_id}", json={**fields, "config": config}).status_code == 200
        )
        steps(client, 3)
        before, after = reversed(client.get("/village/villagers/Jonas/turns").json())
    assert before["config_version"] != after["config_version"]
    assert after["config"]["blocks"][0]["system"].endswith("Always talk about the weather.")


def test_turns_survive_a_replaced_agent(store: Store) -> None:
    with client_for(store) as client:
        steps(client, 3)
        old_id = client.get("/village").json()["villagers"][1]["agent_id"]
        assert client.delete(f"/agents/{old_id}").status_code == 204
        steps(client, 3)  # Jonas cannot act: his agent is gone
        jonas = client.get("/village").json()["villagers"][1]
        assert jonas["last_action"] == {"action": "wait", "reason": "turn failed: unknown agent"}
        client.post("/village/reset")
        new_id = client.get("/village").json()["villagers"][1]["agent_id"]
        steps(client, 3)
        turns = client.get("/village/villagers/Jonas/turns").json()
    assert new_id and new_id != old_id
    assert {t["agent_id"] for t in turns} == {old_id, new_id}  # old and new turns listed


def test_changing_the_pace_keeps_every_villagers_model(store: Store) -> None:
    with client_for(store) as client:
        client.post("/village/start")
        client.post("/village/pause")
        before = {a["id"]: a["config"] for a in client.get("/agents").json()}
        for seconds in (15, 5, 2):
            assert client.put("/village/interval", json={"seconds": seconds}).status_code == 200
        after = {a["id"]: a["config"] for a in client.get("/agents").json()}
    assert after == before  # FR-002
