"""The notes server keeps notes inside its folder only (FR-013, data-model "Note")."""

from pathlib import Path
from typing import Any

import pytest

from agent_lab.mcp import jsonrpc
from agent_lab.mcp.notes import notes_server
from agent_lab.mcp.server import Server


def call(server: Server, tool: str, **arguments: Any) -> tuple[str, bool]:
    answer = server.handle(jsonrpc.request(1, "tools/call", {"name": tool, "arguments": arguments}))
    assert answer is not None and "result" in answer, answer
    return answer["result"]["content"][0]["text"], answer["result"]["isError"]


def test_write_list_read(tmp_path: Path) -> None:
    server = notes_server(tmp_path / "notes")
    assert server.info["name"] == "glasshouse-notes"
    assert call(server, "list_notes") == ("No notes yet.", False)
    assert call(server, "write_note", name="Groceries list", text="eggs\nflour") == (
        'Saved "Groceries list" (10 characters).',
        False,
    )
    call(server, "write_note", name="a", text="first")
    assert call(server, "list_notes") == ("a (5 characters)\nGroceries list (10 characters)", False)
    assert call(server, "read_note", name="Groceries list") == ("eggs\nflour", False)
    call(server, "write_note", name="a", text="replaced")
    assert call(server, "read_note", name="a") == ("replaced", False)
    assert (tmp_path / "notes" / "a.md").read_text() == "replaced"


@pytest.mark.parametrize("name", ["../secret", "/etc/passwd", "a/b", ".hidden", "", "x" * 61])
def test_names_outside_the_rules_are_refused(tmp_path: Path, name: str) -> None:
    server = notes_server(tmp_path / "notes")
    text, failed = call(server, "write_note", name=name, text="x")
    assert failed and "note name" in text
    assert call(server, "read_note", name=name)[1]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes"]


def test_a_link_out_of_the_folder_is_refused(tmp_path: Path) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("private")
    folder = tmp_path / "notes"
    server = notes_server(folder)
    (folder / "leak.md").symlink_to(secret)
    assert call(server, "read_note", name="leak") == (
        "the note leak is outside the notes folder",
        True,
    )
    assert call(server, "write_note", name="leak", text="x")[1]
    assert secret.read_text() == "private"
    assert call(server, "list_notes") == ("No notes yet.", False)


def test_limits(tmp_path: Path) -> None:
    server = notes_server(tmp_path)
    assert call(server, "write_note", name="big", text="x" * 20_001) == (
        "a note holds at most 20000 characters; this one has 20001",
        True,
    )
    assert call(server, "read_note", name="nothing") == ('no note named "nothing"', True)
    for i in range(200):
        (tmp_path / f"n{i}.md").write_text("")
    assert call(server, "write_note", name="one more", text="x") == (
        "the folder already holds 200 notes, the most it may",
        True,
    )
    assert not call(server, "write_note", name="n0", text="replacing is fine")[1]
