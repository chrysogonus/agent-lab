"""One connection: era discovery, listing, calls and their result text (research §1, §6)."""

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

import pytest

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.client import Connection
from agent_lab.mcp.jsonrpc import MODERN, VERSION_KEY, Message
from agent_lab.mcp.server import Server
from agent_lab.mcp.transports import InProcess, TransportClosed
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER

SERVER = Server("test", "1.0", [CALCULATOR, WEATHER])

Answer = Callable[[Message], Any]  # a message, None, or an awaitable of one


class Fake:
    """A transport whose answers come from a function; by default the real server's."""

    streams_notices = False

    def __init__(self, answer: Answer | None = None) -> None:
        self.answer: Answer = answer or SERVER.handle
        self.sent: list[Message] = []
        self.headers: list[dict[str, str] | None] = []
        self.notified: list[Message] = []
        self.closed = False

    async def start(self) -> None:
        pass

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        self.sent.append(message)
        self.headers.append(headers)
        reply = self.answer(message)
        if inspect.isawaitable(reply):
            reply = await reply
        assert reply is not None
        return reply

    async def notify(self, message: Message) -> None:
        self.notified.append(message)

    def on_notice(self, callback: Callable[[Message], None]) -> None:
        self.notice = callback

    async def close(self) -> None:
        self.closed = True


def except_method(method: str, reply: Callable[[Message], Any]) -> Answer:
    """The real server, except that `method` gets `reply(message)`."""

    def answer(message: Message) -> Any:
        return reply(message) if message["method"] == method else SERVER.handle(message)

    return answer


def legacy(message: Message) -> Message | None:
    """A server that predates `server/discover`."""
    if message["method"] == "server/discover":
        return jsonrpc.error(message["id"], -32601, "method not found")
    return SERVER.handle(message)


def call_result(result: dict[str, Any]) -> Answer:
    return except_method("tools/call", lambda m: jsonrpc.result(m["id"], result))


async def opened(answer: Answer | None = None, **kwargs: Any) -> tuple[Connection, Fake]:
    transport = Fake(answer)
    connection = Connection("t", transport, **kwargs)
    await connection.open()
    return connection, transport


@pytest.mark.anyio
async def test_modern_open() -> None:
    connection = Connection("t", InProcess(SERVER))
    await connection.open()
    assert connection.state == "connected" and connection.reason is None
    assert connection.era == "modern" and connection.protocol_version == MODERN
    assert connection.server_info == {"name": "test", "version": "1.0"}
    assert [t.name for t in connection.tools] == ["calculator", "get_weather"]
    assert connection.tools[0].input_schema == CALCULATOR.parameters
    methods = [e["message"].get("method") for e in connection.log if e["direction"] == "out"]
    assert methods == ["server/discover", "tools/list"]


@pytest.mark.anyio
async def test_every_modern_request_carries_meta() -> None:
    connection, transport = await opened()
    await connection.call("calculator", {"expression": "1+1"})
    for message in transport.sent:
        meta = message["params"]["_meta"]
        assert meta[VERSION_KEY] == MODERN
        assert meta["io.modelcontextprotocol/clientCapabilities"] == {}
        assert meta["io.modelcontextprotocol/clientInfo"] == {
            "name": "glasshouse",
            "version": "0.1.0",
        }
    assert len({m["id"] for m in transport.sent}) == len(transport.sent)


@pytest.mark.anyio
async def test_legacy_fallback() -> None:
    connection, transport = await opened(legacy)
    assert connection.state == "connected"
    assert connection.era == "legacy" and connection.protocol_version == "2025-11-25"
    assert [m["method"] for m in transport.sent] == ["server/discover", "initialize", "tools/list"]
    assert transport.sent[1]["params"]["protocolVersion"] == "2025-11-25"
    assert "_meta" not in transport.sent[2].get("params", {})
    assert transport.notified == [jsonrpc.notification("notifications/initialized")]
    result = await connection.call("calculator", {"expression": "6*7"})
    assert result.text == "42" and result.error is None


