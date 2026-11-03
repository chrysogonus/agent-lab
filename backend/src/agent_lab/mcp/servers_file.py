"""The owner's servers file, in the `mcpServers` shape other MCP clients use (research §5).

The file is the grant: whatever it lists may run (local programs) or be reached (addresses).
"""

import json
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

MAX_SERVERS = 20
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class EntryError(Exception):
    """An entry that cannot be connected: the reason is shown on the Tools page."""


def _not_lab(name: str) -> str:
    if name == "lab":
        raise ValueError('"lab" is the lab\'s own server')
    return name


ServerName = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,29}$"), AfterValidator(_not_lab)
]
Arg = Annotated[str, StringConstraints(max_length=500)]


class StdioEntry(BaseModel):
    """A local program the lab starts and speaks to over stdin and stdout."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["stdio"] = "stdio"
    command: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    args: list[Arg] = Field(default=[], max_length=50)
    env: dict[str, str] = {}


class HttpEntry(BaseModel):
    """An address the lab reaches over streamable HTTP."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
    type: Literal["http"] = "http"
    url: str
    headers: dict[str, str] = {}
    allow_hosts: list[str] = Field(default=[], alias="allowHosts")

    @field_validator("url")
    @classmethod
    def http_or_https(cls, url: str) -> str:
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            raise ValueError("url must be an http or https address")
        return url


Entry = StdioEntry | HttpEntry


class ServersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servers: dict[ServerName, Annotated[Entry, Field(discriminator="type")]] = Field(
        alias="mcpServers", max_length=MAX_SERVERS
    )

    @model_validator(mode="before")
    @classmethod
    def default_types(cls, data: Any) -> Any:
        """`type` may be left out: `http` when the entry has a `url`, else `stdio`."""
        if not isinstance(data, dict):
            return data
        data = cast(dict[str, Any], data)
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            return data
        filled: dict[str, Any] = {}
        for name, entry in cast(dict[str, Any], servers).items():
            if isinstance(entry, dict) and "type" not in entry:
                entry = {
                    "type": "http" if "url" in entry else "stdio",
                    **cast(dict[str, Any], entry),
                }
            filled[name] = entry
        return {**data, "mcpServers": filled}


def find(setting: str, root: Path = Path()) -> Path:
    """`MCP_SERVERS_FILE`, else the owner's `data/mcp.json`, else the committed default."""
    if setting:
        return Path(setting)
    own = root / "data" / "mcp.json"
    return own if own.exists() else root / "mcp.json"


def load(path: Path) -> tuple[dict[str, Entry], str | None]:
    """The entries by name, or none and the one error that explains why."""
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        return {}, f"{path}: cannot read: {exc.strerror}"
    except json.JSONDecodeError as exc:
        return {}, f"{path}: not valid JSON: {exc.msg} (line {exc.lineno})"
    try:
        return dict(ServersFile.model_validate(data).servers), None
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return {}, f"{path}: {problems}"


def _fill(values: Mapping[str, str], environ: Mapping[str, str]) -> dict[str, str]:
    def variable(match: re.Match[str]) -> str:
        if match[1] not in environ:
            raise EntryError(f"variable {match[1]} is not set")
        return environ[match[1]]

    return {k: _VARIABLE.sub(variable, v) for k, v in values.items()}


def resolve_values(entry: Entry, environ: Mapping[str, str]) -> Entry:
    """`${NAME}` in `env` and `headers` values, taken from the lab's environment."""
    if isinstance(entry, StdioEntry):
        return entry.model_copy(update={"env": _fill(entry.env, environ)})
    return entry.model_copy(update={"headers": _fill(entry.headers, environ)})


def check_host(entry: HttpEntry) -> None:
    """Addresses stay on this computer unless the entry allows the host."""
    host = urlsplit(entry.url).hostname or ""
    if host not in LOOPBACK and host not in entry.allow_hosts:
        raise EntryError(f'host "{host}" is not this computer; add it to allowHosts to allow it')


def secrets(entry: Entry) -> list[str]:
    """Every resolved `env` and `headers` value: redacted wherever it could show."""
    values = entry.env if isinstance(entry, StdioEntry) else entry.headers
    return [v for v in values.values() if v]


def target(entry: Entry) -> str:
    """What the Tools page shows: the command line or the address."""
    if isinstance(entry, StdioEntry):
        return shlex.join([entry.command, *entry.args])
    return entry.url
