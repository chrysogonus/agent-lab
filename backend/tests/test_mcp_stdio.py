"""Local programs over stdio: the legacy fallback, the environment, exits (research §2)."""

import asyncio
import sys
from pathlib import Path

import pytest

from agent_lab.mcp.client import Connection
from agent_lab.mcp.transports import Stdio

LEGACY = str(Path(__file__).with_name("mcp_legacy_server.py"))


def legacy(env: dict[str, str] | None = None) -> Stdio:
    return Stdio(sys.executable, [LEGACY], env or {})


@pytest.mark.anyio
async def test_a_legacy_program() -> None:
    connection = Connection("old", legacy())
    await connection.open()
    try:
        assert connection.state == "connected", connection.reason
        assert (connection.era, connection.protocol_version) == ("legacy", "2025-11-25")
        assert connection.server_info == {"name": "legacy", "version": "0"}
        assert connection.watching  # stdio notices arrive unasked
        result = await connection.call("echo", {"text": "hello"})
        assert (result.text, result.error) == ("hello", None)
    finally:
        await connection.close()


@pytest.mark.anyio
async def test_only_named_variables_reach_the_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-for-servers")
    connection = Connection("old", legacy({"ONLY_THIS": "1"}))
    await connection.open()
    try:
        names = set((await connection.call("env", {})).text.split())
    finally:
        await connection.close()
    names.discard("LC_CTYPE")  # Python sets it in a C locale
    assert names == {"PATH", "HOME", "ONLY_THIS"}


@pytest.mark.anyio
async def test_a_missing_program_fails() -> None:
    connection = Connection("gone", Stdio("/nonexistent/server", [], {}))
    await connection.open()
    assert connection.state == "failed"
    assert connection.reason == "cannot start: No such file or directory"


@pytest.mark.anyio
async def test_a_program_that_exits() -> None:
    connection = Connection("old", legacy())
    await connection.open()
    result = await connection.call("exit", {})
    assert result.text == 'error: server "old" is unavailable'
    assert connection.state == "failed"
    assert connection.reason == "the program exited with code 3: a line on stderr"
    await connection.close()


@pytest.mark.anyio
async def test_a_tools_changed_notice_lists_again() -> None:
    connection = Connection("old", legacy())
    await connection.open()
    try:
        await connection.call("notify", {})
        for _ in range(100):
            if connection.tool("added"):
                break
            await asyncio.sleep(0.01)
        assert connection.tool("added") is not None
    finally:
        await connection.close()


@pytest.mark.anyio
async def test_close_stops_the_program() -> None:
    transport = legacy()
    connection = Connection("old", transport)
    await connection.open()
    await connection.close()
    assert transport.process is not None and transport.process.returncode is not None
