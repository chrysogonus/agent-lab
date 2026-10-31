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
