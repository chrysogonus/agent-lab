"""The host: resolving config names and naming tools for the model (research §4, §8)."""

import pytest

from agent_lab.mcp.client import Connection
from agent_lab.mcp.host import Host, HostTool, ToolsUnavailable, model_names
from agent_lab.mcp.server import Server
from agent_lab.mcp.transports import InProcess


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
