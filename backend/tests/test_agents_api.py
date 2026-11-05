"""Custom agents through the API: create, list, update, preview, run, model choice."""

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import answer, fake_models, tool_call
from test_api import BASE, ORIGIN, WS_BASE, GatedLLM, final_spans, read_until_run_ended
from test_templates import CASES

from agent_lab.api import create_app
from agent_lab.graph import Graph
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelEntry, ModelRef, Models
from agent_lab.llm.openai_compat import OpenAICompatClient
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
    return TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE), llm


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
    assert [t["server"] for t in tools] == ["lab", "lab"]
    assert all(t["description"] for t in tools)
    # The builder shows one argument field per parameter of a tool block.
    assert [list(t["parameters"]["properties"]) for t in tools] == [["expression"], ["city"]]


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


def test_delete_keeps_runs(store: Store) -> None:
    """Deleting an agent leaves its runs listed and replayable with their snapshot (US3-3)."""
    client, _ = client_for(store, [answer("first")])
    with client:
        agent = new_agent(client, "react", name="Short-lived")
        run, _ = run_to_end(client, agent["id"], "hi")
        assert client.delete(f"/agents/{agent['id']}").status_code == 204
        assert agent["id"] not in [a["id"] for a in client.get("/agents").json()]
        [listed] = client.get("/runs").json()
        detail = client.get(f"/runs/{run['run_id']}").json()
        assert client.delete(f"/agents/{agent['id']}").status_code == 404
        assert client.delete("/agents/react").status_code == 404
    assert (listed["agent_id"], listed["agent_name"]) == (agent["id"], "Short-lived")
    assert detail["run"]["graph"] == run["graph"]
    assert detail["run"]["config"] == run["config"]
    assert detail["spans"]


def test_delete_while_running(store: Store) -> None:
    gate = threading.Event()
    llm = GatedLLM([answer("late")], gate)
    with TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE) as client:
        agent = new_agent(client, "react")
        run = client.post("/runs", json={"prompt": "hi", "agent_id": agent["id"]}).json()
        assert client.delete(f"/agents/{agent['id']}").status_code == 204
        gate.set()
        with client.websocket_connect(f"{WS_BASE}/runs/{run['run_id']}/stream") as ws:
            ended = read_until_run_ended(ws)[-1]["run"]
    assert (ended["status"], ended["answer"], ended["agent_name"]) == (
        "completed",
        "late",
        "My react",
    )


def test_edit_changes_version_not_history(store: Store) -> None:
    """Earlier runs keep the config and version they ran with (US3-1, SC-004)."""
    client, _ = client_for(store, [answer("one"), answer("two")])
    with client:
        agent = new_agent(client, "react")
        before, _ = run_to_end(client, agent["id"], "hi")
        config = {**agent["config"], "system_prompt": "Be terse."}
        body = {"name": agent["name"], "sample_prompt": "x", "config": config}
        assert client.put(f"/agents/{agent['id']}", json=body).status_code == 200
        after, _ = run_to_end(client, agent["id"], "hi")
        stored_before = client.get(f"/runs/{before['run_id']}").json()["run"]
    assert before["config_version"] != after["config_version"]
    assert stored_before["config"] == before["config"]
    assert stored_before["config"]["system_prompt"] != "Be terse."
    assert after["config"]["system_prompt"] == "Be terse."


def test_duplicate_is_independent(store: Store) -> None:
    """A duplicate is a new agent with copied fields; editing one leaves the other (US3-2)."""
    client, _ = client_for(store)
    with client:
        original = new_agent(client, "parallel", name="Reviewer")
        copy = new_agent(
            client,
            "parallel",
            name="Reviewer (copy)",
            config=deepcopy(original["config"]),
        )
        config = {**copy["config"], "merge_prompt": "Only the top issue."}
        body = {"name": copy["name"], "sample_prompt": "x", "config": config}
        client.put(f"/agents/{copy['id']}", json=body)
        agents = {a["id"]: a for a in client.get("/agents").json()}
    assert copy["id"] != original["id"]
    assert agents[original["id"]]["config"] == original["config"]
    assert agents[copy["id"]]["config"]["merge_prompt"] == "Only the top issue."


