"""JSON-RPC 2.0 messages and the MCP constants both ends share (research §1)."""

from typing import Any, TypeGuard, cast

Message = dict[str, Any]

MODERN = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # newest first

VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022


class RpcError(Exception):
    """A JSON-RPC error answer, raised where a result was expected."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def request(id: int | str, method: str, params: dict[str, Any] | None = None) -> Message:
    message: Message = {"jsonrpc": "2.0", "id": id, "method": method}
    return message if params is None else message | {"params": params}


def notification(method: str, params: dict[str, Any] | None = None) -> Message:
    message: Message = {"jsonrpc": "2.0", "method": method}
    return message if params is None else message | {"params": params}


def result(id: Any, value: Any) -> Message:
    return {"jsonrpc": "2.0", "id": id, "result": value}


def error(id: Any, code: int, message: str, data: Any = None) -> Message:
    body: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": body}


def _valid(message: object) -> TypeGuard[Message]:
    return isinstance(message, dict) and cast(Message, message).get("jsonrpc") == "2.0"


def is_request(message: object) -> bool:
    return _valid(message) and "method" in message and "id" in message


def is_notification(message: object) -> bool:
    return _valid(message) and "method" in message and "id" not in message


def is_response(message: object) -> bool:
    return (
        _valid(message)
        and "method" not in message
        and "id" in message
        and ("result" in message or "error" in message)
    )
