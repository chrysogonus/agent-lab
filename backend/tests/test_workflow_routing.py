import pytest
from helpers import answer, assert_trace_valid, ended, json_answer, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span, SpanKind
from agent_lab.workflows.routing import AGENT_ID, Config, RoutingWorkflow, build_graph


async def run(script: list[ScriptItem]) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    workflow = RoutingWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("question")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([json_answer({"label": "general"}), answer("Paris")])

    assert (outcome.status, outcome.answer) == ("completed", "Paris")
    assert_trace_valid(build_graph(), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    route = next(s for s in spans if s.kind == SpanKind.ROUTE)
    assert route.output == {"label": "general"}
    assert taken_edges(spans) == {("start", "router"), ("router", "general"), ("general", "end")}
