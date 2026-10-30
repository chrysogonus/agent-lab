"""Provider-neutral model interface. An Anthropic adapter implements `LLMClient` later."""

from typing import Any, Protocol

from pydantic import BaseModel

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
    tokens_in: int | None = None
    tokens_out: int | None = None
    model: str | None = None

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
        return message


class LLMError(Exception):
    """The model endpoint failed (transport, HTTP status or unparseable response)."""


class LLMClient(Protocol):
    provider: str
    model: str

    async def chat(self, messages: list[Message], tools: list[dict[str, Any]]) -> ChatResponse: ...
