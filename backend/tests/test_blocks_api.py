"""Block agents through the API: drafts, save, validation locs, runs, history (M5)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import BlockDict, answer, fake_models, model_block, router_block, tool_block
from test_agents_api import LUNA, run_to_end, two_models
from test_api import BASE

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store
from agent_lab.tools import catalog


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def client_for(store: Store, script: list[ScriptItem] | None = None) -> tuple[TestClient, FakeLLM]:
    llm = FakeLLM(list(script or []))
    return TestClient(create_app(store=store, models=fake_models(llm)), base_url=BASE), llm


def block_agent(*blocks: BlockDict, name: str = "Mine", **fields: Any) -> dict[str, Any]:
    return {
        "template_id": "blocks",
        "name": name,
        "description": "",
        "sample_prompt": "What is 17 times 23?",
        "config": {"reasoning": False, "blocks": list(blocks)},
        **fields,
    }


def save(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/agents", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def test_new_block_agent_draft(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        draft = client.get("/blocks/new").json()
    assert (draft["id"], draft["kind"], draft["template_id"], draft["model"]) == (
        "",
        "custom",
        "blocks",
        None,
    )
    assert [b["name"] for b in draft["config"]["blocks"]] == ["answer"]
    assert "model" not in draft["config"]
    assert [n["id"] for n in draft["graph"]["nodes"]] == ["start", "answer", "end"]


def test_save_block_agent(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        agent = save(client, block_agent(model_block("answer")))
        listed = [a for a in client.get("/agents").json() if a["id"] == agent["id"]]
    assert listed == [agent]
    assert (agent["kind"], agent["template_id"]) == ("custom", "blocks")
    assert agent["config"]["blocks"][0]["message"] == "{previous}"


def test_layout_error_locs(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        response = client.post(
            "/agents", json=block_agent(model_block("a"), model_block("b", message="{nope}"))
        )
        custom = [a for a in client.get("/agents").json() if a["kind"] == "custom"]
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "loc": ["body", "config", "blocks", 1, "message"],
            "msg": "unknown reference {nope}",
            "type": "value_error",
        }
    ]
    assert custom == []


def test_nested_field_error_locs(store: Store) -> None:
    """Pydantic's union tag is removed, so every loc is a path into the draft."""
    routes = {"x": [model_block("mx")], "y": [model_block("my", system=" ")]}
    body = block_agent(router_block("r", routes))
    loc = ["body", "config", "blocks", 0, "routes", 1, "blocks", 0, "system"]
    client, _ = client_for(store)
    with client:
        created = client.post("/agents", json=body)
        valid = save(client, block_agent(model_block("a"), name="Valid"))
        update = {k: v for k, v in body.items() if k != "template_id"}
        updated = client.put(f"/agents/{valid['id']}", json=update)
        preview = client.post("/graph", json={"template_id": "blocks", "config": body["config"]})
    for response in (created, updated, preview):
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == loc


def test_blocks_is_not_a_template(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        templates = [a["id"] for a in client.get("/agents").json() if a["kind"] == "template"]
        run = client.post("/runs", json={"prompt": "hi", "agent_id": "blocks"})
    assert "blocks" not in templates
    assert run.status_code == 422


def test_run_rejected_when_stored_agent_invalid(store: Store) -> None:
    client, _ = client_for(store)
    saved_tools = dict(catalog.TOOLS)
    try:
        with client:
            agent = save(client, block_agent(model_block("a"), tool_block("calc")))
            del catalog.TOOLS["calculator"]  # the tool is gone after a change
            response = client.post("/runs", json={"prompt": "hi", "agent_id": agent["id"]})
            runs = client.get("/runs").json()
    finally:
        catalog.TOOLS.clear()
        catalog.TOOLS.update(saved_tools)  # same order for later tests
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "agent_id"]
    assert runs == []


def test_build_and_run_three_blocks(store: Store) -> None:
    blocks = [
        model_block("expr", system="Reply with only the expression."),
        tool_block("calc", expression="{previous}"),
        model_block("explain", message="Question: {input}\nResult: {calc}"),
    ]
    client, llm = client_for(store, [answer("17*23"), answer("It is 391.")])
    with client:
        agent = save(client, block_agent(*blocks))
        preview = client.post("/graph", json={"template_id": "blocks", "config": agent["config"]})
        run, spans = run_to_end(client, agent["id"], "What is 17 times 23?")
    assert (run["status"], run["answer"]) == ("completed", "It is 391.")
    assert (run["template_id"], run["agent_name"]) == ("blocks", "Mine")
    assert [b["name"] for b in run["config"]["blocks"]] == ["expr", "calc", "explain"]
    assert run["graph"] == preview.json() == agent["graph"]
    assert [s["node_id"] for s in spans if s["kind"] in ("llm", "tool")] == [
        "expr",
        "calc",
        "explain",
    ]
    assert llm.calls[1][1]["content"] == "Question: What is 17 times 23?\nResult: 391"


