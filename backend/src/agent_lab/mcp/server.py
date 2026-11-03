"""One MCP server core for the lab's server and the notes server, answering both eras.

Modern clients (2026-07-28) send `server/discover` and carry the protocol version in every
request's `_meta`; legacy clients (2025-11-25 and older) send `initialize` first. Neither era
needs a session here, so both are answered by the same stateless `handle`.
"""

import json
import logging
import sys
from collections.abc import Iterable
from typing import IO, Any, cast

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.jsonrpc import LEGACY, MODERN, SERVER_INFO_KEY, VERSION_KEY, Message, RpcError
from agent_lab.tools.base import Tool, ToolError

log = logging.getLogger(__name__)


def check_arguments(tool: Tool, args: object) -> dict[str, object]:
    """The arguments as keyword arguments, or a `ToolError` naming what is wrong."""
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    args = cast(dict[str, object], args)  # JSON object keys are always strings
    expected: set[str] = set(tool.parameters.get("properties", {}))
    missing: set[str] = set(tool.parameters.get("required", [])) - args.keys()
    extra = args.keys() - expected
    if missing or extra:
        raise ToolError(f"invalid arguments: missing {sorted(missing)}, unexpected {sorted(extra)}")
    return args


class Server:
    def __init__(self, name: str, version: str, tools: Iterable[Tool]) -> None:
        self.info = {"name": name, "version": version}
        self.tools = {t.name: t for t in tools}

    def handle(self, message: object) -> Message | None:
        """The answer to one message; None for notifications and stray responses."""
        if not jsonrpc.is_request(message):
            if isinstance(message, dict) and "id" in message and "method" in message:
                return jsonrpc.error(message["id"], jsonrpc.INVALID_REQUEST, "invalid request")
            return None
        message = cast(Message, message)
        id_, method = message["id"], message["method"]
        params: object = message.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError(jsonrpc.INVALID_PARAMS, "params must be an object")
            params = cast(dict[str, Any], params)
            meta: dict[str, Any] = params.get("_meta") or {}
            requested = meta.get(VERSION_KEY)
            if requested is not None and requested != MODERN:
                raise RpcError(
                    jsonrpc.UNSUPPORTED_VERSION,
                    f"unsupported protocol version {requested}",
                    {"supported": [MODERN], "requested": requested},
                )
            return jsonrpc.result(id_, self._answer(method, params))
        except RpcError as exc:
            return jsonrpc.error(id_, exc.code, exc.message, exc.data)

    def _answer(self, method: object, params: dict[str, Any]) -> dict[str, Any]:
        if method == "server/discover":
            return {
                "resultType": "complete",
                "supportedVersions": [MODERN, LEGACY[0]],
                "capabilities": {"tools": {}},
                "_meta": {SERVER_INFO_KEY: self.info},
            }
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in LEGACY else LEGACY[0],
                "capabilities": {"tools": {}},
                "serverInfo": self.info,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            tools = [
                {"name": t.name, "description": t.description, "inputSchema": t.parameters}
                for t in self.tools.values()
            ]
            return {
                "resultType": "complete",
                "tools": tools,
                "ttlMs": 3600000,
                "cacheScope": "public",
            }
        if method == "tools/call":
            return self._call(params)
        raise RpcError(jsonrpc.METHOD_NOT_FOUND, f"unknown method {method}")

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        tool = self.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            raise RpcError(jsonrpc.INVALID_PARAMS, f"unknown tool {name!r}")
        try:
            text, failed = tool.fn(**check_arguments(tool, params.get("arguments", {}))), False
        except ToolError as exc:
            text, failed = str(exc), True
        except Exception as exc:
            log.exception("tool %s failed", tool.name)
            raise RpcError(jsonrpc.INTERNAL_ERROR, f"tool {tool.name} failed") from exc
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": text}],
            "isError": failed,
        }


def run_stdio(server: Server, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
    """Serve one JSON message per line until stdin closes; logs go to stderr only."""
    for line in stdin:
        if not line.strip():
            continue
        try:
            answer = server.handle(json.loads(line))
        except json.JSONDecodeError:
            answer = jsonrpc.error(None, jsonrpc.PARSE_ERROR, "parse error")
        if answer is not None:
            stdout.write(json.dumps(answer) + "\n")
            stdout.flush()
