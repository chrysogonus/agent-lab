import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from agent_lab.llm.base import LLMError
from agent_lab.llm.openai_compat import OpenAICompatClient
from agent_lab.workflows.evaluator import Verdict
from agent_lab.workflows.orchestrator import plan_model
from agent_lab.workflows.routing import route_model

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


# --- M4: OpenAI request shapes (US2) ---


def openai_client(
    transport: httpx.MockTransport, reasoning_off: str = "none"
) -> OpenAICompatClient:
    return client_with(
        transport,
        provider="openai",
        reasoning_off={"reasoning_effort": reasoning_off} if reasoning_off else {},
        strict_schema=True,
    )


def decision(model_cls: type[BaseModel], name: str) -> dict[str, Any]:
    """The response format `steps.decide` sends."""
    schema = model_cls.model_json_schema()
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}


@pytest.mark.anyio
async def test_openai_thinking_off() -> None:
    transport, bodies = recording()
    await openai_client(transport).chat([], [], reasoning=False)
    await openai_client(transport, reasoning_off="").chat([], [], reasoning=False)
    assert bodies[0]["reasoning_effort"] == "none"
    assert "chat_template_kwargs" not in bodies[0]
    assert "reasoning_effort" not in bodies[1] and "chat_template_kwargs" not in bodies[1]


@pytest.mark.anyio
async def test_openai_reasoning_on_adds_nothing() -> None:
    transport, bodies = recording()
    for reasoning in (True, None):
        await openai_client(transport).chat([], [], reasoning=reasoning)
    assert bodies == [{"model": "m1", "messages": [], "stream": False}] * 2


@pytest.mark.anyio
async def test_openai_strict_schema() -> None:
    transport, bodies = recording()
    client = openai_client(transport)
    for model_cls, name in [
        (route_model(["math", "general"]), "route"),
        (plan_model(3), "plan"),
        (Verdict, "verdict"),
    ]:
        await client.chat([], [], response_format=decision(model_cls, name))

    route, plan, verdict = (b["response_format"]["json_schema"] for b in bodies)
    assert route == {
        "name": "route",
        "strict": True,
        "schema": {
            "properties": {
                "label": {"enum": ["math", "general"], "title": "Label", "type": "string"}
            },
            "required": ["label"],
            "title": "Route",
            "type": "object",
            "additionalProperties": False,
        },
    }
    assert plan["schema"] == {
        "properties": {
            "subtasks": {
                "items": {"type": "string"},  # length bounds dropped; pydantic still checks them
                "maxItems": 3,
                "minItems": 1,
                "title": "Subtasks",
                "type": "array",
            }
        },
        "required": ["subtasks"],
        "title": "Plan",
        "type": "object",
        "additionalProperties": False,
    }
    assert verdict["schema"]["additionalProperties"] is False
    assert verdict["schema"]["required"] == ["approved", "feedback"]


@pytest.mark.anyio
async def test_local_schema_unchanged() -> None:
    transport, bodies = recording()
    format_ = decision(plan_model(3), "plan")
    await client_with(transport).chat([], [], response_format=format_)
    assert bodies[0]["response_format"] == format_


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["local", "openai"])
async def test_only_known_parameters(provider: str) -> None:
    """Each provider gets only the fields it accepts (SC-003)."""
    transport, bodies = recording()
    client = client_with(transport) if provider == "local" else openai_client(transport)
    thinking_off = {
        "local": {"reasoning_effort", "chat_template_kwargs"},
        "openai": {"reasoning_effort"},
    }[provider]
    format_ = decision(route_model(["a", "b"]), "route")
    for reasoning in (False, True, None):
        await client.chat([], TOOLS, reasoning=reasoning)
        await client.chat([], [], response_format=format_, reasoning=reasoning)
    allowed = {"model", "messages", "stream", "tools", "response_format"} | thinking_off
    assert all(set(body) <= allowed for body in bodies)
    assert any(set(body) & thinking_off == thinking_off for body in bodies)


@pytest.mark.anyio
async def test_tool_call_parsing_openai() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        call = {
            "id": "call_9",
            "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression": "2*3"}'},
        }
        message = {"role": "assistant", "content": None, "tool_calls": [call]}
        usage = {"prompt_tokens": 5, "completion_tokens": 3}
        return httpx.Response(
            200,
            json={"model": "gpt-6-luna-2026", "choices": [{"message": message}], "usage": usage},
        )

    result = await openai_client(httpx.MockTransport(handler)).chat([], TOOLS)
    assert [(c.id, c.name, c.arguments) for c in result.tool_calls] == [
        ("call_9", "calculator", '{"expression": "2*3"}')
    ]
    assert (result.tokens_in, result.tokens_out, result.model) == (5, 3, "gpt-6-luna-2026")
