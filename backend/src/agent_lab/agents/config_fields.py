"""Field rules shared by the template configs (data-model.md, "Shared field rules")."""

import re
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

RESERVED_NAMES = frozenset({"start", "end", "gate", "router", "merge"})

LOCAL = "local"
# Left out of the JSON when local, so local configs keep their M3 `config_version`.
Provider = Annotated[Literal["local", "openai"], Field(exclude_if=lambda v: v == LOCAL)]

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


def _not_reserved(name: str) -> str:
    if name in RESERVED_NAMES:
        raise ValueError(f"{name!r} is reserved")
    return name


# Chain steps, routes and aspects: the name is also the graph node id.
ItemName = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9-]{1,30}$"), AfterValidator(_not_reserved)
]

# Graph nodes and reference words of block agents (blocks/model.py).
BLOCK_RESERVED = frozenset({"start", "end", "input", "previous", "feedback", "item"})


def _not_block_reserved(name: str) -> str:
    if name in BLOCK_RESERVED:
        raise ValueError(f"{name!r} is reserved")
    return name


BlockName = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9-]{1,30}$"), AfterValidator(_not_block_reserved)
]


_TOOL_NAME = re.compile(r"^(calculator|get_weather|[a-z][a-z0-9-]{0,29}/[A-Za-z0-9_.-]{1,64})$")


def known_tool(name: str) -> str:
    """A tool name of the right form; whether a server offers it is checked when a run starts."""
    if not _TOOL_NAME.fullmatch(name):
        raise ValueError(f"unknown tool name {name!r}: use calculator, get_weather or server/tool")
    return name


def unique(names: Iterable[str], what: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"duplicate {what} {name!r}")
        seen.add(name)


def fill(text: str, **values: object) -> str:
    """Replace `{key}` placeholders; unlike str.format, other braces in free text stay as is."""
    for key, value in values.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text
