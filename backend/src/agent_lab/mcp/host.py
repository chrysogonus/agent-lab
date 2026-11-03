"""The host: every server connection, and the tools agents get from them (research §4, §8, §11)."""

import asyncio
import os
import re
from collections import Counter
from collections.abc import Callable, Coroutine, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from agent_lab.mcp.client import CallResult, Connection
from agent_lab.mcp.jsonrpc import Message
from agent_lab.mcp.lab_server import BUILT_INS, LAB
from agent_lab.mcp.servers_file import (
    Entry,
    EntryError,
    HttpEntry,
    StdioEntry,
    check_host,
    load,
    resolve_values,
    secrets,
    target,
)
from agent_lab.mcp.transports import Http, InProcess, Stdio, Transport, TransportError
from agent_lab.tracing.redact import redact

_MODEL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ToolsUnavailable(Exception):
    """A config names a tool no connected server offers."""


@dataclass(frozen=True)
class HostTool:
    server: str
    name: str  # the server's own name for it
    config_name: str  # `calculator`, `get_weather` or `server/tool`
    description: str
    parameters: dict[str, Any]  # the tool's input schema
    # shortcut: holds the connection it was resolved from; a reconnect during a run is not seen
    connection: Connection

    def schema(self, model_name: str) -> dict[str, Any]:
        """The chat tool declaration, under the name the model sees."""
        return {
            "type": "function",
            "function": {
                "name": model_name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def call(self, arguments: dict[str, Any]) -> CallResult:
        return await self.connection.call(self.name, arguments)


def model_names(tools: Iterable[HostTool]) -> dict[str, HostTool]:
    """The name each offered tool has for the model: its own if unique and safe, else
    `server__tool` with other characters replaced, at most 64 long, made unique."""
    tools = list(tools)
    counts = Counter(t.name for t in tools)
    named: dict[str, HostTool] = {}
    for tool in tools:
        name = tool.name
        if counts[name] > 1 or not _MODEL_NAME.fullmatch(name):
            name = re.sub(r"[^A-Za-z0-9_-]", "_", f"{tool.server}__{tool.name}")[:64]
        base, n = name, 2
        while name in named:
            suffix = f"_{n}"
            name, n = base[: 64 - len(suffix)] + suffix, n + 1
        named[name] = tool
    return named


def _config_name(server: str, tool: str) -> str:
    return tool if server == "lab" and tool in BUILT_INS else f"{server}/{tool}"


class _Refused:
    """The transport of an entry that cannot be connected: opening it fails with the reason."""

    streams_notices = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def start(self) -> None:
        raise TransportError(self.reason)

    async def send(self, message: Message, *, headers: dict[str, str] | None = None) -> Message:
        raise TransportError(self.reason)

    async def notify(self, message: Message) -> None:
        raise TransportError(self.reason)

    def on_notice(self, callback: Callable[[Message], None]) -> None:
        pass

    async def close(self) -> None:
        pass


class Host:
    """The lab's server at once; the servers file's entries in the background (research §11)."""

    def __init__(
        self,
        file_path: Path | None = None,
        http_client: httpx.AsyncClient | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.file_path = file_path
        self.http_client = http_client
        self.environ = os.environ if environ is None else environ
        self.connections: dict[str, Connection] = {}
        self.entries: dict[str, Entry] = {}
        self.file_error: str | None = None
        self._secrets: dict[str, list[str]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._started = False
        self._starting = asyncio.Lock()

    async def start(self) -> None:
        """Connect the lab's server and start connecting the file's; later calls do nothing
        (endpoints call it in tests that skip the app's lifespan)."""
        async with self._starting:
            if self._started:
                return
            lab = Connection("lab", InProcess(LAB))
            await lab.open()
            self.connections["lab"] = lab
            self._started = True
            await self.reload()

    async def settled(self) -> None:
        """Wait until every connection being opened is connected or failed."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for connection in self.connections.values():
            await connection.close()  # stops local programs (FR-017)

    async def reload(self) -> None:
        """Re-read the file: new and changed entries connect, removed ones close, unchanged
        connected ones stay as they are."""
        if self.file_path is None:
            return
        entries, self.file_error = load(self.file_path)
        for name in self.entries.keys() - entries.keys():
            self._spawn(self.connections.pop(name).close())
            self._secrets.pop(name, None)
        for name, entry in entries.items():
            current = self.connections.get(name)
            unchanged = self.entries.get(name) == entry
            if not (unchanged and current and current.state == "connected"):
                self._connect(name, entry)
        self.entries = entries

    def reconnect(self, name: str) -> Connection:
        """Re-read one entry and connect it again; `KeyError` for a name the file lacks."""
        if self.file_path is None or name == "lab":
            raise KeyError(name)
        entries, self.file_error = load(self.file_path)
        self.entries[name] = entries[name]
        return self._connect(name, entries[name])

    def _connect(self, name: str, entry: Entry) -> Connection:
        if old := self.connections.get(name):
            self._spawn(old.close())
        transport: Transport
        try:
            resolved = resolve_values(entry, self.environ)
            if isinstance(resolved, HttpEntry):
                check_host(resolved)
                transport = Http(resolved.url, resolved.headers, self._client())
            else:
                assert isinstance(resolved, StdioEntry)
                transport = Stdio(resolved.command, resolved.args, resolved.env)
            self._secrets[name] = secrets(resolved)
        except EntryError as exc:
            transport = _Refused(str(exc))
        connection = Connection(name, transport, kind=entry.type, target=target(entry))
        self.connections[name] = connection
        self._spawn(connection.open())
        return connection

    def _client(self) -> httpx.AsyncClient:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient()
        return self.http_client

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def secrets(self) -> list[str]:
        """Every resolved `env` and `headers` value of the file's entries."""
        return [value for values in self._secrets.values() for value in values]

    def servers(self) -> dict[str, Any]:
        """The Tools page: the file, its error, and every server (contracts `GET /mcp/servers`)."""
        return redact(
            {
                "file": None if self.file_path is None else str(self.file_path),
                "file_error": self.file_error,
                "servers": [self.server(name) for name in self.connections],
            },
            self.secrets(),
        )

    def server(self, name: str) -> dict[str, Any]:
        c = self.connections[name]
        return redact(
            {
                "name": name,
                "kind": c.kind,
                "target": c.target,
                "state": c.state,
                "reason": c.reason,
                "era": c.era,
                "protocol_version": c.protocol_version,
                "server_info": c.server_info,
                "watching": c.watching,
                "tools": [
                    {
                        "name": t.name,
                        "config_name": _config_name(name, t.name),
                        "description": t.description,
                        "parameters": t.input_schema,
                    }
                    for t in c.tools
                ],
                "log": c.log,
            },
            self.secrets(),
        )

    def resolve(self, config_names: Iterable[str]) -> dict[str, HostTool]:
        """The tools a config names, by config name; `ToolsUnavailable` names what is missing."""
        tools: dict[str, HostTool] = {}
        for config_name in config_names:
            server, _, name = config_name.rpartition("/")
            server = server or "lab"
            connection = self.connections.get(server)
            if connection is None or connection.state != "connected":
                raise ToolsUnavailable(f'server "{server}" is not connected')
            listed = connection.tool(name)
            if listed is None:
                raise ToolsUnavailable(f'tool "{config_name}" is not listed by "{server}"')
            tools[config_name] = HostTool(
                server, name, config_name, listed.description, listed.input_schema, connection
            )
        return tools

    def tools(self) -> list[dict[str, Any]]:
        """Every tool of every connected server, by config name (`GET /tools`)."""
        return [
            {
                "name": _config_name(server, t.name),
                "server": server,
                "description": t.description,
                "parameters": t.input_schema,
            }
            for server, connection in self.connections.items()
            if connection.state == "connected"
            for t in connection.tools
        ]