# --- M4: model choice (US1) ---

LUNA = {"provider": "openai", "model": "gpt-6-luna"}


def two_models(
    store: Store,
    local_script: list[ScriptItem] | None = None,
    openai_script: list[ScriptItem] | None = None,
    **options: Any,
) -> tuple[TestClient, FakeLLM, FakeLLM]:
    local = FakeLLM(list(local_script or []))
    openai = FakeLLM(list(openai_script or []), model="gpt-6-luna")
    app = create_app(store=store, models=fake_models(local, openai, **options))
    return TestClient(app, base_url=BASE), local, openai


def llm_models(spans: list[Any]) -> set[tuple[str, str]]:
    return {
        (s["attributes"]["gen_ai.provider.name"], s["attributes"]["gen_ai.request.model"])
        for s in spans
        if s["kind"] == "llm"
    }


def test_models_list(store: Store) -> None:
    client, _, _ = two_models(store)
    with client:
        models = client.get("/models").json()
    assert models == [
        {
            "provider": "local",
            "provider_label": "Local",
            "model": "fake-model",
            "external": False,
            "available": True,
            "unavailable_reason": None,
            "default": True,
        },
        {
            "provider": "openai",
            "provider_label": "OpenAI",
            "model": "gpt-6-luna",
            "external": True,
            "available": True,
            "unavailable_reason": None,
            "default": False,
        },
    ]


def test_pin_openai_model(store: Store) -> None:
    _, prompt, script = CASES["routing-general"]
    client, local, openai = two_models(store, openai_script=script)
    with client:
        agent = new_agent(client, "routing", model=LUNA)
        listed = template(client, agent["id"])
        run, spans = run_to_end(client, agent["id"], prompt)
    assert agent["model"] == listed["model"] == LUNA
    assert "model" not in agent["config"] and "provider" not in agent["config"]
    assert local.calls == [] and len(openai.calls) == 2
    assert run["status"] == "completed"
    assert (run["config"]["provider"], run["config"]["model"]) == ("openai", "gpt-6-luna")
    assert llm_models(spans) == {("openai", "gpt-6-luna")}


def test_m3_agent_is_default(store: Store) -> None:
    client, local, _ = two_models(store, local_script=[answer("a"), answer("b")])
    with client:
        config = deepcopy(template(client, "react")["config"])
        old = store.create_agent(  # stored as by M3: no model key
            template_id="react", name="Old", description="", sample_prompt="hi", config=config
        )
        info = template(client, old.agent_id)
        run, spans = run_to_end(client, old.agent_id, "hi")
        template_run, _ = run_to_end(client, "react", "hi")
    assert info["model"] is None
    assert "provider" not in run["config"] and run["config"]["model"] == local.model
    assert run["config_version"] == template_run["config_version"]  # same config, M3 hash
    assert llm_models(spans) == {("local", "fake-model")}


def test_default_agent_follows_default(store: Store) -> None:
    client, _, _ = two_models(store, local_script=[answer("a")])
    with client:
        agent = new_agent(client, "react")
        first, _ = run_to_end(client, agent["id"], "hi")
    # The owner changes DEFAULT_MODEL and restarts: same database, new catalog.
    luna = ModelRef.model_validate(LUNA)
    restarted, _, _ = two_models(store, openai_script=[answer("b")], default=luna)
    with restarted as client:
        second, spans = run_to_end(client, agent["id"], "hi")
    assert agent["model"] is None
    assert (first["config"]["model"], second["config"]["model"]) == ("fake-model", "gpt-6-luna")
    assert second["config"]["provider"] == "openai"
    assert first["config_version"] != second["config_version"]
    assert llm_models(spans) == {("openai", "gpt-6-luna")}