@pytest.mark.anyio
async def test_a_silent_discover_falls_back() -> None:
    async def silent(message: Message) -> Message | None:
        if message["method"] == "server/discover":
            await asyncio.sleep(10)
        return SERVER.handle(message)

    connection, _ = await opened(silent, discover_timeout=0.01)
    assert connection.era == "legacy" and connection.state == "connected"


@pytest.mark.anyio
async def test_unsupported_version_fails_without_fallback() -> None:
    def refuse(m: Message) -> Message:
        return jsonrpc.error(m["id"], -32022, "unsupported protocol version 2026-07-28")

    connection, transport = await opened(except_method("server/discover", refuse))
    assert connection.state == "failed"
    assert connection.reason == "unsupported protocol version 2026-07-28"
    assert [m["method"] for m in transport.sent] == ["server/discover"]


@pytest.mark.anyio
async def test_unknown_legacy_version_fails() -> None:
    def old(m: Message) -> Message:
        return jsonrpc.result(m["id"], {"protocolVersion": "2023-01-01", "capabilities": {}})

    connection, _ = await opened(_legacy_with(old))
    assert connection.state == "failed"
    assert connection.reason == "unsupported protocol version 2023-01-01"


def _legacy_with(initialize: Callable[[Message], Message]) -> Answer:
    def answer(m: Message) -> Message | None:
        return initialize(m) if m["method"] == "initialize" else legacy(m)

    return answer


@pytest.mark.anyio
async def test_connect_timeout() -> None:
    async def hang(_: Message) -> Message | None:
        await asyncio.sleep(10)

    connection, _ = await opened(hang, connect_timeout=0.02, discover_timeout=0.01)
    assert connection.state == "failed" and connection.reason == "timed out after 0.02 s"


@pytest.mark.anyio
async def test_pagination_and_dropped_tools() -> None:
    pages = {
        None: {"tools": [{"name": "a", "inputSchema": {"type": "object"}}], "nextCursor": "p2"},
        "p2": {
            "tools": [
                {"name": "b", "description": "B", "inputSchema": {"type": "object"}},
                {"name": "no-schema"},
                {"name": "string-schema", "inputSchema": {"type": "string"}},
            ]
        },
    }

    def tools(m: Message) -> Message:
        return jsonrpc.result(m["id"], pages[m["params"].get("cursor")])

    connection, _ = await opened(except_method("tools/list", tools))
    assert [(t.name, t.description) for t in connection.tools] == [("a", ""), ("b", "B")]


