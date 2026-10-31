import pytest
from helpers import answer, assert_trace_valid, ended, json_answer, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.evaluator import AGENT_ID, Config, EvaluatorWorkflow, build_graph

APPROVE = json_answer({"approved": True, "feedback": ""})


async def run(
    script: list[ScriptItem], config: Config | None = None
) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    config = config or Config(model=llm.model)
    workflow = EvaluatorWorkflow(llm=llm, config=config, tracer=tracer)
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


@pytest.mark.anyio
async def test_never_approves() -> None:
    reject = json_answer({"approved": False, "feedback": "Shorter."})
    script: list[ScriptItem] = []
    for i in range(3):
        script += [answer(f"draft {i + 1}"), reject]
    outcome, spans, llm = await run(script)

    assert (outcome.status, outcome.answer) == ("max_iterations", "draft 3")
    assert len(llm.calls) == 6
    assert spans[-1].error == "not approved after 3 rounds"
    assert spans[0].error == spans[-1].error
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_invalid_verdict_counts_as_rejection() -> None:
    outcome, spans, llm = await run(
        [answer("draft 1"), answer("looks great!"), answer("draft 2"), APPROVE]
    )

    assert (outcome.status, outcome.answer) == ("completed", "draft 2")
    verdict = next(s for s in spans if s.name == "verdict")
    assert verdict.error is not None and verdict.error.startswith("invalid verdict:")
    # The validation error is the feedback for the next draft.
    assert verdict.error in llm.calls[2][-1]["content"]
    assert_trace_valid(build_graph(), spans)


REJECT = json_answer({"approved": False, "feedback": "Shorter."})


@pytest.mark.anyio
@pytest.mark.parametrize("rounds", [1, 5])
async def test_one_and_five_rounds(rounds: int) -> None:
    script: list[ScriptItem] = [
        answer(f"draft {i}") if i % 2 == 0 else REJECT for i in range(rounds * 2)
    ]
    outcome, spans, _ = await run(script, Config(model="m", max_rounds=rounds))

    assert (outcome.status, outcome.answer) == ("max_iterations", f"draft {(rounds - 1) * 2}")
    assert max(s.attributes.get("lab.round", 0) for s in spans) == rounds
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_approved_in_round_five() -> None:
    script: list[ScriptItem] = [*[answer("d"), REJECT] * 4, answer("final"), APPROVE]
    outcome, spans, _ = await run(script, Config(model="m", max_rounds=5))

    assert (outcome.status, outcome.answer) == ("completed", "final")
    assert_trace_valid(build_graph(), spans)
