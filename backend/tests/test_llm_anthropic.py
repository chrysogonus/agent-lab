"""The hand-written Claude adapter: OpenAI-format messages in, the Messages API out."""

import json
from typing import Any

import httpx
import pytest

from agent_lab.llm.anthropic import AnthropicClient
from agent_lab.llm.base import ChatResponse, LLMError, Message

KEY = "sk-ant-test-key"
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate arithmetic.",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
        },
    }
]
THINKING = {"type": "thinking", "thinking": "Multiply first.", "signature": "sig-1"}
TOOL_USE = {
    "type": "tool_use",
    "id": "toolu_1",
    "name": "calculator",
    "input": {"expression": "6*7"},
}


def calc(arguments: str) -> dict[str, str]:
    return {"name": "calculator", "arguments": arguments}


def answer(*content: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": list(content),
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 12, "output_tokens": 5},
        **extra,
    }


def client_for(
    *responses: httpx.Response,
) -> tuple[AnthropicClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    client = AnthropicClient(
        base_url="https://claude.test/v1/",
        model="claude-sonnet-5-5",
        api_key=KEY,
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return client, seen


def ok(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=body)


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


@pytest.mark.anyio
async def test_request_shape() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": "hi"})))
    messages: list[Message] = [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "6*7?"},
    ]
    await client.chat(messages, TOOLS)
    request = seen[0]
    assert str(request.url) == "https://claude.test/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert request.headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    body = body_of(request)
    assert body["model"] == "claude-sonnet-5-5"
    assert body["system"] == "Be brief."
    assert body["messages"] == [{"role": "user", "content": "6*7?"}]
    assert body["tools"] == [
        {
            "name": "calculator",
            "description": "Evaluate arithmetic.",
            "input_schema": TOOLS[0]["function"]["parameters"],
        }
    ]
    assert body["max_tokens"] == 16000
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert body["output_config"] == {"effort": "medium"}
    assert body["fallbacks"] == "default"
    assert not {"temperature", "top_p", "top_k", "tool_choice"} & set(body)


@pytest.mark.anyio
async def test_no_tools_sends_no_tools_field() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": "hi"})))
    await client.chat([{"role": "user", "content": "hi"}], [])
    assert "tools" not in body_of(seen[0])
    assert "system" not in body_of(seen[0])


@pytest.mark.anyio
async def test_response_parsing() -> None:
    client, _ = client_for(
        ok(answer(THINKING, {"type": "text", "text": "Let me compute."}, TOOL_USE))
    )
    response = await client.chat([{"role": "user", "content": "6*7?"}], TOOLS)
    assert response.content == "Let me compute."
    assert response.reasoning == "Multiply first."
    assert [(c.id, c.name, json.loads(c.arguments)) for c in response.tool_calls] == [
        ("toolu_1", "calculator", {"expression": "6*7"})
    ]
    assert (response.tokens_in, response.tokens_out) == (12, 5)
    assert response.model == "claude-sonnet-5-5"
    assert response.blocks == [THINKING, {"type": "text", "text": "Let me compute."}, TOOL_USE]


@pytest.mark.anyio
async def test_empty_thinking_is_no_reasoning() -> None:
    empty = {"type": "thinking", "thinking": "", "signature": "s"}
    client, _ = client_for(ok(answer(empty, {"type": "text", "text": "42"})))
    response = await client.chat([{"role": "user", "content": "6*7?"}], [])
    assert (response.content, response.reasoning) == ("42", None)


@pytest.mark.anyio
async def test_a_tool_loop_sends_blocks_back_unchanged() -> None:
    """Thinking blocks must go back with their tool_use (preserved thinking)."""
    client, seen = client_for(
        ok(answer(THINKING, TOOL_USE)),
        ok(answer({"type": "text", "text": "42"})),
    )
    messages: list[Message] = [{"role": "user", "content": "6*7?"}]
    first = await client.chat(messages, TOOLS)
    messages.append(first.as_message())
    messages.append({"role": "tool", "tool_call_id": "toolu_1", "content": "42"})
    second = await client.chat(messages, TOOLS)
    assert second.content == "42"
    assert body_of(seen[1])["messages"] == [
        {"role": "user", "content": "6*7?"},
        {"role": "assistant", "content": [THINKING, TOOL_USE]},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "42"}],
        },
    ]


@pytest.mark.anyio
async def test_tool_results_merge_and_plain_assistant_messages_convert() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": "done"})))
    messages: list[Message] = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "Two calls.",
            "tool_calls": [
                {"id": "a", "type": "function", "function": calc('{"expression": "1"}')},
                {"id": "b", "type": "function", "function": calc("")},
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "tool", "tool_call_id": "b", "content": "error: no expression"},
        {"role": "assistant", "content": "Both done."},
        {"role": "user", "content": "thanks"},
    ]
    await client.chat(messages, TOOLS)
    assert body_of(seen[0])["messages"][1:] == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Two calls."},
                {"type": "tool_use", "id": "a", "name": "calculator", "input": {"expression": "1"}},
                {"type": "tool_use", "id": "b", "name": "calculator", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "1"},
                {"type": "tool_result", "tool_use_id": "b", "content": "error: no expression"},
            ],
        },
        {"role": "assistant", "content": "Both done."},
        {"role": "user", "content": "thanks"},
    ]


