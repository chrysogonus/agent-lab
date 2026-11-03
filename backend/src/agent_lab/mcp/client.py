"""One connection to one MCP server: find its era, list its tools, call them (research §1, §6)."""

import asyncio
import itertools
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.jsonrpc import (
    CAPABILITIES_KEY,
    CLIENT_INFO_KEY,
    LEGACY,
    MODERN,
    SERVER_INFO_KEY,
    VERSION_KEY,
    Message,
    RpcError,
)
from agent_lab.mcp.transports import Transport, TransportClosed, TransportError

log = logging.getLogger(__name__)

CLIENT_INFO = {"name": "glasshouse", "version": "0.1.0"}
MAX_TEXT = 20_000  # characters of a tool result the model gets
MAX_LOG = 20  # messages kept of the last connect
MAX_LOG_TEXT = 4_000  # characters per kept message
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_HEADER_TYPES = {"string", "integer", "number", "boolean"}

State = Literal["connecting", "connected", "failed"]


@dataclass(frozen=True)
class ListedTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    header_params: dict[str, str] = field(default_factory=dict[str, str])  # argument → header


@dataclass(frozen=True)
class CallResult:
    text: str  # what the model gets
    error: str | None  # the failure, without the "error: " prefix
    request: Message
    response: Message | None  # None on a timeout or a dead connection


def _header_params(schema: dict[str, Any]) -> dict[str, str] | None:
    """Arguments mirrored into `Mcp-Param-*` headers; None when a declaration is invalid."""
    found: dict[str, str] = {}
    properties: object = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return None
    for name, prop in cast(dict[str, Any], properties).items():
        if not isinstance(prop, dict) or "x-mcp-header" not in prop:
            continue
        prop = cast(dict[str, Any], prop)
        header = prop["x-mcp-header"]
        if (
            not isinstance(header, str)
            or not _HEADER_NAME.fullmatch(header)
            or prop.get("type") not in _HEADER_TYPES
            or header.lower() in {h.lower() for h in found.values()}
        ):
            return None
        found[name] = header
    return found


def _listed(raw: object) -> ListedTool | None:
    """A tool from `tools/list`, or None for one the lab cannot offer."""
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    name, schema = raw.get("name"), raw.get("inputSchema")
    if not isinstance(name, str) or not isinstance(schema, dict):
        return None
    schema = cast(dict[str, Any], schema)
    headers = _header_params(schema)
    if schema.get("type") != "object" or headers is None:
        return None
    description = raw.get("description")
    return ListedTool(name, description if isinstance(description, str) else "", schema, headers)


