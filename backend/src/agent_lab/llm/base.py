"""Provider-neutral model interface: OpenAI chat format, translated by each adapter."""

from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel

# The model providers; model refs and agent configs both use this one list.
ProviderName = Literal["local", "openai", "anthropic"]

# OpenAI chat format: {"role": ..., "content": ..., "tool_calls"?: ..., "tool_call_id"?: ...}
Message = dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str  # raw JSON text exactly as the model produced it


class ChatResponse(BaseModel):
    content: str | None = None
    # Thinking text some providers return beside the answer; traced, never sent back.
    reasoning: str | None = None
    tool_calls: list[ToolCall] = []
    tokens_in: int | None = None  # all prompt tokens, cached ones included
    tokens_out: int | None = None
    # Prompt tokens read from / written to the provider's prompt cache, when it reports them.
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    model: str | None = None
    # The provider's own content blocks, sent back unchanged on the next call (Claude's thinking
    # blocks must return with their tool calls); other providers ignore them.
    blocks: list[dict[str, Any]] | None = None

    def as_message(self) -> Message:
        """The assistant message to append to the conversation."""
        message: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in self.tool_calls
            ]
        if self.blocks is not None:
            message["blocks"] = self.blocks
        return message


class LLMError(Exception):
    """The model endpoint failed (transport, HTTP status or unparseable response)."""


class LLMClient(Protocol):
    provider: str
    model: str

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        """`response_format`: OpenAI-style structured output request, passed through.

        `reasoning`: False turns model thinking off; None or True keeps the provider default.
        """
        ...


def strict_schema(schema: Any, unsupported: tuple[str, ...]) -> Any:
    """Close every object, require all its properties, and drop the keywords a provider refuses.

    The answer is still validated against the full pydantic model, bounds included.
    """
    if isinstance(schema, list):
        return [strict_schema(v, unsupported) for v in cast(list[Any], schema)]
    if not isinstance(schema, dict):
        return schema
    mapping = cast(dict[str, Any], schema)
    out = {k: strict_schema(v, unsupported) for k, v in mapping.items() if k not in unsupported}
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties") or {})
    return out
