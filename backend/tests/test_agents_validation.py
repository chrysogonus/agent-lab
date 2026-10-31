"""Every invalid input is rejected with a 422 naming its field, and nothing is stored (US3-4)."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api import BASE

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM
from agent_lab.store import Store

Body = dict[str, Any]


def config_of(body: Body) -> Body:
    return body["config"]


def steps(n: int) -> list[Body]:
    return [{"name": f"s{i}", "prompt": "p"} for i in range(n)]


def routes(n: int) -> list[Body]:
    return [{"name": f"r{i}", "description": "d", "prompt": "p"} for i in range(n)]


# (case, template, change to a valid body, expected loc of the first error)
CASES: list[tuple[str, str, Callable[[Body], None], list[str | int]]] = [
    (
        "empty prompt",
        "evaluator",
        lambda b: config_of(b).update(generator_prompt="  "),
        ["config", "generator_prompt"],
    ),
    ("empty name", "react", lambda b: b.update(name=" "), ["name"]),
    ("61-character name", "react", lambda b: b.update(name="x" * 61), ["name"]),
    ("no chain steps", "chain", lambda b: config_of(b).update(steps=[]), ["config", "steps"]),
    ("7 chain steps", "chain", lambda b: config_of(b).update(steps=steps(7)), ["config", "steps"]),
    (
        "duplicate step name",
        "chain",
        lambda b: config_of(b).update(steps=[*steps(2), {"name": "s0", "prompt": "p"}]),
        ["config", "steps"],
    ),
    (
        "reserved name",
        "chain",
        lambda b: config_of(b)["steps"][0].update(name="start"),
        ["config", "steps", 0, "name"],
    ),
    (
        "uppercase name",
        "routing",
        lambda b: config_of(b)["routes"][0].update(name="Math"),
        ["config", "routes", 0, "name"],
    ),
    (
        "1 route",
        "routing",
        lambda b: config_of(b).update(routes=routes(1), fallback="r0"),
        ["config", "routes"],
    ),
    (
        "7 routes",
        "routing",
        lambda b: config_of(b).update(routes=routes(7), fallback="r0"),
        ["config", "routes"],
    ),
    (
        "unknown tool",
        "routing",
        lambda b: config_of(b)["routes"][1].update(tool="read_file"),
        ["config", "routes", 1, "tool"],
    ),
    (
        "fallback not a route",
        "routing",
        lambda b: config_of(b).update(fallback="sports"),
        ["config"],
    ),
    (
        "7 aspects",
        "parallel",
        lambda b: config_of(b).update(aspects={f"a{i}": "f" for i in range(7)}),
        ["config", "aspects"],
    ),
    (
        "0 subtasks",
        "orchestrator",
        lambda b: config_of(b).update(max_subtasks=0),
        ["config", "max_subtasks"],
    ),
    (
        "7 subtasks",
        "orchestrator",
        lambda b: config_of(b).update(max_subtasks=7),
        ["config", "max_subtasks"],
    ),
    (
        "6 rounds",
        "evaluator",
        lambda b: config_of(b).update(max_rounds=6),
        ["config", "max_rounds"],
    ),
    (
        "11 iterations",
        "react",
        lambda b: config_of(b).update(max_iterations=11),
        ["config", "max_iterations"],
    ),
    (
        "unknown react tool",
        "react",
        lambda b: config_of(b).update(tools=["read_file"]),
        ["config", "tools"],
    ),
    ("unknown template", "react", lambda b: b.update(template_id="nope"), ["template_id"]),
    ("model key", "react", lambda b: config_of(b).update(model="other"), ["config", "model"]),
]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(store=Store(tmp_path / "lab.db"), llm=FakeLLM([])), base_url=BASE)


def valid_body(client: TestClient, template_id: str) -> Body:
    template = next(a for a in client.get("/agents").json() if a["id"] == template_id)
    return {
        "template_id": template_id,
        "name": "Mine",
        "description": "",
        "sample_prompt": "hi",
        "config": deepcopy(template["config"]),
    }


@pytest.mark.parametrize(("case", "template_id", "change", "loc"), CASES, ids=[c[0] for c in CASES])
def test_rejected_on_create_and_update(
    client: TestClient,
    case: str,
    template_id: str,
    change: Callable[[Body], None],
    loc: list[str | int],
) -> None:
    with client:
        saved = client.post("/agents", json={**valid_body(client, template_id), "name": "Kept"})
        assert saved.status_code == 201
        before = client.get("/agents").json()

        body = valid_body(client, template_id)
        change(body)
        created = client.post("/agents", json=body)
        assert created.status_code == 422, case
        assert created.json()["detail"][0]["loc"] == ["body", *loc]
        if loc != ["template_id"]:  # updates carry no template id: it never changes
            update = {k: v for k, v in body.items() if k != "template_id"}
            updated = client.put(f"/agents/{saved.json()['id']}", json=update)
            assert updated.status_code == 422, case
            assert updated.json()["detail"][0]["loc"] == ["body", *loc]
        assert client.get("/agents").json() == before


def test_name_in_use_ignoring_case_and_spaces(client: TestClient) -> None:
    with client:
        first = client.post("/agents", json=valid_body(client, "chain"))
        other = client.post("/agents", json={**valid_body(client, "chain"), "name": "Other"})
        before = client.get("/agents").json()

        clash = client.post("/agents", json={**valid_body(client, "react"), "name": "  mINE "})
        rename = valid_body(client, "chain")
        del rename["template_id"]
        renamed = client.put(f"/agents/{other.json()['id']}", json={**rename, "name": "mine"})

        assert first.status_code == other.status_code == 201
        for response in (clash, renamed):
            assert response.status_code == 422
            assert response.json()["detail"] == [
                {"loc": ["body", "name"], "msg": "name already in use", "type": "value_error"}
            ]
        assert client.get("/agents").json() == before
