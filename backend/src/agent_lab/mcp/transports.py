"""How messages reach a server: in-process (the lab's own), stdio (local programs), HTTP.

Every transport has the same shape (`Transport`): `send` a request and get its response,
`notify`, receive the server's notices through `on_notice`, and `close`.
"""

import json
from collections.abc import Callable
from typing import Protocol

from agent_lab.mcp.jsonrpc import Message
from agent_lab.mcp.server import Server


class TransportClosed(Exception):
    """The server is gone: the program exited or the connection broke."""


class TransportError(Exception):
    """An answer that is not a JSON-RPC message, e.g. an HTTP 404 page."""


class Transport(Protocol):
    streams_notices: bool  # notices arrive without asking (stdio), not only on a listen stream

    async def start(self) -> None: ...

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        """The response to one request; `headers` are extra HTTP headers (ignored elsewhere)."""
        ...

    async def notify(self, message: Message) -> None: ...

    def on_notice(self, callback: Callable[[Message], None]) -> None: ...

    async def close(self) -> None: ...


def _wire(message: Message) -> Message:
    """A copy as it would travel: only JSON survives."""
    return json.loads(json.dumps(message))


class InProcess:
    """The lab's own server, called directly: the same messages, without a socket."""

    streams_notices = False

    def __init__(self, server: Server) -> None:
        self.server = server

    async def start(self) -> None:
        pass

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        answer = self.server.handle(_wire(message))
        if answer is None:
            raise TransportError("no answer to a request")
        return _wire(answer)

    async def notify(self, message: Message) -> None:
        self.server.handle(_wire(message))

    def on_notice(self, callback: Callable[[Message], None]) -> None:
        pass  # the lab's server never changes its tools

    async def close(self) -> None:
        pass
