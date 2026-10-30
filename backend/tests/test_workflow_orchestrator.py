import pytest
from helpers import answer, assert_trace_valid, ended, json_answer, make_tracer

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.orchestrator import AGENT_ID, Config, OrchestratorWorkflow, build_graph


async def run(script: list[ScriptItem], delay: float = 0) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script, delay=delay)
    tracer, events = make_tracer(AGENT_ID)
    workflow = OrchestratorWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("Porto weekend")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    plan = json_answer({"subtasks": ["getting there", "food"]})
    outcome, spans, llm = await run([plan, answer("part"), answer("part"), answer("note")])

    assert (outcome.status, outcome.answer) == ("completed", "note")
    assert_trace_valid(build_graph(), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    assert [s.name for s in spans if s.node_id == "worker" and s.kind == "step"] == [
        "worker 0",
        "worker 1",
    ]
    synth_input = llm.calls[3][-1]["content"]
    assert "getting there" in synth_input and "food" in synth_input
