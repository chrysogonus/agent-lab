"""The host: every server connection, and the tools agents get from them (research §4, §8, §11)."""

import asyncio
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from agent_lab.mcp.client import CallResult, Connection
from agent_lab.mcp.lab_server import BUILT_INS, LAB
from agent_lab.mcp.transports import InProcess

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


class Host:
    def __init__(self) -> None:
        self.connections: dict[str, Connection] = {}
        self._started = False
        self._starting = asyncio.Lock()

    async def start(self) -> None:
        """Connect the lab's server; later calls do nothing (endpoints call it in tests that
        skip the app's lifespan)."""
        async with self._starting:
            if self._started:
                return
            lab = Connection("lab", InProcess(LAB))
            await lab.open()
            self.connections["lab"] = lab
            self._started = True

    async def close(self) -> None:
        for connection in self.connections.values():
            await connection.close()

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