def test_versions_differ_by_model(store: Store) -> None:
    client, _, _ = two_models(store, local_script=[answer("a")], openai_script=[answer("b")])
    with client:
        default = new_agent(client, "react")
        pinned = new_agent(client, "react", name="Pinned", model=LUNA)
        a, _ = run_to_end(client, default["id"], "hi")
        b, _ = run_to_end(client, pinned["id"], "hi")
    assert default["config"] == pinned["config"]
    assert a["config_version"] != b["config_version"]


def test_template_runs_on_default(store: Store) -> None:
    luna = ModelRef.model_validate(LUNA)
    client, local, openai = two_models(store, openai_script=[answer("b")], default=luna)
    with client:
        info = template(client, "react")
        run, spans = run_to_end(client, "react", "hi")
    assert info["model"] is None
    assert local.calls == [] and len(openai.calls) == 1
    assert run["config"]["provider"] == "openai"
    assert llm_models(spans) == {("openai", "gpt-6-luna")}


def test_runs_on_two_providers_concurrently(store: Store) -> None:
    local = FakeLLM([answer("a")], delay=0.3)
    openai = FakeLLM([answer("b")], model="gpt-6-luna", delay=0.3)
    app = create_app(store=store, models=fake_models(local, openai))
    with TestClient(app, base_url=BASE) as client:
        pinned = new_agent(client, "react", model=LUNA)
        ids = [
            client.post("/runs", json={"prompt": "hi", "agent_id": agent_id}).json()["run_id"]
            for agent_id in ("react", pinned["id"])
        ]
        runs: list[dict[str, Any]] = []
        for run_id in ids:
            with client.websocket_connect(f"{WS_BASE}/runs/{run_id}/stream") as ws:
                runs.append(read_until_run_ended(ws)[-1]["run"])
    assert [r["status"] for r in runs] == ["completed", "completed"]
    assert [r["answer"] for r in runs] == ["a", "b"]
    first, second = runs
    assert second["started_at"] < first["ended_at"]  # the two runs overlapped (FR-003)


def test_openai_request_over_http(store: Store) -> None:
    """A pinned agent's model calls go to the OpenAI endpoint with its key and model id."""
    seen: list[httpx.Request] = []
    replies = iter(['{"label": "general"}', "Paris"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    openai = OpenAICompatClient(
        base_url="https://openai.test/v1",
        model="gpt-6-luna",
        api_key="sk-test-0123456789abcdef",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        provider="openai",
        reasoning_off={"reasoning_effort": "none"},
    )
    local = FakeLLM([], provider="local")
    local_ref = ModelRef(provider="local", model=local.model)
    models = Models(
        [
            ModelEntry(local_ref, False, None, local),
            ModelEntry(ModelRef.model_validate(LUNA), True, None, openai),
        ],
        local_ref,
    )
    with TestClient(create_app(store=store, models=models), base_url=BASE) as client:
        agent = new_agent(client, "routing", model=LUNA)
        run, _ = run_to_end(client, agent["id"], "Capital of France?")
    assert (run["status"], run["answer"]) == ("completed", "Paris")
    assert len(seen) == 2
    for request in seen:
        assert str(request.url) == "https://openai.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test-0123456789abcdef"
        assert json.loads(request.content)["model"] == "gpt-6-luna"


# --- Unavailable models (US3) ---


def test_models_list_marks_missing_key(store: Store) -> None:
    client, _, _ = two_models(store, openai_key=False)
    with client:
        luna = client.get("/models").json()[1]
    assert (luna["available"], luna["unavailable_reason"]) == (False, "no API key")


def test_save_rejects_unavailable_model(store: Store) -> None:
    client, _, _ = two_models(store, openai_key=False)
    with client:
        base = template(client, "react")
        body = {
            "template_id": "react",
            "name": "Mine",
            "description": "",
            "sample_prompt": "hi",
            "config": base["config"],
            "model": LUNA,
        }
        response = client.post("/agents", json=body)
        custom = [a for a in client.get("/agents").json() if a["kind"] == "custom"]
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "loc": ["body", "model"],
            "msg": "model openai/gpt-6-luna is not available: no API key",
            "type": "value_error",
        }
    ]
    assert custom == []


