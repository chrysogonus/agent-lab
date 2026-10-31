"""Custom agents through the API: create, list, update, preview, run (US1, US3)."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import answer
from test_api import BASE, ORIGIN, WS_BASE, final_spans, read_until_run_ended
from test_templates import CASES

from agent_lab.api import create_app
from agent_lab.graph import Graph
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store

# Which prompt each template's test changes, as (path into the config, request it must reach).
CHANGED_PROMPT: dict[str, tuple[str | int, ...]] = {
    "react": ("system_prompt",),
    "chain": ("steps", 0, "prompt"),
    "routing": ("router_prompt",),
    "parallel": ("merge_prompt",),
    "orchestrator": ("worker_prompt",),
    "evaluator": ("generator_prompt",),
}
RUN_CASE = {
    "react": "react",
    "chain": "chain",
    "routing": "routing-general",
    "parallel": "parallel",
    "orchestrator": "orchestrator",
    "evaluator": "evaluator",
}


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def client_for(store: Store, script: list[ScriptItem] | None = None) -> tuple[TestClient, FakeLLM]:
    llm = FakeLLM(list(script or []))
    return TestClient(create_app(store=store, llm=llm), base_url=BASE), llm


def template(client: TestClient, template_id: str) -> dict[str, Any]:
    return next(a for a in client.get("/agents").json() if a["id"] == template_id)


def set_path(config: dict[str, Any], path: tuple[str | int, ...], value: str) -> None:
    target: Any = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def new_agent(client: TestClient, template_id: str, **changes: Any) -> dict[str, Any]:
    base = template(client, template_id)
    body = {
        "template_id": template_id,
        "name": f"My {template_id}",
        "description": "mine",
        "sample_prompt": base["sample_prompt"],
        "config": deepcopy(base["config"]),
        **changes,
    }
    response = client.post("/agents", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def run_to_end(client: TestClient, agent_id: str, prompt: str) -> tuple[dict[str, Any], list[Any]]:
    run = client.post("/runs", json={"prompt": prompt, "agent_id": agent_id})
    assert run.status_code == 202, run.json()
    with client.websocket_connect(f"{WS_BASE}/runs/{run.json()['run_id']}/stream") as ws:
        events = read_until_run_ended(ws)
    return events[-1]["run"], list(final_spans(events).values())


@pytest.mark.parametrize("template_id", list(CHANGED_PROMPT))
def test_customize_each_template(store: Store, template_id: str) -> None:
    _, prompt, script = CASES[RUN_CASE[template_id]]
    client, llm = client_for(store, script)
    with client:
        config = deepcopy(template(client, template_id)["config"])
        set_path(config, CHANGED_PROMPT[template_id], "CHANGED PROMPT")
        agent = new_agent(client, template_id, config=config)
        run, spans = run_to_end(client, agent["id"], prompt)

    assert any("CHANGED PROMPT" in (call[0]["content"] or "") for call in llm.calls)
    assert run["status"] == "completed"
    assert (run["agent_id"], run["agent_name"], run["template_id"]) == (
        agent["id"],
        f"My {template_id}",
        template_id,
    )
    graph = Graph.model_validate(run["graph"])
    assert {s["node_id"] for s in spans} <= graph.node_ids()
    declared = {(e.source, e.target) for e in graph.edges}
    taken = {(src, s["node_id"]) for s in spans for src in s["attributes"].get("lab.came_from", [])}
    assert taken <= declared
    assert {s["agent_id"] for s in spans} == {agent["id"]}


def test_update_agent(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        agent = new_agent(client, "evaluator")
        config = {**agent["config"], "max_rounds": 5}
        body = {"name": "Renamed", "description": "", "sample_prompt": "x", "config": config}
        updated = client.put(f"/agents/{agent['id']}", json=body)
        listed = [a for a in client.get("/agents").json() if a["kind"] == "custom"]
    assert updated.status_code == 200
    assert listed == [updated.json()]
    assert (listed[0]["name"], listed[0]["config"]["max_rounds"]) == ("Renamed", 5)


def test_template_is_read_only(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        config = template(client, "chain")["config"]
        body = {"name": "x", "sample_prompt": "x", "config": config}
        assert client.put("/agents/chain", json=body).status_code == 404
        assert client.put("/agents/custom-missing", json=body).status_code == 404


def test_list_agents_order_and_kinds(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        new_agent(client, "chain", name="beta")
        new_agent(client, "routing", name="Alpha")
        agents = client.get("/agents").json()
    assert [(a["id"], a["kind"]) for a in agents[:6]] == [(t, "template") for t in CHANGED_PROMPT]
    assert [(a["name"], a["kind"], a["template_id"]) for a in agents[6:]] == [
        ("Alpha", "custom", "routing"),
        ("beta", "custom", "chain"),
    ]
    assert all("model" not in a["config"] for a in agents)


def test_tools(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        tools = client.get("/tools").json()
    assert [t["name"] for t in tools] == ["calculator", "get_weather"]
    assert all(t["description"] for t in tools)


def test_graph_preview_matches_saved_graph(store: Store) -> None:
    """The builder's preview is the graph the next run stores (SC-003)."""
    client, _ = client_for(store, [answer("- a\n- b\n- c"), answer("2"), answer("3"), answer("4")])
    with client:
        config = deepcopy(template(client, "chain")["config"])
        config["steps"].append({"name": "german", "prompt": "Translate into German."})
        preview = client.post("/graph", json={"template_id": "chain", "config": config})
        agent = new_agent(client, "chain", config=config)
        run, _ = run_to_end(client, agent["id"], "A bottle")
    assert preview.status_code == 200
    assert preview.json() == agent["graph"] == run["graph"]
    assert "german" in {n["id"] for n in preview.json()["nodes"]}


def test_preview_reports_field_errors(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        config = deepcopy(template(client, "routing")["config"])
        config["routes"][1]["name"] = "Bad Name"
        response = client.post("/graph", json={"template_id": "routing", "config": config})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "config", "routes", 1, "name"]


def test_model_key_rejected(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        config = {**template(client, "evaluator")["config"], "model": "other"}
        body = {
            "template_id": "evaluator",
            "name": "x",
            "sample_prompt": "x",
            "config": config,
        }
        response = client.post("/agents", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "config", "model"]


def test_custom_run_uses_server_model(store: Store) -> None:
    client, llm = client_for(store, [answer("ok")])
    with client:
        agent = new_agent(client, "react")
        run, _ = run_to_end(client, agent["id"], "hi")
    assert run["config"]["model"] == llm.model


def test_cors_allows_put_delete(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        for method in ("PUT", "DELETE"):
            response = client.options(
                "/agents/x",
                headers={"Origin": ORIGIN, "Access-Control-Request-Method": method},
            )
            assert response.status_code == 200, method
