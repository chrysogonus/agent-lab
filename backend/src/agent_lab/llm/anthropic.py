"""Thin client for Claude's `POST /v1/messages`, translating the lab's OpenAI-format messages.

The lab keeps every conversation in OpenAI chat format. This adapter translates at the edge:
- leading system messages become the top-level `system`; later ones stay in place;
- assistant tool calls become `tool_use` blocks, and tool results one user turn of
  `tool_result` blocks;
- an assistant message Claude wrote is sent back as its own blocks, unchanged, because its
  thinking blocks must return with their tool calls.
"""

import json
from typing import Any, cast

import httpx

from agent_lab.llm.base import ChatResponse, LLMError, Message, ToolCall, strict_schema

API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16_000  # thinking counts toward it; non-streaming, so kept moderate
EFFORT = "medium"  # the starting point for multistep tool use; valid with thinking off too
# Claude's structured outputs refuse these keywords; pydantic still checks them afterwards.
UNSUPPORTED = ("minLength", "maxLength", "minimum", "maximum", "multipleOf")
# How each model turns thinking off: Sonnet 5.5 refuses "disabled", and "between_tools" is its
# lowest setting; Haiku 5.5 takes "disabled". shortcut: Opus 5.5 and Fable refuse both; add them
# here (keeping adaptive thinking) when the lab offers them.
THINKING_OFF: dict[str, dict[str, str]] = {"claude-sonnet-5-5": {"type": "between_tools"}}
# Models with server-side refusal fallback; Haiku 5.5 has none.
WITH_FALLBACK = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
# Prompt caching, 5-minute entries: a hit costs a tenth of the input price, a write 1.25 times it.
CACHE = {"type": "ephemeral"}


class AnthropicClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        workspace_id: str = "",
        http: httpx.AsyncClient | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.provider = "anthropic"
        self.model = model
        self._url = base_url.rstrip("/") + "/messages"
        self._fallback = model in WITH_FALLBACK
        self._headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}
        if self._fallback:
            self._headers["anthropic-beta"] = FALLBACK_BETA
        if workspace_id:  # an organization-wide key must name the workspace to bill
            self._headers["anthropic-workspace-id"] = workspace_id
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        system, turns = _messages(messages)
        output: dict[str, Any] = {"effort": EFFORT}
        if response_format is not None:
            output["format"] = _format(response_format)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": turns,
            "thinking": (
                THINKING_OFF.get(self.model, {"type": "disabled"})
                if reasoning is False
                else {"type": "adaptive", "display": "summarized"}
            ),
            "output_config": output,
        }
        if self._fallback:
            body["fallbacks"] = "default"  # a declined request is retried on the fallback model
        if system:
            # Tools render before the system prompt, so this caches both: every call of an agent
            # (every villager turn) shares them. Prefixes under 512 tokens are simply not cached.
            body["system"] = [{"type": "text", "text": system, "cache_control": CACHE}]
        if tools:
            body["tools"] = [_tool(t) for t in tools]
            # A tool loop sends this whole prompt again next call: cache up to its last block.
            body["cache_control"] = CACHE
        elif used := _used_tools(turns):
            # An answer without tools after tool calls: Claude needs those tools defined, so they
            # are declared but not callable. Thinking blocks are dropped, since the tool list they
            # were written with changed (the API would refuse them).
            body["tools"] = [
                {
                    "name": name,
                    "description": "Not available for this answer.",
                    "input_schema": {"type": "object"},
                }
                for name in used
            ]
            body["tool_choice"] = {"type": "none"}
            body["messages"] = [_without_thinking(turn) for turn in turns]
        try:
            response = await self._http.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"request failed: {exc!r}") from exc
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            data = response.json()
            parsed = _parse(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc!r}") from exc
        if data.get("stop_reason") == "refusal":
            details: dict[str, Any] = data.get("stop_details") or {}
            category = details.get("category")
            raise LLMError(f"the model declined ({category})")
        return parsed


def _messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """The top-level system text and the Messages API turns."""
    system: list[str] = []
    turns: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "system" and not turns:
            system.append(message["content"])
        elif role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": message["tool_call_id"],
                "content": message["content"],
            }
            last = turns[-1] if turns else None
            if last and last["role"] == "user" and isinstance(last["content"], list):
                cast(list[dict[str, Any]], last["content"]).append(result)
            else:
                turns.append({"role": "user", "content": [result]})
        elif role == "assistant":
            turns.append({"role": "assistant", "content": _assistant(message)})
        else:
            turns.append({"role": role, "content": message["content"]})
    return "\n\n".join(system), turns


def _assistant(message: Message) -> str | list[dict[str, Any]]:
    if message.get("blocks") is not None:
        return message["blocks"]
    calls: list[dict[str, Any]] = message.get("tool_calls") or []
    if not calls:
        return message.get("content") or ""
    blocks: list[dict[str, Any]] = []
    if message.get("content"):
        blocks.append({"type": "text", "text": message["content"]})
    for call in calls:
        function = call["function"]
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": function["name"],
                "input": json.loads(function.get("arguments") or "{}"),
            }
        )
    return blocks


def _used_tools(turns: list[dict[str, Any]]) -> list[str]:
    names = [
        block["name"]
        for turn in turns
        if turn["role"] == "assistant" and isinstance(turn["content"], list)
        for block in cast(list[dict[str, Any]], turn["content"])
        if block["type"] == "tool_use"
    ]
    return list(dict.fromkeys(names))


def _without_thinking(turn: dict[str, Any]) -> dict[str, Any]:
    if turn["role"] != "assistant" or not isinstance(turn["content"], list):
        return turn
    blocks = cast(list[dict[str, Any]], turn["content"])
    kept = [b for b in blocks if b["type"] not in ("thinking", "redacted_thinking")]
    return {"role": "assistant", "content": kept}


def _tool(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool["function"]
    out: dict[str, Any] = {
        "name": function["name"],
        "input_schema": function.get("parameters") or {},
    }
    if function.get("description"):
        out["description"] = function["description"]
    return out


def _format(response_format: dict[str, Any]) -> dict[str, Any]:
    json_schema: dict[str, Any] = response_format.get("json_schema") or {}
    schema = json_schema.get("schema")
    if response_format.get("type") != "json_schema" or schema is None:
        raise LLMError(f"unsupported response_format for Claude: {response_format!r}")
    return {"type": "json_schema", "schema": strict_schema(schema, UNSUPPORTED)}


def _parse(data: dict[str, Any]) -> ChatResponse:
    blocks: list[dict[str, Any]] = data["content"]
    usage: dict[str, Any] = data.get("usage") or {}
    texts = [b["text"] for b in blocks if b["type"] == "text"]
    thoughts = [b["thinking"] for b in blocks if b["type"] == "thinking" and b.get("thinking")]
    return ChatResponse(
        content="".join(texts) if texts else None,
        reasoning="\n\n".join(thoughts) or None,
        tool_calls=[
            ToolCall(id=b["id"], name=b["name"], arguments=json.dumps(b["input"]))
            for b in blocks
            if b["type"] == "tool_use"
        ],
        tokens_in=(
            usage["input_tokens"]
            + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            if "input_tokens" in usage
            else None
        ),
        tokens_out=usage.get("output_tokens"),
        tokens_cache_read=usage.get("cache_read_input_tokens"),
        tokens_cache_write=usage.get("cache_creation_input_tokens"),
        model=data.get("model"),
        blocks=blocks,
    )