@pytest.mark.parametrize(
    ("removed", "message"),
    [
        ("key", "model openai/gpt-6-luna is not available: no API key"),
        ("model", "model openai/gpt-6-luna is not configured"),
    ],
)
def test_run_rejected_when_pinned_model_unusable(store: Store, removed: str, message: str) -> None:
    client, _, _ = two_models(store)
    with client:
        agent = new_agent(client, "react", model=LUNA)
    # Restarted after removing the key, or the model, from the configuration.
    if removed == "model":
        app = create_app(store=store, models=fake_models(FakeLLM([])))
        restarted = TestClient(app, base_url=BASE)
    else:
        restarted, _, _ = two_models(store, openai_key=False)
    with restarted as client:
        response = client.post("/runs", json={"prompt": "hi", "agent_id": agent["id"]})
        listed = template(client, agent["id"])
        runs = client.get("/runs").json()
    assert response.status_code == 422
    assert response.json()["detail"][0] == {
        "loc": ["body", "agent_id"],
        "msg": message,
        "type": "value_error",
    }
    assert runs == []
    assert listed["model"] == LUNA  # still listed with its model, shown as unavailable


# --- budgets (M17, FR-010) ---

DEFAULTS = {"model_calls": 30, "tokens": 200_000, "tool_calls": 30, "seconds": 600}
SMALL = {"model_calls": 1, "tokens": 1000, "tool_calls": 1, "seconds": 60}


def agent_body(name: str = "Budgeted", **fields: Any) -> dict[str, Any]:
    return {
        "template_id": "react",
        "name": name,
        "sample_prompt": "hi",
        "config": {"reasoning": False},
        **fields,
    }


@pytest.fixture
def budget_client(tmp_path: Path) -> Any:
    store = Store(tmp_path / "lab.db")
    llm = FakeLLM([answer("done")] * 5)
    with TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE) as client:
        yield client


def test_a_new_agent_starts_with_the_default_budget(budget_client: TestClient) -> None:
    assert budget_client.post("/agents", json=agent_body()).json()["budget"] == DEFAULTS


def test_a_new_agent_can_ask_for_no_budget_or_its_own(budget_client: TestClient) -> None:
    none = budget_client.post("/agents", json=agent_body("None", budget=None)).json()
    own = budget_client.post("/agents", json=agent_body("Own", budget=SMALL)).json()
    assert none["budget"] is None
    assert own["budget"] == SMALL


@pytest.mark.parametrize(
    "bad",
    [
        {**SMALL, "model_calls": 0},
        {**SMALL, "tokens": 2_000_001},
        {**SMALL, "seconds": 3_601},
        {"model_calls": 1},
    ],
)
def test_a_budget_outside_the_limits_is_refused(
    budget_client: TestClient, bad: dict[str, int]
) -> None:
    assert budget_client.post("/agents", json=agent_body(budget=bad)).status_code == 422


def test_an_update_without_a_budget_leaves_it_and_null_removes_it(
    budget_client: TestClient,
) -> None:
    agent = budget_client.post("/agents", json=agent_body(budget=SMALL)).json()
    fields = {k: agent_body()[k] for k in ("name", "sample_prompt", "config")}
    url = f"/agents/{agent['id']}"
    assert budget_client.put(url, json=fields).json()["budget"] == SMALL
    assert budget_client.put(url, json={**fields, "budget": DEFAULTS}).json()["budget"] == DEFAULTS
    assert budget_client.put(url, json={**fields, "budget": None}).json()["budget"] is None
    assert budget_client.put(url, json=fields).json()["budget"] is None


def test_templates_have_no_budget(budget_client: TestClient) -> None:
    templates = [a for a in budget_client.get("/agents").json() if a["kind"] == "template"]
    assert templates
    assert all(a["budget"] is None and a["ask_first"] == [] for a in templates)


