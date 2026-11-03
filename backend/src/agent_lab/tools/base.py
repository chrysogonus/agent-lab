"""A tool as an MCP server defines it: it receives only its parsed arguments."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class ToolError(Exception):
    """Invalid input or a failed tool call; the message is returned to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments object
    fn: Callable[..., str]
