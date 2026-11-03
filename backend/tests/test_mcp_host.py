"""The host: resolving config names and naming tools for the model (research §4, §8)."""

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_lab.mcp.client import Connection
from agent_lab.mcp.host import Host, HostTool, ToolsUnavailable, model_names
from agent_lab.mcp.lab_server import LAB
from agent_lab.mcp.server import Server
from agent_lab.mcp.transports import InProcess, Stdio


def tool(server: str, name: str) -> HostTool:
    connection = Connection(server, InProcess(Server(server, "1", [])))
    return HostTool(server, name, f"{server}/{name}", "", {"type": "object"}, connection)


@pytest.mark.anyio
async def test_resolve_the_built_ins() -> None:
    host = Host()
    await host.start()
    tools = host.resolve(["calculator", "lab/get_weather"])
    assert list(tools) == ["calculator", "lab/get_weather"]
    assert (tools["calculator"].server, tools["calculator"].name) == ("lab", "calculator")
    assert tools["lab/get_weather"].config_name == "lab/get_weather"
    result = await tools["calculator"].call({"expression": "17*23"})
    assert result.text == "391"
    assert host.resolve([]) == {}
    await host.close()


@pytest.mark.anyio
async def test_resolve_names_what_is_missing() -> None:
    host = Host()
    await host.start()
    with pytest.raises(ToolsUnavailable, match=r'^server "notes" is not connected$'):
        host.resolve(["calculator", "notes/write_note"])
    with pytest.raises(ToolsUnavailable, match=r'^tool "lab/nope" is not listed by "lab"$'):
        host.resolve(["lab/nope"])


@pytest.mark.anyio
async def test_tools_for_the_api() -> None:
    host = Host()
    await host.start()
    assert [(t["name"], t["server"]) for t in host.tools()] == [
        ("calculator", "lab"),
        ("get_weather", "lab"),
    ]


def test_model_names() -> None:
    a, b, dotted = tool("a", "search"), tool("b", "search"), tool("c", "my.tool")
    long = tool("d", "x" * 70)
    plain = tool("lab", "calculator")
    names = model_names([plain, a, b, dotted, long])
    assert names == {
        "calculator": plain,
        "a__search": a,
        "b__search": b,
        "c__my_tool": dotted,
        "d__" + "x" * 61: long,
    }


def test_model_names_stay_unique() -> None:
    first, second = tool("a-b", "x y"), tool("a_b", "x.y")
    assert list(model_names([first, second])) == ["a-b__x_y", "a_b__x_y"]
    clash, clash2 = tool("s", "a b"), tool("s", "a.b")
    assert list(model_names([clash, clash2])) == ["s__a_b", "s__a_b_2"]


def test_schema_uses_the_model_name() -> None:
    assert tool("a", "search").schema("a__search") == {
        "type": "function",
        "function": {"name": "a__search", "description": "", "parameters": {"type": "object"}},
    }


# --- The owner's servers file (data-model "State changes", research §11) ---

LEGACY_SCRIPT = str(Path(__file__).with_name("mcp_legacy_server.py"))
WEB = "http://127.0.0.1:9000/mcp"