def _item_text(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    item = cast(dict[str, Any], item)
    kind = item.get("type")
    if kind == "text":
        return str(item.get("text", ""))
    if kind in ("image", "audio"):
        return f"[{kind}: {item.get('mimeType', 'unknown')}]"
    if kind == "resource_link":
        return f"[resource link: {item.get('uri', '')}]"
    if kind == "resource":
        resource = cast(dict[str, Any], item.get("resource") or {})
        text = resource.get("text")
        return text if isinstance(text, str) else f"[resource: {resource.get('uri', '')}]"
    return f"[{kind}]"


def result_text(result: dict[str, Any]) -> str:
    """The model's text for a `tools/call` result (contracts "Tool result text")."""
    content = cast(list[Any], result.get("content") or [])
    if not content and "structuredContent" in result:
        return json.dumps(result["structuredContent"])
    return "\n\n".join(_item_text(item) for item in content)


def cut(text: str) -> str:
    extra = len(text) - MAX_TEXT
    return text if extra <= 0 else f"{text[:MAX_TEXT]}\n[cut: {extra} more characters]"


def _error(answer: Message) -> tuple[int, str, Any]:
    """(code, message, data) of a JSON-RPC error answer, whatever shape it came in."""
    error = answer["error"]
    if not isinstance(error, dict):
        return jsonrpc.INTERNAL_ERROR, str(error), None
    error = cast(dict[str, Any], error)
    code = error.get("code")
    return (
        code if isinstance(code, int) else jsonrpc.INTERNAL_ERROR,
        str(error.get("message")),
        error.get("data"),
    )


def _header_value(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return None


class Connection:
    def __init__(
        self,
        name: str,
        transport: Transport,
        *,
        connect_timeout: float = 10,
        call_timeout: float = 30,
        discover_timeout: float = 3,
        kind: str = "internal",
        target: str = "built in",
    ) -> None:
        self.name = name
        self.kind = kind  # internal, stdio or http
        self.target = target  # the command line or the address
        self.transport = transport
        self.connect_timeout = connect_timeout
        self.call_timeout = call_timeout
        self.discover_timeout = discover_timeout
        self.state: State = "connecting"
        self.reason: str | None = None
        self.era: Literal["modern", "legacy"] | None = None
        self.protocol_version: str | None = None
        self.server_info: dict[str, Any] | None = None
        self.capabilities: dict[str, Any] = {}
        self.tools: list[ListedTool] = []
        self.watching = False
        self.log: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._tasks: set[asyncio.Task[Any]] = set()
        transport.on_notice(self._notice)

    def tool(self, name: str) -> ListedTool | None:
        return next((t for t in self.tools if t.name == name), None)

    async def open(self) -> None:
        """Connect within the connect timeout; failures become `state` and `reason`."""
        self.log = []
        try:
            await asyncio.wait_for(self._open(), self.connect_timeout)
        except TimeoutError:
            self.fail(f"timed out after {self.connect_timeout:g} s")
        except (RpcError, TransportClosed, TransportError) as exc:
            self.fail(str(exc))
        except OSError as exc:  # e.g. a program that does not exist
            self.fail(f"cannot start: {exc.strerror or exc}")
        except Exception as exc:  # a malformed answer must still end the attempt
            log.exception("connecting %s failed", self.name)
            self.fail(f"unexpected answer: {exc}")

    def fail(self, reason: str) -> None:
        self.state, self.reason = "failed", reason

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await self.transport.close()

    async def _open(self) -> None:
        await self.transport.start()
        try:
            info = await asyncio.wait_for(
                self._rpc("server/discover", {}, modern=True), self.discover_timeout
            )
            if MODERN not in info.get("supportedVersions", []):
                raise TransportError("no common modern version")
            self.era, self.protocol_version = "modern", MODERN
            self.server_info = cast(dict[str, Any], info.get("_meta") or {}).get(SERVER_INFO_KEY)
        except RpcError as exc:
            if exc.code == jsonrpc.UNSUPPORTED_VERSION:
                raise
            await self._initialize()
        except (TimeoutError, TransportError):
            await self._initialize()
        else:
            self.capabilities = info.get("capabilities") or {}
        self.tools = await self._list_tools()
        self.state, self.reason = "connected", None
        await self._watch()

    async def _initialize(self) -> None:
        """The legacy handshake (2025-11-25 and older)."""
        self.era = "legacy"
        info = await self._rpc(
            "initialize",
            {"protocolVersion": LEGACY[0], "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        version = info.get("protocolVersion")
        if version not in LEGACY:
            raise RpcError(jsonrpc.UNSUPPORTED_VERSION, f"unsupported protocol version {version}")
        self.protocol_version = cast(str, version)
        self.server_info = info.get("serverInfo")
        self.capabilities = info.get("capabilities") or {}
        initialized = jsonrpc.notification("notifications/initialized")
        self._log("out", initialized)
        await self.transport.notify(initialized)

    async def _list_tools(self) -> list[ListedTool]:
        tools: list[ListedTool] = []
        cursor: str | None = None
        while True:
            page = await self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            tools += [t for t in map(_listed, page.get("tools") or []) if t is not None]
            cursor = page.get("nextCursor")
            if not cursor:
                return tools

    async def _watch(self) -> None:
        """Follow tool changes when the server announces them (FR-016, research §3)."""
        if not cast(dict[str, Any], self.capabilities.get("tools") or {}).get("listChanged"):
            return
        if self.era == "modern":
            listen = self._request(
                "subscriptions/listen", {"notifications": {"toolsListChanged": True}}
            )
            self._spawn(self.transport.send(listen))  # open as long as the connection
            self.watching = True
        else:
            self.watching = self.transport.streams_notices

    def _notice(self, message: Message) -> None:
        if (
            message.get("method") == "notifications/tools/list_changed"
            and self.state == "connected"
        ):
            self._spawn(self._relist())

    async def _relist(self) -> None:
        try:
            self.tools = await self._list_tools()
        except (RpcError, TransportClosed, TransportError) as exc:
            log.warning("listing the tools of %s again failed: %s", self.name, exc)

    def _spawn(self, work: Any) -> None:
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _request(self, method: str, params: dict[str, Any], *, modern: bool = False) -> Message:
        if modern or self.era == "modern":
            params = params | {
                "_meta": {
                    VERSION_KEY: MODERN,
                    CAPABILITIES_KEY: {},
                    CLIENT_INFO_KEY: CLIENT_INFO,
                }
            }
        return jsonrpc.request(next(self._ids), method, params)

    def _log(self, direction: str, message: Message) -> None:
        if len(self.log) >= MAX_LOG:
            return
        text = json.dumps(message)
        kept: Any = message if len(text) <= MAX_LOG_TEXT else text[:MAX_LOG_TEXT] + "…"
        self.log.append({"direction": direction, "message": kept})

    async def _rpc(
        self, method: str, params: dict[str, Any], *, modern: bool = False
    ) -> dict[str, Any]:
        """A logged request during connect; an error answer raises `RpcError`."""
        message = self._request(method, params, modern=modern)
        self._log("out", message)
        answer = await self.transport.send(message)
        self._log("in", answer)
        if "error" in answer:
            raise RpcError(*_error(answer))
        result = answer.get("result", {})
        if not isinstance(result, dict):
            raise TransportError(f"the answer to {method} is not an object")
        return cast(dict[str, Any], result)

    async def call(self, tool: str, arguments: dict[str, Any]) -> CallResult:
        request = self._request("tools/call", {"name": tool, "arguments": arguments})

        def failed(error: str, response: Message | None = None) -> CallResult:
            return CallResult(f"error: {error}", error, request, response)

        if self.state != "connected":
            return failed(f'server "{self.name}" is unavailable')
        headers: dict[str, str] = {}
        listed = self.tool(tool)
        if self.era == "modern" and listed:
            for param, header in listed.header_params.items():
                if (value := _header_value(arguments.get(param))) is not None:
                    headers[f"Mcp-Param-{header}"] = value
        try:
            response = await asyncio.wait_for(
                self.transport.send(request, headers=headers or None), self.call_timeout
            )
        except TimeoutError:
            return failed(f"timed out after {self.call_timeout:g} s")
        except TransportClosed as exc:
            self.fail(str(exc))
            return failed(f'server "{self.name}" is unavailable')
        except TransportError as exc:
            return failed(str(exc))
        if "error" in response:
            return failed(_error(response)[1], response)
        result = response.get("result", {})
        if not isinstance(result, dict):
            return failed("the answer to tools/call is not an object", response)
        result = cast(dict[str, Any], result)
        if result.get("resultType", "complete") == "input_required":
            return failed("the tool asked for input, which the lab does not support", response)
        text = cut(result_text(result))
        if result.get("isError"):
            return failed(text, response)
        return CallResult(text, None, request, response)
