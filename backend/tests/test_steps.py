from typing import Literal

import pytest
from helpers import answer, ended, json_answer, make_ctx
from pydantic import BaseModel

from agent_lab.agents import steps
from agent_lab.agents.steps import DecisionError
from agent_lab.llm.base import ToolCall
from agent_lab.llm.fake import FakeLLM
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tracing.span import SpanKind


class Route(BaseModel):
    label: Literal["math", "general"]


MESSAGES = steps.messages("classify", "2+2?")


@pytest.mark.anyio
async def test_chat_records_reasoning_and_came_from() -> None:
    llm = FakeLLM([answer("hi")])
    ctx, events = make_ctx(llm, reasoning=False)
    await steps.chat(ctx, "n", MESSAGES, came_from=["start", "start"], attributes={"lab.round": 1})

    span = ended(events)[0]
    assert llm.requests[0]["reasoning"] is False
    assert span.attributes["lab.reasoning"] is False
    assert span.attributes["lab.came_from"] == ["start"]
    assert span.attributes["lab.round"] == 1
    assert "gen_ai.request.response_format" not in span.attributes


@pytest.mark.anyio
async def test_decide_sends_schema_and_validates() -> None:
    llm = FakeLLM([json_answer({"label": "math"})])
    ctx, events = make_ctx(llm)
    route = await steps.decide(
        ctx, "router", "route", MESSAGES, Route, kind=SpanKind.ROUTE, came_from=["start"]
    )

    assert route == Route(label="math")
    decision, call = ended(events)
    sent = llm.requests[0]["response_format"]
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["schema"] == Route.model_json_schema()
    assert decision.kind == SpanKind.ROUTE
    assert (decision.name, decision.node_id) == ("route", "router")
    assert decision.input["schema"] == Route.model_json_schema()
    assert decision.output == {"label": "math"}
    assert decision.attributes["lab.came_from"] == ["start"]
    # The llm call is nested at the same node, so it records no edge.
    assert call.parent_span_id == decision.span_id
    assert "lab.came_from" not in call.attributes
    assert call.attributes["gen_ai.request.response_format"] == sent


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    ['Sure! {"label": "math"} is my answer.', '```json\n{"label": "math"}\n```'],
)
async def test_decide_extracts_json_from_prose(content: str) -> None:
    ctx, _ = make_ctx(FakeLLM([answer(content)]))
    assert await steps.decide(ctx, "router", "route", MESSAGES, Route) == Route(label="math")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    ["not json", '{"label": "sports"}', '{"label": "math"} or {"label": "general"}', ""],
)
async def test_decide_rejects_invalid(content: str) -> None:
    ctx, events = make_ctx(FakeLLM([answer(content)]))
    with pytest.raises(DecisionError):
        await steps.decide(ctx, "router", "route", MESSAGES, Route)

    decision = ended(events)[0]
    assert decision.error is not None
    assert decision.error.startswith("invalid route:")
    assert repr(content[:200]) in decision.error
    assert decision.output is None


@pytest.mark.anyio
async def test_call_tool_on_own_node() -> None:
    ctx, events = make_ctx(FakeLLM([]))
    call = ToolCall(id="c1", name="calculator", arguments='{"expression": "2+3"}')
    tools = {"calculator": CALCULATOR}
    assert await steps.call_tool(ctx, tools, call, caller="x", node_id="calc") == "5"
    await steps.call_tool(ctx, tools, call, caller="x")
    assert [s.node_id for s in ended(events)] == ["calc", "tool:calculator"]
