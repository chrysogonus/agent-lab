"""How messages reach a server: in-process (the lab's own), stdio (local programs), HTTP.

Every transport has the same shape (`Transport`): `send` a request and get its response,
`notify`, receive the server's notices through `on_notice`, and `close`.
"""

import asyncio
import base64
import json
import logging
import os
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.jsonrpc import LEGACY, VERSION_KEY, Message
from agent_lab.mcp.server import Server

log = logging.getLogger(__name__)

MAX_LINE = 16 * 1024 * 1024  # bytes of one stdout message
STDERR_LINES = 20  # kept for the failure reason
STOP_WAIT = 2.0  # seconds between closing stdin, terminating and killing


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


class Stdio:
    """A local program: one JSON message per line on stdin and stdout; stderr is its log."""

    streams_notices = True

    def __init__(
        self, command: str, args: list[str], env: dict[str, str], cwd: Path | None = None
    ) -> None:
        self.command, self.args, self.cwd = command, args, cwd
        # Only what any program needs to start, plus what the entry names (FR-003).
        self.env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ} | env
        self.process: asyncio.subprocess.Process | None = None
        self._waiting: dict[Any, asyncio.Future[Message]] = {}
        self._callback: Callable[[Message], None] | None = None
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES)
        self._closed: str | None = None  # why, once the program is gone
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            cwd=self.cwd,
            limit=MAX_LINE,
        )
        stderr = asyncio.create_task(self._read_stderr())
        self._tasks = [stderr, asyncio.create_task(self._read(stderr))]

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        async for line in self.process.stderr:
            self._stderr.append(line.decode(errors="replace").rstrip())

    async def _read(self, stderr: asyncio.Task[None]) -> None:
        assert self.process and self.process.stdout
        while True:
            try:
                line = await self.process.stdout.readline()
            except ValueError:  # a line over MAX_LINE; the rest of it is dropped
                log.warning("%s: a message over %d bytes was ignored", self.command, MAX_LINE)
                continue
            if not line:
                break
            self._receive(line)
        await stderr
        code = await self.process.wait()
        tail = "; ".join(self._stderr)
        self._closed = f"the program exited with code {code}" + (f": {tail}" if tail else "")
        for future in self._waiting.values():
            if not future.done():
                future.set_exception(TransportClosed(self._closed))

    def _receive(self, line: bytes) -> None:
        try:
            message: object = json.loads(line)
        except json.JSONDecodeError:
            log.info("%s: ignored a line that is not JSON: %.200r", self.command, line)
            return
        if jsonrpc.is_response(message):
            message = cast(Message, message)
            future = self._waiting.get(message["id"])
            if future is not None and not future.done():
                future.set_result(message)
        elif jsonrpc.is_notification(message) and self._callback:
            self._callback(cast(Message, message))
        else:
            log.info("%s: ignored a message: %.200r", self.command, line)

    async def _write(self, message: Message) -> None:
        if self._closed or self.process is None or self.process.stdin is None:
            raise TransportClosed(self._closed or "the program is not running")
        try:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise TransportClosed(self._closed or f"the program stopped reading: {exc}") from exc

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        future = asyncio.get_running_loop().create_future()
        self._waiting[message["id"]] = future
        try:
            await self._write(message)
            return await future
        finally:
            self._waiting.pop(message["id"], None)

    async def notify(self, message: Message) -> None:
        await self._write(message)

    def on_notice(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback

    async def close(self) -> None:
        """Close stdin, then terminate, then kill (FR-017)."""
        process = self.process
        if process is not None and process.returncode is None:
            if process.stdin:
                process.stdin.close()
            for stop in (process.terminate, process.kill):
                try:
                    await asyncio.wait_for(process.wait(), STOP_WAIT)
                    break
                except TimeoutError:
                    try:
                        stop()
                    except ProcessLookupError:
                        break
            await process.wait()
        for task in self._tasks:
            task.cancel()


def _header(value: str) -> str:
    """Header values must be ASCII; others travel base64-encoded."""
    if value.isascii():
        return value
    return f"=?base64?{base64.b64encode(value.encode()).decode()}?="


async def _events(response: httpx.Response) -> AsyncIterator[object]:
    """The JSON messages of a server-sent event stream, one per event."""
    data: list[str] = []
    async for line in response.aiter_lines():
        if line:
            if line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
            continue
        if data:
            yield json.loads("\n".join(data))
            data = []
    if data:
        yield json.loads("\n".join(data))


class Http:
    """Streamable HTTP: every message is a POST; the answer is JSON or an event stream."""

    streams_notices = False

    def __init__(self, url: str, headers: dict[str, str], client: httpx.AsyncClient) -> None:
        self.url, self.headers, self.client = url, headers, client
        self._callback: Callable[[Message], None] | None = None
        self._legacy_version: str | None = None  # agreed by `initialize`
        self._session: str | None = None  # a legacy server's `Mcp-Session-Id`

    async def start(self) -> None:
        pass

    def _request_headers(self, message: Message, extra: dict[str, str] | None) -> dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream", **self.headers}
        params = cast(dict[str, Any], message.get("params") or {})
        version = cast(dict[str, Any], params.get("_meta") or {}).get(VERSION_KEY)
        if version:  # modern: every request says what it is
            headers |= {"MCP-Protocol-Version": version, "Mcp-Method": message["method"]}
            if message["method"] == "tools/call":
                headers["Mcp-Name"] = _header(str(params.get("name")))
            headers |= {k: _header(v) for k, v in (extra or {}).items()}
        elif self._legacy_version:
            headers["MCP-Protocol-Version"] = self._legacy_version
            if self._session:
                headers["Mcp-Session-Id"] = self._session
        return headers

    def _post(
        self, message: Message, extra: dict[str, str] | None = None
    ) -> AbstractAsyncContextManager[httpx.Response]:
        return self.client.stream(
            "POST",
            self.url,
            json=message,
            headers=self._request_headers(message, extra),
            timeout=httpx.Timeout(10.0, read=None),  # calls time out in the client; listens stay
        )

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        try:
            async with self._post(message, headers) as response:
                self._session = response.headers.get("mcp-session-id", self._session)
                answer = await self._answer(response, message["id"])
        except httpx.TransportError as exc:
            raise TransportClosed(str(exc) or type(exc).__name__) from exc
        if message["method"] == "initialize" and "result" in answer:
            version = cast(dict[str, Any], answer["result"]).get("protocolVersion")
            self._legacy_version = version if version in LEGACY else None
        return answer

    async def _answer(self, response: httpx.Response, id_: object) -> Message:
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            async for event in _events(response):
                if jsonrpc.is_response(event) and cast(Message, event)["id"] == id_:
                    return cast(Message, event)
                if jsonrpc.is_notification(event) and self._callback:
                    self._callback(cast(Message, event))
            raise TransportClosed("the event stream ended before the answer")
        body = await response.aread()
        try:
            answer: object = json.loads(body)
        except ValueError:
            answer = None
        if not jsonrpc.is_response(answer):
            raise TransportError(f"HTTP {response.status_code} without a JSON-RPC answer")
        return cast(Message, answer)

    async def notify(self, message: Message) -> None:
        try:
            async with self._post(message) as response:
                await response.aread()
        except httpx.TransportError as exc:
            raise TransportClosed(str(exc) or type(exc).__name__) from exc

    def on_notice(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback

    async def close(self) -> None:
        pass  # the client belongs to the host
