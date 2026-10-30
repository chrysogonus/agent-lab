"""Tool declaration. Tools receive only their parsed arguments: no file or network handles."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
    """Invalid input or a failed tool call; the message is returned to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments object
    fn: Callable[..., str]
    # Access a tool needs beyond pure computation, e.g. {"net:api.example.com"}.
    scopes: frozenset[str] = field(default_factory=frozenset[str])

    def schema(self) -> dict[str, Any]:
        """OpenAI-style function tool declaration."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
