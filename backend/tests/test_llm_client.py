import json
from typing import Any

import httpx
import pytest

from agent_lab.llm.base import LLMError
from agent_lab.llm.openai_compat import OpenAICompatClient

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "calculator", "parameters": {}}}
]


def client_with(
    handler: httpx.MockTransport, api_key: str = "", **settings: Any
) -> OpenAICompatClient:
    return OpenAICompatClient(
        base_url="http://llm.test/v1/",
        model="m1",
        api_key=api_key,
        http=httpx.AsyncClient(transport=handler),
        **settings,
    )


def recording() -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    """A transport that answers "{}" and records each request body."""
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    return httpx.MockTransport(handler), bodies


@pytest.mark.anyio
async def test_request_and_tool_call_parsing() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "m1-served",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": '{"expression": "1+1"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    client = client_with(httpx.MockTransport(handler), api_key="sk-test")
    messages = [{"role": "user", "content": "1+1?"}]
    result = await client.chat(messages, TOOLS)

    request = seen[0]
    assert str(request.url) == "http://llm.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {
        "model": "m1",
        "messages": messages,
        "stream": False,
        "tools": TOOLS,
    }
    assert result.tool_calls[0].name == "calculator"
    assert result.tool_calls[0].arguments == '{"expression": "1+1"}'
    assert (result.tokens_in, result.tokens_out, result.model) == (11, 7, "m1-served")


@pytest.mark.anyio
async def test_no_auth_header_without_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    result = await client_with(httpx.MockTransport(handler)).chat([], [])
    assert "authorization" not in seen[0].headers
    assert "tools" not in json.loads(seen[0].content)
    assert result.content == "hi"
    assert result.tool_calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, text="boom"), httpx.Response(200, json={"nope": 1})],
)
async def test_errors_become_llm_error(response: httpx.Response) -> None:
    client = client_with(httpx.MockTransport(lambda _: response))
    with pytest.raises(LLMError):
        await client.chat([], [])


@pytest.mark.anyio
async def test_transport_error_becomes_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMError):
        await client_with(httpx.MockTransport(handler)).chat([], [])


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["reasoning", "reasoning_content"])
async def test_reasoning_parsed(field: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        message = {"role": "assistant", "content": "5", field: "2 plus 3 is 5"}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    result = await client_with(httpx.MockTransport(handler)).chat([], [])
    assert (result.content, result.reasoning) == ("5", "2 plus 3 is 5")


@pytest.mark.anyio
async def test_response_format_and_reasoning_sent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = client_with(httpx.MockTransport(handler))
    schema: dict[str, Any] = {"type": "json_schema", "json_schema": {"name": "route"}}
    await client.chat([], [], response_format=schema, reasoning=False)
    await client.chat([], [], reasoning=True)
    await client.chat([], [])

    first, on, default = (json.loads(r.content) for r in seen)
    assert first["response_format"] == schema
    assert first["reasoning_effort"] == "none"
    assert first["chat_template_kwargs"] == {"enable_thinking": False}
    for body in (on, default):
        assert "response_format" not in body
        assert "reasoning_effort" not in body
        assert "chat_template_kwargs" not in body


@pytest.mark.anyio
async def test_local_body_unchanged() -> None:
    """The local provider sends exactly the M3 bodies (FR-009)."""
    transport, bodies = recording()
    client = client_with(transport)
    messages = [{"role": "user", "content": "hi"}]
    for reasoning in (False, True, None):
        await client.chat(messages, TOOLS, reasoning=reasoning)

    base = {"model": "m1", "messages": messages, "stream": False, "tools": TOOLS}
    assert bodies == [
        {
            **base,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        },
        base,
        base,
    ]
    assert client.provider == "local"


@pytest.mark.anyio
async def test_reasoning_off_fields_are_configurable() -> None:
    transport, bodies = recording()
    await client_with(transport, reasoning_off={}).chat([], [], reasoning=False)
    await client_with(transport, reasoning_off={"reasoning_effort": "low"}).chat(
        [], [], reasoning=False
    )
    assert bodies == [
        {"model": "m1", "messages": [], "stream": False},
        {"model": "m1", "messages": [], "stream": False, "reasoning_effort": "low"},
    ]
