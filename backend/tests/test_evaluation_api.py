"""Cases and evaluations through the API (M17, contracts/interfaces.md)."""

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import answer, fake_models, tool_call
from test_api import BASE, GatedLLM

from agent_lab.api import create_app
from agent_lab.evaluation.examples import EXAMPLES
from agent_lab.evaluation.model import Evaluation
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelRef
from agent_lab.store import Store
from agent_lab.village.runner import Village

CASE: dict[str, Any] = {
    "name": "Multiplies",
    "prompt": "a good prompt",
    "checks": [{"kind": "contains", "text": "right"}],
}


def by_prompt(messages: list[Message]) -> ChatResponse:
    return answer("right" if "good" in (messages[-1]["content"] or "") else "wrong")


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def client_for(store: Store, script: list[ScriptItem] | None = None) -> TestClient:
    llm = FakeLLM(script if script is not None else [by_prompt] * 30)
    return TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE)


def new_agent(client: TestClient, name: str = "Mine", **fields: Any) -> str:
    response = client.post(
        "/agents",
        json={
            "template_id": "react",
            "name": name,
            "sample_prompt": "hi",
            "config": {"reasoning": False},
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def wait_for(client: TestClient, eval_id: str) -> dict[str, Any]:
    for _ in range(500):
        body = client.get(f"/evaluations/{eval_id}").json()
        if body["evaluation"]["state"] != "running":
            return body
        time.sleep(0.01)
    raise AssertionError("the evaluation did not end")


def test_a_cases_life_through_the_api(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        created = client.post(f"/agents/{agent}/cases", json=CASE)
        assert created.status_code == 201
        case = created.json()
        assert case["agent_id"] == agent
        assert case["read_only"] is False
        assert case["approvals"] == "deny"
        assert client.get(f"/agents/{agent}/cases").json() == [case]

        changed = client.put(f"/cases/{case['case_id']}", json={**CASE, "name": "Renamed"})
        assert changed.json()["name"] == "Renamed"
        assert client.delete(f"/cases/{case['case_id']}").status_code == 204
        assert client.get(f"/agents/{agent}/cases").json() == []
        assert client.delete(f"/cases/{case['case_id']}").status_code == 404
        assert client.put(f"/cases/{case['case_id']}", json=CASE).status_code == 404


def test_a_bad_case_is_refused_naming_its_field(store: Store) -> None:
    bad = {**CASE, "checks": [{"kind": "matches", "pattern": "("}]}
    with client_for(store) as client:
        agent = new_agent(client)
        response = client.post(f"/agents/{agent}/cases", json=bad)
        assert response.status_code == 422
        assert "invalid pattern" in response.text
        assert client.post("/agents/nobody/cases", json=CASE).status_code == 404


def test_a_duplicate_name_is_refused(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        assert client.post(f"/agents/{agent}/cases", json=CASE).status_code == 422
        example_name = EXAMPLES["react"][0].name
        response = client.post("/agents/react/cases", json={**CASE, "name": example_name})
        assert response.status_code == 422


def test_an_agent_holds_at_most_fifty_cases_counting_examples(store: Store) -> None:
    with client_for(store) as client:
        for i in range(50 - len(EXAMPLES["react"])):
            response = client.post("/agents/react/cases", json={**CASE, "name": f"Case {i}"})
            assert response.status_code == 201
        full = client.post("/agents/react/cases", json={**CASE, "name": "One more"})
        assert full.status_code == 409


def test_a_templates_examples_are_listed_first_and_read_only(store: Store) -> None:
    with client_for(store) as client:
        mine = client.post("/agents/react/cases", json=CASE).json()
        listed = client.get("/agents/react/cases").json()
        assert [c["case_id"] for c in listed] == [
            *(c.case_id for c in EXAMPLES["react"]),
            mine["case_id"],
        ]
        assert listed[0]["read_only"] is True
        example = listed[0]["case_id"]
        assert client.put(f"/cases/{example}", json=CASE).status_code == 409
        assert client.delete(f"/cases/{example}").status_code == 409


def test_a_new_agent_copies_the_cases_it_came_from(store: Store) -> None:
    with client_for(store) as client:
        from_template = new_agent(client, "From template", cases_from="react")
        copied = client.get(f"/agents/{from_template}/cases").json()
        assert [c["name"] for c in copied] == sorted(c.name for c in EXAMPLES["react"])
        assert all(c["read_only"] is False for c in copied)
        assert not {c["case_id"] for c in copied} & {c.case_id for c in EXAMPLES["react"]}

        client.put(f"/cases/{copied[0]['case_id']}", json={**CASE, "name": "Edited"})
        again = client.get("/agents/react/cases").json()
        assert again[0]["name"] == EXAMPLES["react"][0].name  # the template's example is untouched

        from_agent = new_agent(client, "From agent", cases_from=from_template)
        assert len(client.get(f"/agents/{from_agent}/cases").json()) == len(copied)
        empty = new_agent(client, "From nothing")
        assert client.get(f"/agents/{empty}/cases").json() == []
        response = client.post(
            "/agents",
            json={
                "template_id": "react",
                "name": "Bad",
                "sample_prompt": "hi",
                "config": {},
                "cases_from": "nobody",
            },
        )
        assert response.status_code == 422


def test_only_a_templates_examples_are_copied_not_the_owners_cases(store: Store) -> None:
    with client_for(store) as client:
        client.post("/agents/react/cases", json=CASE)
        agent = new_agent(client, cases_from="react")
        names = [c["name"] for c in client.get(f"/agents/{agent}/cases").json()]
        assert CASE["name"] not in names


def test_an_evaluation_runs_and_shows_its_results(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        good = client.post(f"/agents/{agent}/cases", json=CASE).json()
        bad = client.post(
            f"/agents/{agent}/cases", json={**CASE, "name": "Bad", "prompt": "a bad prompt"}
        ).json()

        started = client.post(f"/agents/{agent}/evaluations", json={"repeats": 3})
        assert started.status_code == 202
        eval_id = started.json()["eval_id"]
        body = wait_for(client, eval_id)

        assert body["evaluation"]["state"] == "finished"
        assert body["summary"]["cases"][good["case_id"]]["pass_rate"] == 1.0
        assert body["summary"]["cases"][bad["case_id"]]["pass_rate"] == 0.0
        assert body["summary"]["overall"]["pass_rate"] == 0.5
        assert len(body["attempts"]) == 6
        failed = next(a for a in body["attempts"] if a["outcome"] == "fail")
        assert client.get(f"/runs/{failed['run_id']}").status_code == 200
        assert client.get("/runs").json() == []

        listed = client.get(f"/agents/{agent}/evaluations").json()
        assert [e["evaluation"]["eval_id"] for e in listed] == [eval_id]
        assert listed[0]["summary"]["overall"]["passed"] == 3


@pytest.mark.parametrize("repeats", [0, 11])
def test_repeats_outside_the_range_are_refused(store: Store, repeats: int) -> None:
    with client_for(store) as client:
        response = client.post("/agents/react/evaluations", json={"repeats": repeats})
        assert response.status_code == 422


def test_what_cannot_start_says_why(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        assert client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).status_code == 422
        assert client.post("/agents/nobody/evaluations", json={"repeats": 1}).status_code == 404
        unavailable = client.post(
            "/agents/react/evaluations",
            json={"repeats": 1, "model": {"provider": "openai", "model": "absent"}},
        )
        assert unavailable.status_code == 422


def test_comparing_two_evaluations_of_an_agent(store: Store) -> None:
    script: list[ScriptItem] = [answer("right"), answer("wrong")]
    with client_for(store, script) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        first = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, first)
        second = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, second)

        comparison = client.get(
            "/evaluations/compare", params={"earlier": first, "later": second}
        ).json()
        assert [r["change"] for r in comparison["rows"]] == ["down"]
        assert comparison["earlier"]["eval_id"] == first


def test_evaluations_of_different_agents_cannot_be_compared(store: Store) -> None:
    script: list[ScriptItem] = [
        tool_call("calculator", '{"expression": "1"}'),
        answer("a"),
        tool_call("get_weather", '{"city": "Oslo"}'),
        answer("b"),
        answer("right"),
    ]
    with client_for(store, script) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        first = client.post("/agents/react/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, first)
        second = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, second)
        response = client.get("/evaluations/compare", params={"earlier": first, "later": second})
        assert response.status_code == 422
        unknown = client.get("/evaluations/compare", params={"earlier": first, "later": "nope"})
        assert unknown.status_code == 404


def test_a_second_evaluation_and_deleting_the_agent_wait_for_the_first(store: Store) -> None:
    gate = threading.Event()
    llm = GatedLLM([by_prompt], gate)
    with TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        eval_id = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]

        assert client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).status_code == 409
        assert client.delete(f"/agents/{agent}").status_code == 409

        gate.set()
        wait_for(client, eval_id)
        assert client.delete(f"/agents/{agent}").status_code == 204


def test_stopping_what_is_not_running_is_refused(store: Store) -> None:
    with client_for(store) as client:
        assert client.post("/evaluations/nobody/stop").status_code == 404
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        eval_id = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, eval_id)
        assert client.post(f"/evaluations/{eval_id}/stop").status_code == 409