@pytest.mark.anyio
async def test_x_mcp_header_declarations() -> None:
    schema = {
        "type": "object",
        "properties": {"region": {"type": "string", "x-mcp-header": "Region"}, "q": {}},
    }
    bad = {"type": "object", "properties": {"r": {"type": "object", "x-mcp-header": "R"}}}
    listed = {
        "tools": [
            {"name": "ok", "inputSchema": schema},
            {"name": "bad", "inputSchema": bad},
        ]
    }
    answer = except_method("tools/list", lambda m: jsonrpc.result(m["id"], listed))
    connection, transport = await opened(answer)
    assert [(t.name, t.header_params) for t in connection.tools] == [("ok", {"region": "Region"})]
    transport.answer = call_result({"content": [{"type": "text", "text": "x"}]})
    await connection.call("ok", {"region": "eu", "q": "hi"})
    assert transport.headers[-1] == {"Mcp-Param-Region": "eu"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "text"),
    [
        ({"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}, "a\n\nb"),
        (
            {"content": [{"type": "image", "data": "x", "mimeType": "image/png"}]},
            "[image: image/png]",
        ),
        (
            {"content": [{"type": "audio", "data": "x", "mimeType": "audio/wav"}]},
            "[audio: audio/wav]",
        ),
        (
            {"content": [{"type": "resource_link", "uri": "file:///a"}]},
            "[resource link: file:///a]",
        ),
        (
            {"content": [{"type": "resource", "resource": {"uri": "u", "text": "inside"}}]},
            "inside",
        ),
        (
            {"content": [{"type": "resource", "resource": {"uri": "u", "blob": "x"}}]},
            "[resource: u]",
        ),
        ({"content": [], "structuredContent": {"t": 21}}, '{"t": 21}'),
    ],
)
async def test_result_text(result: dict[str, Any], text: str) -> None:
    connection, _ = await opened(call_result(result))
    called = await connection.call("calculator", {})
    assert called.text == text and called.error is None
    assert called.response is not None and called.response["result"] == result


@pytest.mark.anyio
async def test_failures_become_error_text() -> None:
    connection, transport = await opened(
        call_result({"content": [{"type": "text", "text": "no"}], "isError": True})
    )
    called = await connection.call("calculator", {})
    assert (called.text, called.error) == ("error: no", "no")

    transport.answer = except_method(
        "tools/call", lambda m: jsonrpc.error(m["id"], -32602, "bad tool")
    )
    called = await connection.call("calculator", {})
    assert (called.text, called.error) == ("error: bad tool", "bad tool")

    transport.answer = call_result({"resultType": "input_required", "inputRequests": {}})
    called = await connection.call("calculator", {})
    assert called.text == "error: the tool asked for input, which the lab does not support"


@pytest.mark.anyio
async def test_long_text_is_cut() -> None:
    connection, _ = await opened(call_result({"content": [{"type": "text", "text": "x" * 20_005}]}))
    called = await connection.call("calculator", {})
    assert called.text == "x" * 20_000 + "\n[cut: 5 more characters]"


@pytest.mark.anyio
async def test_call_timeout() -> None:
    async def slow(m: Message) -> Message | None:
        if m["method"] == "tools/call":
            await asyncio.sleep(10)
        return SERVER.handle(m)

    connection, _ = await opened(slow, call_timeout=0.01)
    called = await connection.call("calculator", {"expression": "1"})
    assert called.text == "error: timed out after 0.01 s"
    assert called.response is None and called.request["method"] == "tools/call"
    assert connection.state == "connected"


@pytest.mark.anyio
async def test_a_dead_connection_fails_the_server() -> None:
    def dead(m: Message) -> Message:
        raise TransportClosed("the program exited with code 1")

    connection, transport = await opened()
    transport.answer = dead
    called = await connection.call("calculator", {"expression": "1"})
    assert called.text == 'error: server "t" is unavailable'
    assert connection.state == "failed" and connection.reason == "the program exited with code 1"
    again = await connection.call("calculator", {"expression": "1"})
    assert again.text == 'error: server "t" is unavailable' and len(transport.sent) == 3


@pytest.mark.anyio
async def test_the_log_is_bounded() -> None:
    many: dict[str, Any] = {
        "tools": [
            {"name": f"t{i}", "description": "d" * 300, "inputSchema": {"type": "object"}}
            for i in range(20)
        ]
    }
    pages: dict[str | None, dict[str, Any]] = {None: many | {"nextCursor": "1"}} | {
        str(i): many | {"nextCursor": str(i + 1)} for i in range(1, 12)
    }
    pages["12"] = many

    def tools(m: Message) -> Message:
        return jsonrpc.result(m["id"], pages[m["params"].get("cursor")])

    connection, _ = await opened(except_method("tools/list", tools))
    assert len(connection.log) == 20
    assert all(
        len(str(e["message"])) <= 4_001 for e in connection.log if isinstance(e["message"], str)
    )
    assert any(isinstance(e["message"], str) for e in connection.log)


@pytest.mark.anyio
async def test_close_closes_the_transport() -> None:
    connection, transport = await opened()
    await connection.close()
    assert transport.closed
