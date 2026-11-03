"""The server core answers both protocol eras (contracts "MCP messages the lab answers")."""

import io
import json
from typing import Any

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.jsonrpc import MODERN, SERVER_INFO_KEY, VERSION_KEY
from agent_lab.mcp.server import Server, run_stdio
from agent_lab.tools.base import Tool, ToolError
from agent_lab.tools.calculator import CALCULATOR

META: dict[str, Any] = {VERSION_KEY: MODERN, "io.modelcontextprotocol/clientCapabilities": {}}


def boom(**_: object) -> str:
    raise RuntimeError("internal detail")


SERVER = Server("test", "1.0", [CALCULATOR])


def ask(method: str, params: dict[str, Any] | None = None, *, modern: bool = True) -> Any:
    params = dict(params or {})
    if modern:
        params["_meta"] = META
    answer = SERVER.handle(jsonrpc.request(7, method, params))
    assert answer is not None and answer["id"] == 7
    return answer


def test_discover() -> None:
    result = ask("server/discover")["result"]
    assert result == {
        "resultType": "complete",
        "supportedVersions": ["2026-07-28", "2025-11-25"],
        "capabilities": {"tools": {}},
        "_meta": {SERVER_INFO_KEY: {"name": "test", "version": "1.0"}},
    }


def test_initialize_answers_a_legacy_version() -> None:
    for asked, agreed in [("2025-06-18", "2025-06-18"), ("1999-01-01", "2025-11-25")]:
        result = ask("initialize", {"protocolVersion": asked}, modern=False)["result"]
        assert result == {
            "protocolVersion": agreed,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test", "version": "1.0"},
        }
    assert SERVER.handle(jsonrpc.notification("notifications/initialized")) is None


def test_tools_list() -> None:
    result = ask("tools/list")["result"]
    assert result == {
        "resultType": "complete",
        "tools": [
            {
                "name": "calculator",
                "description": CALCULATOR.description,
                "inputSchema": CALCULATOR.parameters,
            }
        ],
        "ttlMs": 3600000,
        "cacheScope": "public",
    }


def test_tools_call() -> None:
    for modern in (True, False):
        result = ask(
            "tools/call",
            {"name": "calculator", "arguments": {"expression": "2**10 - 24"}},
            modern=modern,
        )["result"]
        assert result == {
            "resultType": "complete",
            "content": [{"type": "text", "text": "1000"}],
            "isError": False,
        }


def test_tool_errors_are_results() -> None:
    def call(arguments: object) -> Any:
        return ask("tools/call", {"name": "calculator", "arguments": arguments})["result"]

    assert call({"expression": "1/0"})["content"][0]["text"] == "division by zero"
    assert call({"expression": "1/0"})["isError"] is True
    assert call([1])["content"][0]["text"] == "arguments must be a JSON object"
    assert call({"x": 1})["content"][0]["text"] == (
        "invalid arguments: missing ['expression'], unexpected ['x']"
    )


def test_a_failing_tool_is_an_internal_error() -> None:
    server = Server("t", "1", [Tool("boom", "", {"type": "object", "properties": {}}, boom)])
    answer = server.handle(jsonrpc.request(1, "tools/call", {"name": "boom", "arguments": {}}))
    assert answer is not None
    assert answer["error"]["code"] == jsonrpc.INTERNAL_ERROR
    assert "internal detail" not in json.dumps(answer)


def test_protocol_errors() -> None:
    assert ask("tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602
    assert ask("resources/list")["error"]["code"] == -32601
    old = SERVER.handle(jsonrpc.request(1, "tools/list", {"_meta": {VERSION_KEY: "2027-01-01"}}))
    assert old is not None
    assert old["error"]["code"] == -32022
    assert old["error"]["data"] == {"supported": ["2026-07-28"], "requested": "2027-01-01"}
    bad = SERVER.handle({"id": 1, "method": "tools/list"})
    assert bad is not None and bad["error"]["code"] == jsonrpc.INVALID_REQUEST
    assert SERVER.handle({"jsonrpc": "2.0", "id": 1, "result": {}}) is None  # a stray response


def test_run_stdio_answers_line_by_line() -> None:
    lines = [
        json.dumps(jsonrpc.request(1, "tools/list", {"_meta": META})),
        "",
        "not json",
        json.dumps(jsonrpc.notification("notifications/initialized")),
    ]
    out = io.StringIO()
    run_stdio(SERVER, io.StringIO("\n".join(lines) + "\n"), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, None]
    assert answers[1]["error"]["code"] == jsonrpc.PARSE_ERROR


def test_tool_error_message_is_kept() -> None:
    def refuse(**_: object) -> str:
        raise ToolError("no such note")

    server = Server("t", "1", [Tool("r", "", {"type": "object", "properties": {}}, refuse)])
    answer = server.handle(jsonrpc.request(1, "tools/call", {"name": "r", "arguments": {}}))
    assert answer is not None
    assert answer["result"]["content"][0]["text"] == "no such note"