def test_the_limits_are_served(budget_client: TestClient) -> None:
    assert budget_client.get("/budget-limits").json() == {
        "default": DEFAULTS,
        "max": {"model_calls": 200, "tokens": 2_000_000, "tool_calls": 200, "seconds": 3_600},
    }


def test_unsaved_block_agents_carry_the_budget_a_save_should_keep(
    budget_client: TestClient,
) -> None:
    assert budget_client.get("/blocks/new").json()["budget"] == DEFAULTS
    assert budget_client.get("/agents/react/blocks").json()["budget"] == DEFAULTS
    limited = budget_client.post("/agents", json=agent_body("L", budget=SMALL)).json()
    unlimited = budget_client.post("/agents", json=agent_body("U", budget=None)).json()
    assert budget_client.get(f"/agents/{limited['id']}/blocks").json()["budget"] == SMALL
    assert budget_client.get(f"/agents/{unlimited['id']}/blocks").json()["budget"] is None


def test_an_agent_saved_before_budgets_has_none_and_nothing_stops_it(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    old = store.create_agent(
        template_id="react",
        name="Old",
        description="",
        sample_prompt="hi",
        config={"reasoning": False},
    )
    llm = FakeLLM([answer("done")])
    with TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE) as client:
        assert client.get("/agents").json()[-1]["budget"] is None
        run = client.post("/runs", json={"prompt": "hi", "agent_id": old.agent_id}).json()
        with client.websocket_connect(
            f"{WS_BASE}/runs/{run['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            ended = read_until_run_ended(ws)[-1]["run"]
    assert ended["status"] == "completed"
    assert ended["harness"]["budget"] is None


def test_a_run_ends_at_its_agents_budget_and_records_it(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    script = [tool_call("calculator", '{"expression": "1"}')] * 5
    with TestClient(
        create_app(store=store, models=fake_models(FakeLLM(list(script)))), base_url=BASE
    ) as client:
        agent = client.post("/agents", json=agent_body(budget=SMALL)).json()
        run = client.post("/runs", json={"prompt": "hi", "agent_id": agent["id"]}).json()
        with client.websocket_connect(
            f"{WS_BASE}/runs/{run['run_id']}/stream", headers={"origin": ORIGIN}
        ) as ws:
            ended = read_until_run_ended(ws)[-1]["run"]
    assert ended["status"] == "over_budget"
    assert ended["stop_reason"] == "model calls: 1 of 1"  # the tool call was within its limit
    assert ended["harness"]["budget"] == SMALL


def test_agents_the_village_makes_have_no_budget(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    app = create_app(store=store, models=fake_models(FakeLLM([])))
    village = app.state.village
    village.ensure_agents()
    assert all(agent.harness is None for agent in store.list_agents())


# --- ask-first tools (M17, FR-015) ---


def test_ask_first_is_kept_and_pruned_to_the_agents_tools(budget_client: TestClient) -> None:
    config = {"reasoning": False, "tools": ["calculator", "get_weather"]}
    agent = budget_client.post(
        "/agents",
        json=agent_body(config=config, ask_first=["calculator", "notes/not_this_agents"]),
    ).json()
    assert agent["ask_first"] == ["calculator"]

    fields = {"name": "Budgeted", "sample_prompt": "hi", "config": config}
    url = f"/agents/{agent['id']}"
    assert budget_client.put(url, json=fields).json()["ask_first"] == ["calculator"]
    changed = budget_client.put(url, json={**fields, "ask_first": ["get_weather"]})
    assert changed.json()["ask_first"] == ["get_weather"]

    fewer = {**fields, "config": {"reasoning": False, "tools": ["calculator"]}}
    assert budget_client.put(url, json=fewer).json()["ask_first"] == []  # that tool is gone


def test_a_saved_agents_ask_first_tools_follow_it_into_a_block_copy(
    budget_client: TestClient,
) -> None:
    agent = budget_client.post("/agents", json=agent_body(ask_first=["calculator"])).json()
    assert budget_client.get(f"/agents/{agent['id']}/blocks").json()["ask_first"] == ["calculator"]