@pytest.mark.anyio
async def test_a_later_system_message_stays_in_place() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": "ok"})))
    messages: list[Message] = [
        {"role": "system", "content": "One."},
        {"role": "system", "content": "Two."},
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "Later."},
    ]
    await client.chat(messages, [])
    body = body_of(seen[0])
    assert body["system"] == "One.\n\nTwo."
    assert body["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "Later."},
    ]


@pytest.mark.anyio
async def test_thinking_off_is_between_tools() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": "ok"})))
    await client.chat([{"role": "user", "content": "hi"}], TOOLS, reasoning=False)
    body = body_of(seen[0])
    assert body["thinking"] == {"type": "between_tools"}
    assert body["output_config"] == {"effort": "medium"}


@pytest.mark.anyio
async def test_structured_output() -> None:
    client, seen = client_for(ok(answer({"type": "text", "text": '{"route": "math"}'})))
    schema = {
        "type": "object",
        "properties": {
            "route": {"type": "string", "minLength": 1, "maxLength": 20},
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
        },
        "required": ["route"],
    }
    response_format = {"type": "json_schema", "json_schema": {"name": "r", "schema": schema}}
    response = await client.chat(
        [{"role": "user", "content": "route"}], [], response_format=response_format
    )
    assert response.content == '{"route": "math"}'
    assert body_of(seen[0])["output_config"] == {
        "effort": "medium",
        "format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {"route": {"type": "string"}, "score": {"type": "integer"}},
                "required": ["route", "score"],
                "additionalProperties": False,
            },
        },
    }


@pytest.mark.anyio
async def test_a_refusal_is_an_error() -> None:
    refusal = answer(stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber"})
    client, _ = client_for(ok(refusal))
    with pytest.raises(LLMError, match=r"declined \(cyber\)"):
        await client.chat([{"role": "user", "content": "x"}], [])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"type": "error", "error": {"message": "bad"}}),
        httpx.Response(429, json={"type": "error", "error": {"message": "slow down"}}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_errors_become_llm_error(response: httpx.Response) -> None:
    client, _ = client_for(response)
    with pytest.raises(LLMError):
        await client.chat([{"role": "user", "content": "x"}], [])


@pytest.mark.anyio
async def test_transport_error_becomes_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = AnthropicClient(
        base_url="https://claude.test/v1",
        model="claude-sonnet-5-5",
        api_key=KEY,
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMError, match="request failed"):
        await client.chat([{"role": "user", "content": "x"}], [])


def test_as_message_carries_blocks() -> None:
    response = ChatResponse(content="hi", blocks=[{"type": "text", "text": "hi"}])
    assert response.as_message() == {
        "role": "assistant",
        "content": "hi",
        "blocks": [{"type": "text", "text": "hi"}],
    }
    assert "blocks" not in ChatResponse(content="hi").as_message()


@pytest.mark.anyio
async def test_answer_without_tools_after_a_tool_call() -> None:
    """The routing template's last call offers no tools after a tool call.

    Claude needs the tools of earlier tool_use blocks defined, so they are declared and not
    callable, and the thinking blocks go: a changed tool list would invalidate them.
    """
    client, seen = client_for(ok(answer({"type": "text", "text": "42"})))
    messages: list[Message] = [
        {"role": "user", "content": "6*7?"},
        {"role": "assistant", "content": None, "blocks": [THINKING, TOOL_USE]},
        {"role": "tool", "tool_call_id": "toolu_1", "content": "42"},
    ]
    await client.chat(messages, [])
    body = body_of(seen[0])
    assert body["tools"] == [
        {
            "name": "calculator",
            "description": "Not available for this answer.",
            "input_schema": {"type": "object"},
        }
    ]
    assert body["tool_choice"] == {"type": "none"}
    assert body["messages"][1] == {"role": "assistant", "content": [TOOL_USE]}


@pytest.mark.anyio
async def test_workspace_header_only_when_set() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(answer({"type": "text", "text": "hi"}))

    for workspace in ("wrkspc_1", ""):
        client = AnthropicClient(
            base_url="https://claude.test/v1",
            model="claude-sonnet-5-5",
            api_key=KEY,
            workspace_id=workspace,
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        await client.chat([{"role": "user", "content": "hi"}], [])
    assert seen[0].headers["anthropic-workspace-id"] == "wrkspc_1"
    assert "anthropic-workspace-id" not in seen[1].headers
