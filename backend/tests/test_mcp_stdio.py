"""Local programs over stdio: the legacy fallback, the environment, exits (research §2)."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import answer, fake_models, model_block, tool_call
from test_agents_api import run_to_end
from test_api import BASE
from test_blocks_api import block_agent, save
from test_mcp_api import settled

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.mcp.client import Connection
from agent_lab.mcp.host import Host
from agent_lab.mcp.servers_file import load, target
from agent_lab.mcp.transports import Stdio
from agent_lab.store import Store

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


# --- The notes server as a local program (US3) ---


def notes_entry(folder: Path) -> dict[str, Any]:
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.mcp.notes", "--folder", str(folder)],
    }


@pytest.mark.anyio
async def test_the_notes_server_over_stdio(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"notes": notes_entry(tmp_path / "notes")}}))
    host = Host(path)
    await host.start()
    await host.settled()
    try:
        notes = host.connections["notes"]
        assert notes.state == "connected", notes.reason
        assert notes.era == "modern"
        assert notes.server_info == {"name": "glasshouse-notes", "version": "0.1.0"}
        tools = host.resolve(["notes/write_note", "notes/read_note"])
        await tools["notes/write_note"].call({"name": "fact", "text": "The sky is green."})
        read = await tools["notes/read_note"].call({"name": "fact"})
        assert read.text == "The sky is green."
        refused = await tools["notes/read_note"].call({"name": "../mcp"})
        assert refused.error is not None and "note name" in refused.error
    finally:
        await host.close()


def test_a_note_written_in_one_run_is_read_in_the_next(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"notes": notes_entry(tmp_path / "notes")}}))
    script: list[ScriptItem] = [
        tool_call("write_note", '{"name": "fact", "text": "The sky is green."}'),
        answer("Noted."),
        tool_call("read_note", '{"name": "fact"}'),
        answer("The sky is green."),
    ]
    llm = FakeLLM(script)
    app = create_app(store=Store(tmp_path / "lab.db"), models=fake_models(llm), host=Host(path))
    tools = ["notes/write_note", "notes/read_note"]
    with TestClient(app, base_url=BASE) as client:
        settled(client)
        agent = save(client, block_agent(model_block("a", tools=tools)))
        first, _ = run_to_end(client, agent["id"], "Remember: the sky is green.")
        second, _ = run_to_end(client, agent["id"], "What did you note?")
    assert (first["status"], second["status"]) == ("completed", "completed")
    assert llm.calls[3][-1]["content"] == "The sky is green."  # the read result, a run later


def test_the_default_file_lists_the_notes_server() -> None:
    entries, error = load(Path(__file__).parents[1] / "mcp.json")
    assert error is None and list(entries) == ["notes"]
    assert target(entries["notes"]).endswith("-m agent_lab.mcp.notes --folder data/notes")