def test_block_agent_on_pinned_model(store: Store) -> None:
    client, local, openai = two_models(store, openai_script=[answer("a"), answer("b")])
    with client:
        agent = save(client, block_agent(model_block("one"), model_block("two"), model=LUNA))
        run, spans = run_to_end(client, agent["id"], "hi")
    assert run["status"] == "completed" and local.calls == [] and len(openai.calls) == 2
    assert {s["attributes"]["gen_ai.provider.name"] for s in spans if s["kind"] == "llm"} == {
        "openai"
    }


# --- US3: open as blocks, history ---


def test_open_template_as_blocks(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        draft = client.get("/agents/routing/blocks").json()
        template = next(a for a in client.get("/agents").json() if a["id"] == "routing")
    assert (draft["id"], draft["template_id"], draft["model"]) == ("", "blocks", None)
    assert (draft["name"], draft["sample_prompt"]) == (template["name"], template["sample_prompt"])
    assert draft["config"]["blocks"][0]["kind"] == "router"
    assert {n["id"] for n in draft["graph"]["nodes"]} == {
        n["id"] for n in template["graph"]["nodes"]
    }


def test_open_custom_agent_as_blocks(store: Store) -> None:
    client, _, _ = two_models(store)
    with client:
        base = next(a for a in client.get("/agents").json() if a["id"] == "evaluator")
        body = {
            "template_id": "evaluator",
            "name": "Slogans",
            "description": "",
            "sample_prompt": "A lamp",
            "config": {**base["config"], "max_rounds": 5},
            "model": LUNA,
        }
        agent = client.post("/agents", json=body).json()
        draft = client.get(f"/agents/{agent['id']}/blocks").json()
        saved = save(client, {**draft, "template_id": "blocks", "name": "Slogans blocks"})
    assert draft["model"] == LUNA and draft["name"] == "Slogans"
    assert draft["config"]["blocks"][0]["max_rounds"] == 5
    assert saved["model"] == LUNA  # the copy saves as a block agent on the same model


def test_open_block_agent_conflict(store: Store) -> None:
    client, _ = client_for(store)
    with client:
        agent = save(client, block_agent(model_block("a")))
        conflict = client.get(f"/agents/{agent['id']}/blocks")
        missing = client.get("/agents/custom-nope/blocks")
    assert (conflict.status_code, missing.status_code) == (409, 404)


def test_edit_keeps_past_runs(store: Store) -> None:
    client, _ = client_for(store, [answer("one"), answer("two")])
    with client:
        agent = save(client, block_agent(model_block("first"), name="History"))
        before, _ = run_to_end(client, agent["id"], "hi")
        changed = {**agent["config"], "blocks": [model_block("renamed", system="Other prompt.")]}
        body = {"name": "History", "description": "", "sample_prompt": "hi", "config": changed}
        assert client.put(f"/agents/{agent['id']}", json=body).status_code == 200
        after, _ = run_to_end(client, agent["id"], "hi")
        replay = client.get(f"/runs/{before['run_id']}").json()
    assert before["config_version"] != after["config_version"]
    assert [b["name"] for b in replay["run"]["config"]["blocks"]] == ["first"]
    assert {n["id"] for n in replay["run"]["graph"]["nodes"]} == {"start", "first", "end"}
    assert {s["node_id"] for s in replay["spans"]} <= {"start", "first", "end"}


def test_delete_keeps_past_runs(store: Store) -> None:
    client, _ = client_for(store, [answer("one")])
    with client:
        agent = save(client, block_agent(model_block("first"), name="Gone"))
        run, _ = run_to_end(client, agent["id"], "hi")
        assert client.delete(f"/agents/{agent['id']}").status_code == 204
        listed = client.get("/runs").json()
        replay = client.get(f"/runs/{run['run_id']}").json()
    assert [r["agent_name"] for r in listed] == ["Gone"]
    assert replay["run"]["graph"] == run["graph"]


def test_templates_and_m3_agents_unchanged(store: Store) -> None:
    """Block agents add a kind; templates and M3 agents keep their M4 shape."""
    client, _ = client_for(store)
    with client:
        agents = client.get("/agents").json()
    templates = [a for a in agents if a["kind"] == "template"]
    assert [a["id"] for a in templates] == [
        "react",
        "chain",
        "routing",
        "parallel",
        "orchestrator",
        "evaluator",
    ]
    assert all(
        set(a)
        == {
            "id",
            "kind",
            "template_id",
            "name",
            "description",
            "sample_prompt",
            "config",
            "model",
            "graph",
        }
        for a in agents
    )


def test_open_as_blocks_rejects_a_literal_placeholder(store: Store) -> None:
    """A valid ReAct prompt with literal "{city}" can't become blocks: 422, not a crash."""
    client, _ = client_for(store)
    with client:
        base = next(a for a in client.get("/agents").json() if a["id"] == "react")
        config = {**base["config"], "system_prompt": "Fill in {city} for the user."}
        body = {
            "template_id": "react",
            "name": "Braces",
            "description": "",
            "sample_prompt": "x",
            "config": config,
        }
        agent = save(client, body)
        response = client.get(f"/agents/{agent['id']}/blocks")
    assert response.status_code == 422
    assert "{city}" in response.json()["detail"][0]["msg"]
