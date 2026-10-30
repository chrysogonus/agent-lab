import pytest
from helpers import answer, assert_trace_valid, ended, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.chain import AGENT_ID, ChainWorkflow, Config, build_graph

OUTLINE = "- tracks every sip\n- glows when you should drink\n- keeps water cold"


async def run(script: list[ScriptItem]) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    workflow = ChainWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("smart bottle")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([answer(OUTLINE), answer("draft"), answer("final blurb")])

    assert (outcome.status, outcome.answer) == ("completed", "final blurb")
    assert_trace_valid(build_graph(), spans)
    assert {s.agent_id for s in spans} == {AGENT_ID}
    assert all(r["reasoning"] is False for r in llm.requests)
    gate = next(s for s in spans if s.name == "gate")
    assert gate.output == {"passed": True, "reason": "3 bullet lines"}
    assert OUTLINE in llm.calls[1][-1]["content"]  # the outline feeds the draft
    assert llm.calls[2][-1]["content"] == "draft"
    assert taken_edges(spans) == {
        ("start", "outline"),
        ("outline", "gate"),
        ("gate", "draft"),
        ("draft", "polish"),
        ("polish", "end"),
    }


@pytest.mark.anyio
async def test_gate_fails_stops_chain() -> None:
    outcome, spans, llm = await run([answer("- only one\n- and two\njust prose")])

    assert (outcome.status, outcome.answer) == ("error", None)
    gate = next(s for s in spans if s.name == "gate")
    assert gate.error == "outline has 2 bullet lines, needs at least 3"
    assert gate.output == {"passed": False, "reason": gate.error}
    assert len(llm.calls) == 1  # no draft or polish
    assert {s.node_id for s in spans} == {"start", "outline", "gate", "end"}
    assert spans[-1].error == f"gate failed: {gate.error}"
    assert taken_edges(spans) == {("start", "outline"), ("outline", "gate"), ("gate", "end")}
    assert_trace_valid(build_graph(), spans)
