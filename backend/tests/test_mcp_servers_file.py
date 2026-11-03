"""The owner's servers file (data-model "Servers file", research §5)."""

import json
from pathlib import Path
from typing import Any

import pytest

from agent_lab.mcp.servers_file import (
    EntryError,
    HttpEntry,
    StdioEntry,
    check_host,
    find,
    load,
    resolve_values,
    secrets,
    target,
)


def write(tmp_path: Path, servers: Any) -> Path:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return path


def test_both_kinds(tmp_path: Path) -> None:
    entries, error = load(
        write(
            tmp_path,
            {
                "notes": {"command": "uv", "args": ["run", "x"], "env": {"A": "1"}},
                "docs": {"url": "http://127.0.0.1:9000/mcp", "headers": {"X": "y"}},
                "explicit": {
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "allowHosts": ["example.com"],
                },
            },
        )
    )
    assert error is None
    assert entries["notes"] == StdioEntry(command="uv", args=["run", "x"], env={"A": "1"})
    assert isinstance(entries["docs"], HttpEntry) and entries["docs"].headers == {"X": "y"}
    explicit = entries["explicit"]
    assert isinstance(explicit, HttpEntry) and explicit.allow_hosts == ["example.com"]


@pytest.mark.parametrize(
    ("servers", "part"),
    [
        ({"Notes": {"command": "x"}}, "Notes"),
        ({"lab": {"command": "x"}}, "lab"),
        ({"n": {"command": ""}}, "command"),
        ({"n": {"command": "x", "args": ["a"] * 51}}, "args"),
        ({"n": {"command": "x", "args": ["a" * 501]}}, "args"),
        ({"n": {"command": "x", "cwd": "/"}}, "cwd"),  # a typo or an unknown field
        ({"n": {"url": "ftp://127.0.0.1/x"}}, "url"),
        ({"n": {"type": "stdio"}}, "command"),
        ({f"s{i}": {"command": "x"} for i in range(21)}, "mcpServers"),
    ],
)
def test_invalid_files(tmp_path: Path, servers: Any, part: str) -> None:
    entries, error = load(write(tmp_path, servers))
    assert entries == {}
    assert error is not None and part in error


def test_unreadable_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{nope")
    _, error = load(broken)
    assert error is not None and "not valid JSON" in error
    _, error = load(tmp_path / "missing.json")
    assert error is not None and "cannot read" in error


def test_values_from_the_environment() -> None:
    entry = HttpEntry(url="http://127.0.0.1/mcp", headers={"Authorization": "Bearer ${TOKEN}"})
    resolved = resolve_values(entry, {"TOKEN": "s3cret"})
    assert isinstance(resolved, HttpEntry)
    assert resolved.headers == {"Authorization": "Bearer s3cret"}
    assert secrets(entry, {"TOKEN": "s3cret"}) == ["Bearer s3cret", "s3cret"]
    stdio = resolve_values(StdioEntry(command="x", env={"KEY": "${K}", "N": "1"}), {"K": "v"})
    assert isinstance(stdio, StdioEntry) and stdio.env == {"KEY": "v", "N": "1"}
    assert secrets(StdioEntry(command="x", env={"KEY": "${K}", "N": "1"}), {"K": "v"}) == [
        "v",
        "1",
    ]
    literal = HttpEntry(url="http://127.0.0.1/mcp", headers={"Authorization": "Basic abcdefgh12"})
    assert secrets(literal, {}) == ["Basic abcdefgh12", "abcdefgh12"]
    short = HttpEntry(url="http://127.0.0.1/mcp", headers={"X": "Basic ab"})
    assert secrets(short, {}) == ["Basic ab"]  # a short word alone would hide ordinary text
    with pytest.raises(EntryError, match="variable TOKEN is not set"):
        resolve_values(entry, {})


def test_hosts() -> None:
    for url in ("http://127.0.0.1:9/mcp", "http://localhost/mcp", "http://[::1]:8/mcp"):
        check_host(HttpEntry(url=url))
    with pytest.raises(EntryError, match=r'host "example\.com" is not this computer; add it'):
        check_host(HttpEntry(url="https://example.com/mcp"))
    check_host(HttpEntry(url="https://example.com/mcp", allowHosts=["example.com"]))


def test_target() -> None:
    assert target(StdioEntry(command="uv", args=["run", "a b"])) == "uv run 'a b'"
    assert target(HttpEntry(url="http://127.0.0.1/mcp")) == "http://127.0.0.1/mcp"


def test_find(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text("{}")
    assert find("", tmp_path) == tmp_path / "mcp.json"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "mcp.json").write_text("{}")
    assert find("", tmp_path) == tmp_path / "data" / "mcp.json"
    assert find("/elsewhere/servers.json", tmp_path) == Path("/elsewhere/servers.json")
