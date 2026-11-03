"""The servers API and the owner's servers in runs (contracts "HTTP API", US2, SC-004)."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import answer, fake_models, model_block, tool_call
from test_agents_api import run_to_end
from test_api import BASE
from test_blocks_api import block_agent, save

from agent_lab.api import create_app
from agent_lab.bus import Bus
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.mcp.host import Host
from agent_lab.mcp.lab_server import LAB
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Store

WEB = "http://127.0.0.1:9000/mcp"
TOKEN = "tok-abcdef123456"  # noqa: S105 (a test value)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def web_handler(request: httpx.Request) -> httpx.Response:
    """A modern server; its tool echoes the request's Authorization header back."""
    message = json.loads(request.content)
    if message.get("method") == "tools/call":
        authorization = request.headers["authorization"]
        text = f"{authorization} says 4 (key {authorization.split()[-1]})"
        result = {"content": [{"type": "text", "text": text}], "isError": False}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})
    answer_ = LAB.handle(message)
    return httpx.Response(202) if answer_ is None else httpx.Response(200, json=answer_)


def client_for(
    store: Store, tmp_path: Path, script: list[ScriptItem] | None = None
) -> tuple[TestClient, FakeLLM]:
    path = tmp_path / "mcp.json"
    headers = {"Authorization": "Bearer ${TOKEN}"}
    path.write_text(json.dumps({"mcpServers": {"web": {"url": WEB, "headers": headers}}}))
    client = httpx.AsyncClient(transport=httpx.MockTransport(web_handler))
    host = Host(path, client, {"TOKEN": TOKEN})
    llm = FakeLLM(list(script or []))
    app = create_app(store=store, models=fake_models(llm), host=host)
    return TestClient(app, base_url=BASE), llm


def settled(client: TestClient) -> dict[str, Any]:
    for _ in range(200):
        body = client.get("/mcp/servers").json()
        if all(s["state"] != "connecting" for s in body["servers"]):
            return body
        time.sleep(0.01)
    raise AssertionError("servers still connecting")


def test_servers(store: Store, tmp_path: Path) -> None:
    client, _ = client_for(store, tmp_path)
    with client:
        body = settled(client)
        tools = client.get("/tools").json()
    assert body["file"] == str(tmp_path / "mcp.json") and body["file_error"] is None
    assert [(s["name"], s["state"]) for s in body["servers"]] == [
        ("lab", "connected"),
        ("web", "connected"),
    ]
    assert [(t["name"], t["server"]) for t in tools] == [
        ("calculator", "lab"),
        ("get_weather", "lab"),
        ("web/calculator", "web"),
        ("web/get_weather", "web"),
    ]
    assert TOKEN not in json.dumps(body)


def test_reconnect_and_reload(store: Store, tmp_path: Path) -> None:
    client, _ = client_for(store, tmp_path)
    with client:
        settled(client)
        again = client.post("/mcp/servers/web/reconnect")
        missing = client.post("/mcp/servers/nope/reconnect")
        lab = client.post("/mcp/servers/lab/reconnect")
        reload = client.post("/mcp/reload")
        body = settled(client)
    assert again.status_code == 202
    assert (again.json()["name"], again.json()["state"]) == ("web", "connecting")
    assert missing.status_code == 404 and lab.status_code == 404
    assert reload.status_code == 202 and reload.json()["file"] == body["file"]
    assert [s["state"] for s in body["servers"]] == ["connected", "connected"]


def test_a_run_uses_an_owners_server_and_hides_its_secret(store: Store, tmp_path: Path) -> None:
    script: list[ScriptItem] = [tool_call("calculator", '{"expression": "2+2"}'), answer("4")]
    client, llm = client_for(store, tmp_path, script)
    with client:
        settled(client)
        system = f"Never repeat {TOKEN}."  # a secret written into a prompt is redacted too
        agent = save(client, block_agent(model_block("a", system=system, tools=["web/calculator"])))
        run, spans = run_to_end(client, agent["id"], "2+2?")
        stored = client.get(f"/runs/{run['run_id']}").json()
    assert run["status"] == "completed"
    tool = next(s for s in spans if s["kind"] == "tool")
    assert tool["node_id"] == "tool:web/calculator"
    assert tool["attributes"]["lab.mcp.server"] == "web"
    assert tool["output"] == "[REDACTED] says 4 (key [REDACTED])"
    assert llm.calls[1][-1]["content"] == f"Bearer {TOKEN} says 4 (key {TOKEN})"  # unredacted
    assert TOKEN not in json.dumps(run)
    assert TOKEN not in json.dumps(stored)


@pytest.mark.anyio
async def test_a_run_whose_agent_cannot_be_built_ends(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="blocks",
        name="Calc",
        description="",
        sample_prompt="x",
        config={"blocks": [model_block("a", tools=["calculator"])]},
    )
    models = fake_models(FakeLLM([]))
    run, config, spec, llm = new_run("hi", agent.agent_id, models, store)
    store.create_run(run)
    await execute_run(
        run=run, prompt="hi", config=config, spec=spec, llm=llm, store=store, bus=Bus(), tools={}
    )
    stored = store.get_run(run.run_id)
    assert stored is not None and stored.status == "error"
