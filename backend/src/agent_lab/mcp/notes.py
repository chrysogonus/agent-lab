"""The example notes server: short notes, kept only inside one folder (FR-013, research §10).

Run as a local program: `python -m agent_lab.mcp.notes --folder PATH`. It speaks MCP over
stdio with the same server core as the lab's own server.
"""

import argparse
import os
import re
import tempfile
from pathlib import Path

from agent_lab.mcp.server import Server, run_stdio
from agent_lab.tools.base import Tool, ToolError

MAX_TEXT = 20_000
MAX_NOTES = 200
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,59}$")
_NAME_RULE = (
    "letters, digits, spaces, _ and -, starting with a letter or digit, at most 60 characters"
)


def notes_server(folder: Path) -> Server:
    folder.mkdir(parents=True, exist_ok=True)
    folder = folder.resolve()

    def inside(path: Path) -> bool:
        return path.resolve().parent == folder  # a link cannot lead out

    def note(name: object) -> Path:
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ToolError(f"invalid note name {name!r}: {_NAME_RULE}")
        path = folder / f"{name}.md"
        if not inside(path):
            raise ToolError(f"the note {name} is outside the notes folder")
        return path

    def notes() -> list[Path]:
        return sorted(
            (p for p in folder.glob("*.md") if inside(p) and p.is_file()),
            key=lambda p: p.stem.lower(),
        )

    def list_notes() -> str:
        found = notes()
        if not found:
            return "No notes yet."
        return "\n".join(f"{p.stem} ({len(p.read_text())} characters)" for p in found)

    def read_note(name: object) -> str:
        path = note(name)
        if not path.is_file():
            raise ToolError(f'no note named "{name}"')
        return path.read_text()

    def write_note(name: object, text: object) -> str:
        path = note(name)
        if not isinstance(text, str):
            raise ToolError("text must be a string")
        if len(text) > MAX_TEXT:
            raise ToolError(f"a note holds at most {MAX_TEXT} characters; this one has {len(text)}")
        if not path.exists() and len(notes()) >= MAX_NOTES:
            raise ToolError(f"the folder already holds {MAX_NOTES} notes, the most it may")
        # A whole note or none: write a temporary file, then replace the note with it.
        handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(handle, "w") as file:
            file.write(text)
        os.replace(temporary, path)
        return f'Saved "{name}" ({len(text)} characters).'

    def schema(**properties: str) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in properties.items()},
            "required": list(properties),
            "additionalProperties": False,
        }

    name_hint = f"The note's name: {_NAME_RULE}."
    return Server(
        "glasshouse-notes",
        "0.1.0",
        [
            Tool("list_notes", "List the saved notes with their sizes.", schema(), list_notes),
            Tool("read_note", "Read one saved note.", schema(name=name_hint), read_note),
            Tool(
                "write_note",
                f"Save a note (at most {MAX_TEXT} characters), replacing one of the same name.",
                schema(name=name_hint, text="The note's text."),
                write_note,
            ),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="The Glasshouse notes MCP server (stdio).")
    parser.add_argument("--folder", required=True, type=Path, help="where the notes are kept")
    run_stdio(notes_server(parser.parse_args().folder))


if __name__ == "__main__":
    main()
