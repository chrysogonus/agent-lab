import pytest
from helpers import answer, assert_trace_valid, ended, json_answer, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.evaluator import AGENT_ID, Config, EvaluatorWorkflow, build_graph

APPROVE = json_answer({"approved": True, "feedback": ""})


async def run(script: list[ScriptItem]) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    workflow = EvaluatorWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("SunSip charger")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([answer(" SunSip: sunshine to go "), APPROVE])

    assert (outcome.status, outcome.answer) == ("completed", "SunSip: sunshine to go")
    assert_trace_valid(build_graph(), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    assert taken_edges(spans) == {
        ("start", "generator"),
        ("generator", "evaluator"),
        ("evaluator", "end"),
    }


@pytest.mark.anyio
async def test_approved_round_two() -> None:
    reject = json_answer({"approved": False, "feedback": "Mention SunSip."})
    outcome, spans, llm = await run(
        [answer("Charge anywhere"), reject, answer("SunSip charges anywhere"), APPROVE]
    )

    assert (outcome.status, outcome.answer) == ("completed", "SunSip charges anywhere")
    second_prompt = llm.calls[2][-1]["content"]
    assert "Charge anywhere" in second_prompt and "Mention SunSip." in second_prompt
    rounds = [(s.name, s.attributes["lab.round"]) for s in spans if "lab.round" in s.attributes]
    assert rounds == [
        ("chat fake-model", 1),
        ("verdict", 1),
        ("chat fake-model", 2),
        ("verdict", 2),
    ]
    verdicts = [s.output for s in spans if s.name == "verdict"]
    assert verdicts == [
        {"approved": False, "feedback": "Mention SunSip."},
        {"approved": True, "feedback": ""},
    ]
    assert ("evaluator", "generator") in taken_edges(spans)
    assert_trace_valid(build_graph(), spans)