def test_results_outlive_a_restart_as_interrupted(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
    store.create_evaluation(
        Evaluation(
            eval_id="left",
            agent_id=agent,
            agent_name="Mine",
            config_version="v",
            config={},
            harness={},
            model=ModelRef(provider="local", model="m"),
            repeats=1,
            cases=[],
            state="running",
            started_at=1.0,
        )
    )
    with client_for(store) as client:
        assert client.get("/evaluations/left").json()["evaluation"]["state"] == "interrupted"


def test_deleting_an_agent_deletes_its_results(store: Store) -> None:
    with client_for(store) as client:
        agent = new_agent(client)
        client.post(f"/agents/{agent}/cases", json=CASE)
        eval_id = client.post(f"/agents/{agent}/evaluations", json={"repeats": 1}).json()["eval_id"]
        wait_for(client, eval_id)
        assert client.delete(f"/agents/{agent}").status_code == 204
        assert client.get(f"/evaluations/{eval_id}").status_code == 404


def test_the_notice_says_whether_the_village_shares_a_provider(store: Store) -> None:
    app = create_app(store=store, models=fake_models(FakeLLM([])))
    village: Village = app.state.village
    village.ensure_agents()

    def shares(provider: str) -> bool:
        response = client.get("/evaluations/notice", params={"provider": provider})
        return response.json()["village_shares_provider"]

    with TestClient(app, base_url=BASE) as client:
        assert shares("local") is False  # paused: nothing to share
        village.world["running"] = True
        assert shares("local") is True
        assert shares("openai") is False

        # A villager the owner pinned to another model is on that provider instead.
        agent = store.get_agent(village.world["villagers"][0]["agent_id"])
        assert agent is not None
        store.update_agent(
            agent.agent_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config={**agent.config, "model": "hosted", "provider": "openai"},
        )
        assert shares("openai") is True
        village.world["running"] = False