def web_server(seen: list[httpx.Request] | None = None) -> httpx.AsyncClient:
    """A modern MCP server at WEB, answering with the lab's own server core."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        answer = LAB.handle(json.loads(request.content))
        return httpx.Response(202) if answer is None else httpx.Response(200, json=answer)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def servers_file(tmp_path: Path, servers: dict[str, Any]) -> Path:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return path


async def started(path: Path, client: httpx.AsyncClient | None = None, **environ: str) -> Host:
    host = Host(path, client or web_server(), environ)
    await host.start()
    await host.settled()
    return host


def states(host: Host) -> dict[str, tuple[str, str | None]]:
    return {s["name"]: (s["state"], s["reason"]) for s in host.servers()["servers"]}


@pytest.mark.anyio
async def test_a_program_and_an_address(tmp_path: Path) -> None:
    path = servers_file(
        tmp_path,
        {"old": {"command": sys.executable, "args": [LEGACY_SCRIPT]}, "web": {"url": WEB}},
    )
    host = await started(path)
    try:
        assert states(host) == {
            "lab": ("connected", None),
            "old": ("connected", None),
            "web": ("connected", None),
        }
        listed = {s["name"]: s for s in host.servers()["servers"]}
        assert listed["old"]["kind"] == "stdio" and listed["old"]["era"] == "legacy"
        assert listed["web"]["kind"] == "http" and listed["web"]["target"] == WEB
        assert listed["lab"]["kind"] == "internal" and listed["lab"]["target"] == "built in"
        assert listed["web"]["tools"][0]["config_name"] == "web/calculator"
        assert listed["lab"]["tools"][0]["config_name"] == "calculator"
        assert listed["web"]["log"][0]["message"]["method"] == "server/discover"
        names = [t["name"] for t in host.tools()]
        assert names[:2] == ["calculator", "get_weather"] and "old/echo" in names
        echo = host.resolve(["old/echo"])["old/echo"]
        assert (await echo.call({"text": "hi"})).text == "hi"
    finally:
        await host.close()


@pytest.mark.anyio
async def test_failures_stay_with_their_server(tmp_path: Path) -> None:
    path = servers_file(
        tmp_path,
        {
            "gone": {"command": "/nonexistent/server"},
            "far": {"url": "https://example.com/mcp"},
            "keyless": {"url": WEB, "headers": {"Authorization": "Bearer ${MISSING}"}},
            "web": {"url": WEB},
        },
    )
    host = await started(path)
    assert states(host) == {
        "lab": ("connected", None),
        "gone": ("failed", "cannot start: No such file or directory"),
        "far": (
            "failed",
            'host "example.com" is not this computer; add it to allowHosts to allow it',
        ),
        "keyless": ("failed", "variable MISSING is not set"),
        "web": ("connected", None),
    }
    await host.close()


@pytest.mark.anyio
async def test_an_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text("{")
    host = await started(path)
    listing = host.servers()
    assert listing["file"] == str(path)
    assert "not valid JSON" in (listing["file_error"] or "")
    assert states(host) == {"lab": ("connected", None)}
    assert (await host.resolve(["calculator"])["calculator"].call({"expression": "1"})).text == "1"


@pytest.mark.anyio
async def test_secrets_never_show(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    path = servers_file(
        tmp_path, {"web": {"url": WEB, "headers": {"Authorization": "Bearer ${TOKEN}"}}}
    )
    host = await started(path, web_server(seen), TOKEN="tok-123456")  # noqa: S106 (a test value)
    assert seen[0].headers["authorization"] == "Bearer tok-123456"
    assert "tok-123456" not in json.dumps(host.servers())
    assert "Bearer tok-123456" in host.secrets()


@pytest.mark.anyio
async def test_reload_and_reconnect(tmp_path: Path) -> None:
    path = servers_file(tmp_path, {"a": {"url": WEB}, "b": {"url": WEB}})
    host = await started(path)
    kept = host.connections["a"]
    servers_file(tmp_path, {"a": {"url": WEB}, "c": {"url": WEB}})
    await host.reload()
    await host.settled()
    assert states(host) == {
        "lab": ("connected", None),
        "a": ("connected", None),
        "c": ("connected", None),
    }
    assert host.connections["a"] is kept  # unchanged and connected: left alone
    servers_file(tmp_path, {"a": {"url": WEB, "headers": {"X": "1"}}, "c": {"url": WEB}})
    await host.reload()
    assert host.connections["a"] is not kept  # changed: connected again
    await host.settled()
    again = host.reconnect("c")
    assert again.state == "connecting"
    await host.settled()
    assert host.connections["c"].state == "connected"
    with pytest.raises(KeyError):
        host.reconnect("nope")


@pytest.mark.anyio
async def test_close_stops_local_programs(tmp_path: Path) -> None:
    path = servers_file(tmp_path, {"old": {"command": sys.executable, "args": [LEGACY_SCRIPT]}})
    host = await started(path)
    transport = host.connections["old"].transport
    assert isinstance(transport, Stdio) and transport.process is not None
    await host.close()
    assert transport.process.returncode is not None
