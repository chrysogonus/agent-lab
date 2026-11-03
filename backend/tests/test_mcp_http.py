"""The lab's own MCP server over HTTP for outside clients (FR-012, research §9, US4)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import fake_models
from test_api import BASE

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM
from agent_lab.mcp import jsonrpc
from agent_lab.mcp.client import Connection
from agent_lab.mcp.jsonrpc import MODERN, VERSION_KEY
from agent_lab.mcp.transports import Http
from agent_lab.store import Store

META: dict[str, Any] = {VERSION_KEY: MODERN, "io.modelcontextprotocol/clientCapabilities": {}}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(store=Store(tmp_path / "lab.db"), models=fake_models(FakeLLM([])))
    return TestClient(app, base_url=BASE)


def modern(method: str, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
    body = jsonrpc.request(1, method, {**(params or {}), "_meta": META})
    headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    if method == "tools/call":
        headers["Mcp-Name"] = (params or {})["name"]
    return body, headers


def test_a_modern_request(client: TestClient) -> None:
    body, headers = modern("tools/call", {"name": "calculator", "arguments": {"expression": "6*7"}})
    response = client.post("/mcp", json=body, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json()["result"]["content"] == [{"type": "text", "text": "42"}]
    assert "mcp-session-id" not in response.headers


@pytest.mark.parametrize(
    "headers",
    [
        {"Mcp-Method": "tools/list"},
        {"MCP-Protocol-Version": "2025-11-25", "Mcp-Method": "tools/list"},
        {"MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/call"},
    ],
)
def test_headers_must_match_the_body(client: TestClient, headers: dict[str, str]) -> None:
    body, _ = modern("tools/list")
    response = client.post("/mcp", json=body, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32020


def test_the_tool_name_header_must_match(client: TestClient) -> None:
    body, headers = modern("tools/call", {"name": "calculator", "arguments": {}})
    response = client.post("/mcp", json=body, headers=headers | {"Mcp-Name": "get_weather"})
    assert response.status_code == 400


def test_legacy_requests(client: TestClient) -> None:
    init = jsonrpc.request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    answer = client.post("/mcp", json=init)
    assert answer.status_code == 200
    assert answer.json()["result"]["protocolVersion"] == "2025-06-18"
    note = client.post("/mcp", json=jsonrpc.notification("notifications/initialized"))
    assert note.status_code == 202 and note.content == b""
    unknown = client.post("/mcp", json=jsonrpc.request(2, "prompts/list"))
    assert unknown.status_code == 200 and unknown.json()["error"]["code"] == -32601


def test_unknown_modern_method_is_404(client: TestClient) -> None:
    body, headers = modern("prompts/list")
    response = client.post("/mcp", json=body, headers=headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == -32601


def test_unreadable_bodies(client: TestClient) -> None:
    response = client.post("/mcp", content=b"{nope", headers={"content-type": "application/json"})
    assert response.status_code == 400 and response.json()["error"]["code"] == -32700
    batch = client.post("/mcp", json=[jsonrpc.request(1, "tools/list")])
    assert batch.status_code == 400 and batch.json()["error"]["code"] == -32600


def test_origins_and_hosts(client: TestClient) -> None:
    body, headers = modern("tools/list")
    foreign = client.post("/mcp", json=body, headers=headers | {"Origin": "https://evil.example"})
    assert foreign.status_code == 403
    own = client.post("/mcp", json=body, headers=headers | {"Origin": "http://localhost:3000"})
    assert own.status_code == 200
    rebinding = client.post("http://evil.example/mcp", json=body, headers=headers)
    assert rebinding.status_code == 400


def test_no_streams_or_sessions(client: TestClient) -> None:
    assert client.get("/mcp").status_code == 405
    assert client.delete("/mcp").status_code == 405


class DiscoverRefused(httpx.AsyncBaseTransport):
    """The app, except that `server/discover` gets a 404 page: a legacy-only server's answer."""

    def __init__(self, app: Any) -> None:
        self.app = httpx.ASGITransport(app=app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if json.loads(request.content).get("method") == "server/discover":
            return httpx.Response(404, text="Not Found")
        return await self.app.handle_async_request(request)


@pytest.mark.anyio
@pytest.mark.parametrize("era", ["modern", "legacy"])
async def test_an_outside_client(tmp_path: Path, era: str) -> None:
    app = create_app(store=Store(tmp_path / "lab.db"), models=fake_models(FakeLLM([])))
    asgi = httpx.ASGITransport(app=app) if era == "modern" else DiscoverRefused(app)
    async with httpx.AsyncClient(transport=asgi) as client:
        connection = Connection("glasshouse", Http(f"{BASE}/mcp", {}, client))
        await connection.open()
        assert connection.state == "connected", connection.reason
        assert connection.era == era
        assert connection.server_info == {"name": "glasshouse", "version": "0.1.0"}
        assert [t.name for t in connection.tools] == ["calculator", "get_weather"]
        assert (await connection.call("calculator", {"expression": "2**10 - 24"})).text == "1000"
        weather = await connection.call("get_weather", {"city": "Berlin"})
        assert json.loads(weather.text)["city"] == "Berlin"
