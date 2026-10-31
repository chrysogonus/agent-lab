"""Agents on a mock OpenAI endpoint: every template shape works (US2), failures end runs (US3)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import assert_trace_valid
from test_agents_api import LUNA, new_agent, run_to_end
from test_api import BASE

from agent_lab.api import create_app
from agent_lab.graph import Graph
from agent_lab.llm.fake import FakeLLM
from agent_lab.llm.models import ModelEntry, ModelRef, Models
from agent_lab.llm.openai_compat import OpenAICompatClient
from agent_lab.store import Store
from agent_lab.tracing.span import Span

KEY = "sk-openai-test-0123456789abcdef"
Body = dict[str, Any]
Reply = Callable[[Body], httpx.Response]


def message(**fields: Any) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", **fields}}]})


def scripted(decisions: dict[str, list[Any]]) -> Reply:
    """Answers like a model: the next scripted decision for a structured request, one tool
    call when tools are offered and none was answered yet, otherwise text."""

    def reply(body: Body) -> httpx.Response:
        if "response_format" in body:
            name = body["response_format"]["json_schema"]["name"]
            return message(content=json.dumps(decisions[name].pop(0)))
        tools: list[Body] = body.get("tools") or []
        if tools and not any(m["role"] == "tool" for m in body["messages"]):
            name: str = tools[0]["function"]["name"]
            arguments = {"calculator": {"expression": "6*7"}, "get_weather": {"city": "Oslo"}}
            call = {"name": name, "arguments": json.dumps(arguments[name])}
            return message(
                content=None, tool_calls=[{"id": "c1", "type": "function", "function": call}]
            )
        return message(content="- one\n- two\n- three")

    return reply


def openai_app(store: Store, reply: Reply) -> tuple[TestClient, list[Body]]:
    """The app with Local (an empty FakeLLM) and OpenAI on a mock transport."""
    bodies: list[Body] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return reply(bodies[-1])

    openai = OpenAICompatClient(
        base_url="https://openai.test/v1",
        model="gpt-6-luna",
        api_key=KEY,
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        provider="openai",
        reasoning_off={"reasoning_effort": "none"},
        strict_schema=True,
    )
    local = FakeLLM([], provider="local")
    local_ref = ModelRef(provider="local", model=local.model)
    models = Models(
        [
            ModelEntry(local_ref, False, None, local),
            ModelEntry(ModelRef.model_validate(LUNA), True, None, openai),
        ],
        local_ref,
    )
    return TestClient(create_app(store=store, models=models, secrets=(KEY,)), base_url=BASE), bodies


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


DECISIONS: dict[str, dict[str, list[Any]]] = {
    "react": {},
    "chain": {},
    "routing": {"route": [{"label": "math"}]},
    "parallel": {},
    "orchestrator": {"plan": [{"subtasks": ["first part", "second part"]}]},
    "evaluator": {
        "verdict": [
            {"approved": False, "feedback": "shorter"},
            {"approved": True, "feedback": ""},
        ]
    },
}


@pytest.mark.parametrize("template_id", list(DECISIONS))
def test_every_template_shape_runs_on_openai(store: Store, template_id: str) -> None:
    client, bodies = openai_app(store, scripted(DECISIONS[template_id]))
    with client:
        agent = new_agent(client, template_id, model=LUNA)
        run, spans = run_to_end(client, agent["id"], agent["sample_prompt"])

    assert run["status"] == "completed", run
    assert_trace_valid(Graph.model_validate(run["graph"]), [Span.model_validate(s) for s in spans])
    assert {s["attributes"]["gen_ai.provider.name"] for s in spans if s["kind"] == "llm"} == {
        "openai"
    }
    for body in bodies:
        assert body["model"] == "gpt-6-luna"
        # Thinking off sends OpenAI's own field; ReAct's template keeps reasoning on.
        assert body.get("reasoning_effort") == (None if template_id == "react" else "none")
        assert "chat_template_kwargs" not in body
        if "response_format" in body:
            assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    if template_id == "react":
        assert any(s["kind"] == "tool" for s in spans)  # native tool calling (US2-4)


def test_off_schema_route_falls_back(store: Store) -> None:
    client, _ = openai_app(store, scripted({"route": [{"label": "sports"}]}))
    with client:
        agent = new_agent(client, "routing", model=LUNA)
        run, spans = run_to_end(client, agent["id"], "Who won?")
    assert run["status"] == "completed"
    assert "general" in {s["node_id"] for s in spans}  # the fallback route, as in M2


def test_over_long_plan_ends_run_error(store: Store) -> None:
    plan = {"subtasks": [f"part {i}" for i in range(5)]}  # the template allows 4
    client, _ = openai_app(store, scripted({"plan": [plan]}))
    with client:
        agent = new_agent(client, "orchestrator", model=LUNA)
        run, _ = run_to_end(client, agent["id"], "Write a guide")
    assert run["status"] == "error"
