"""Running an agent's cases as ordinary runs, one at a time (M17, FR-003, FR-003a, FR-008)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from helpers import answer, assert_trace_valid, fake_models, json_answer, tool_call

from agent_lab.bus import Bus
from agent_lab.evaluation.model import CaseFields, Evaluation
from agent_lab.evaluation.results import summarize
from agent_lab.evaluation.runner import (
    EvaluationConflict,
    Evaluations,
    NothingToEvaluate,
)
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelRef, Models, UnavailableModel
from agent_lab.mcp.host import Host
from agent_lab.runs import UnknownAgent
from agent_lab.store import CustomAgent, Store

pytestmark = pytest.mark.anyio


def by_prompt(_messages: list[Message]) -> ChatResponse:
    """Passes "good" prompts and fails the rest, whatever order they come in."""
    return answer("right" if "good" in (_messages[-1]["content"] or "") else "wrong")


def always(script_item: ScriptItem, times: int = 30) -> list[ScriptItem]:
    return [script_item] * times


def fields(name: str, prompt: str, **changes: Any) -> CaseFields:
    return CaseFields.model_validate(
        {
            "name": name,
            "prompt": prompt,
            "checks": [{"kind": "contains", "text": "right"}],
            **changes,
        }
    )


def saved_agent(store: Store, **config: Any) -> CustomAgent:
    return store.create_agent(
        template_id="react",
        name="Tested",
        description="",
        sample_prompt="hi",
        config={"reasoning": False, "tools": ["calculator"], **config},
    )


def lab(store: Store, models: Models) -> Evaluations:
    return Evaluations(
        store=store, models=models, host=Host(), bus=Bus(), secrets=(), live=LiveRuns()
    )


async def done(store: Store, evaluation: Evaluation) -> Evaluation:
    for _ in range(500):
        current = store.get_evaluation(evaluation.eval_id)
        assert current is not None
        if current.state != "running":
            return current
        await asyncio.sleep(0.01)
    raise AssertionError("the evaluation did not end")


class Hangs(FakeLLM):
    """Answers until its gate shuts: then a model call stays under way until the gate opens."""

    def __init__(self, script: list[ScriptItem], answered: int) -> None:
        super().__init__(script)
        self.answered = answered
        self.gate = asyncio.Event()

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        self.answered -= 1
        if self.answered < 0:
            await self.gate.wait()
        return await super().chat(
            messages, tools, response_format=response_format, reasoning=reasoning
        )


async def test_one_case_passing_and_one_failing_show_as_such(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    good = store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    bad = store.create_case(agent.agent_id, fields("Bad", "a bad prompt"))
    llm = FakeLLM(always(by_prompt))

    evaluation = await lab(store, fake_models(llm)).start(agent.agent_id, repeats=3)
    finished = await done(store, evaluation)

    assert finished.state == "finished"
    assert finished.ended_at is not None
    attempts = store.attempts(evaluation.eval_id)
    assert len(attempts) == 6
    summary = summarize(attempts)
    assert summary.cases[good.case_id].pass_rate == 1.0
    assert summary.cases[bad.case_id].pass_rate == 0.0
    assert summary.overall.pass_rate == 0.5
    failed = next(a for a in attempts if a.outcome == "fail")
    assert failed.reason == "the answer does not contain 'right': 'wrong'"
    assert failed.checks[0].expected == "contains 'right'"
    assert failed.run_id is not None
    assert failed.llm_calls == 1
    assert failed.tokens == 23  # helpers.answer: 20 in, 3 out
    assert [a.number for a in attempts if a.case_id == good.case_id] == [1, 2, 3]


async def test_every_attempt_is_a_stored_traced_run_kept_out_of_the_run_list(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    store.create_case(agent.agent_id, fields("Good", "a good prompt"))

    evaluation = await lab(store, fake_models(FakeLLM(always(by_prompt)))).start(
        agent.agent_id, repeats=1
    )
    await done(store, evaluation)

    attempt = store.attempts(evaluation.eval_id)[0]
    assert attempt.run_id is not None
    run = store.get_run(attempt.run_id)
    assert run is not None
    assert run.eval_id == evaluation.eval_id
    assert run.agent_id == agent.agent_id
    assert run.prompt == "a good prompt"
    assert_trace_valid(run.graph, store.get_spans(attempt.run_id))
    assert store.list_runs() == []


async def test_editing_the_agent_or_a_case_changes_only_later_evaluations(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store, system_prompt="the first prompt")
    case = store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    llm = Hangs(always(by_prompt), answered=1)

    evaluation = await lab(store, fake_models(llm)).start(agent.agent_id, repeats=2)
    await asyncio.sleep(0.05)  # the second attempt is waiting for the model
    store.update_agent(
        agent.agent_id,
        name="Tested",
        description="",
        sample_prompt="hi",
        config={"reasoning": False, "tools": ["calculator"], "system_prompt": "edited"},
    )
    store.update_case(case.case_id, fields("Good", "an edited prompt"))
    llm.gate.set()
    finished = await done(store, evaluation)

    assert [c[0]["content"] for c in llm.calls] == ["the first prompt", "the first prompt"]
    assert [c[1]["content"] for c in llm.calls] == ["a good prompt", "a good prompt"]
    assert finished.cases[0].prompt == "a good prompt"
    assert finished.config["system_prompt"] == "the first prompt"


async def test_stop_starts_no_further_attempt_and_keeps_the_finished_ones(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    llm = Hangs(always(by_prompt), answered=1)
    evaluations = lab(store, fake_models(llm))

    evaluation = await evaluations.start(agent.agent_id, repeats=5)
    await asyncio.sleep(0.05)
    assert evaluations.stop(evaluation.eval_id) is True
    finished = await done(store, evaluation)

    assert finished.state == "stopped"
    attempts = store.attempts(evaluation.eval_id)
    assert [a.outcome for a in attempts] == ["pass", "error"]  # a stopped run is an error (FR-004)
    assert attempts[1].reason == "the run was stopped"
    assert len(llm.calls) == 1  # the hanging call never finished; nothing started after it
    assert evaluations.stop(evaluation.eval_id) is False


async def test_only_one_evaluation_runs_at_a_time(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    llm = Hangs(always(by_prompt), answered=0)
    evaluations = lab(store, fake_models(llm))

    first = await evaluations.start(agent.agent_id, repeats=1)
    assert evaluations.running_for(agent.agent_id) is True
    with pytest.raises(EvaluationConflict):
        await evaluations.start(agent.agent_id, repeats=1)

    llm.gate.set()
    await done(store, first)
    await asyncio.sleep(0)
    assert evaluations.running_for(agent.agent_id) is False
    second = await evaluations.start(agent.agent_id, repeats=1)
    await done(store, second)


async def test_a_tool_on_no_connected_server_is_an_error_not_a_fail(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store, tools=["gone/tool"])
    case = store.create_case(agent.agent_id, fields("Good", "a good prompt"))

    evaluation = await lab(store, fake_models(FakeLLM([]))).start(agent.agent_id, repeats=2)
    finished = await done(store, evaluation)

    assert finished.state == "finished"
    attempts = store.attempts(evaluation.eval_id)
    assert [a.outcome for a in attempts] == ["error", "error"]
    assert attempts[0].run_id is None
    assert attempts[0].reason is not None
    assert "gone" in attempts[0].reason
    assert attempts[0].checks[0].result == "error"  # every check ends as something (FR-004)
    summary = summarize(attempts)
    assert summary.cases[case.case_id].pass_rate is None
    assert summary.cases[case.case_id].errors == 2


async def test_the_chosen_model_and_the_chosen_cases_are_what_runs(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    chosen = store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    store.create_case(agent.agent_id, fields("Other", "another good prompt"))
    local, hosted = FakeLLM([]), FakeLLM(always(by_prompt), model="hosted")
    model = ModelRef(provider="openai", model="hosted")

    evaluation = await lab(store, fake_models(local, hosted)).start(
        agent.agent_id, repeats=2, case_ids=[chosen.case_id], model=model
    )
    finished = await done(store, evaluation)

    assert finished.model == model
    assert len(hosted.calls) == 2
    assert local.calls == []
    assert {a.case_id for a in store.attempts(evaluation.eval_id)} == {chosen.case_id}


async def test_a_template_runs_its_examples(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    script: list[ScriptItem] = [
        tool_call("calculator", '{"expression": "17*23"}'),
        answer("391"),
        tool_call("get_weather", '{"city": "Berlin"}'),
        answer("Rain"),
    ]
    evaluation = await lab(store, fake_models(FakeLLM(script))).start("react", repeats=1)
    await done(store, evaluation)
    assert [a.outcome for a in store.attempts(evaluation.eval_id)] == ["pass", "pass"]


async def test_a_judge_check_decides_on_the_evaluations_model(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    judged = {"kind": "judge", "question": "Is it right?"}
    store.create_case(agent.agent_id, fields("Judged", "a good prompt", checks=[judged]))
    llm = FakeLLM([answer("right"), json_answer({"answer": "no"})])

    evaluation = await lab(store, fake_models(llm)).start(agent.agent_id, repeats=1)
    await done(store, evaluation)

    attempt = store.attempts(evaluation.eval_id)[0]
    assert attempt.outcome == "fail"
    assert attempt.reason == "the judge answered no"
    assert attempt.llm_calls == 1  # the judge's call is its own run, outside the attempt
    judge_run_id = attempt.checks[0].judge_run_id
    assert judge_run_id is not None
    assert judge_run_id != attempt.run_id


async def test_a_stopped_attempt_asks_no_judge(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    judged = {"kind": "judge", "question": "Is it right?"}
    store.create_case(agent.agent_id, fields("Judged", "a good prompt", checks=[judged]))
    llm = Hangs([], answered=0)
    evaluations = lab(store, fake_models(llm))

    evaluation = await evaluations.start(agent.agent_id, repeats=1)
    await asyncio.sleep(0.05)
    evaluations.stop(evaluation.eval_id)
    await done(store, evaluation)

    check = store.attempts(evaluation.eval_id)[0].checks[0]
    assert check.result == "error"
    assert check.judge_run_id is None


async def test_what_cannot_start_says_so(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    evaluations = lab(store, fake_models(FakeLLM([])))

    with pytest.raises(UnknownAgent):
        await evaluations.start("nobody", repeats=1)
    with pytest.raises(NothingToEvaluate):  # no cases yet
        await evaluations.start(agent.agent_id, repeats=1)
    case = store.create_case(agent.agent_id, fields("Good", "a good prompt"))
    with pytest.raises(NothingToEvaluate):
        await evaluations.start(agent.agent_id, repeats=1, case_ids=["unknown"])
    with pytest.raises(UnavailableModel):
        await evaluations.start(
            agent.agent_id,
            repeats=1,
            case_ids=[case.case_id],
            model=ModelRef(provider="openai", model="absent"),
        )
    assert store.list_evaluations(agent.agent_id) == []


async def test_the_default_budget_is_recorded_for_an_agent_without_one(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    store.create_case(agent.agent_id, fields("Good", "a good prompt"))

    evaluation = await lab(store, fake_models(FakeLLM(always(by_prompt)))).start(
        agent.agent_id, repeats=1
    )
    finished = await done(store, evaluation)

    assert finished.harness["default_budget"] is True
    assert finished.harness["budget"]["model_calls"] == 30
    stored_agent = store.get_agent(agent.agent_id)
    assert stored_agent is not None
    assert stored_agent.harness is None  # the agent itself stays without one
    attempt = store.attempts(evaluation.eval_id)[0]
    assert attempt.run_id is not None
    run = store.get_run(attempt.run_id)
    assert run is not None
    assert run.harness == finished.harness


BIG = ChatResponse(content="right", tokens_in=300_000, tokens_out=1)


async def test_an_agent_without_a_budget_is_held_to_the_default_in_an_evaluation(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    store.create_case(agent.agent_id, fields("Good", "a good prompt"))

    evaluation = await lab(store, fake_models(FakeLLM([BIG]))).start(agent.agent_id, repeats=1)
    await done(store, evaluation)

    attempt = store.attempts(evaluation.eval_id)[0]
    assert attempt.outcome == "fail"
    assert attempt.reason == (
        "the run ended over_budget: tokens: 300,001 of 200,000 (the default budget)"
    )
    assert store.get_agent(agent.agent_id) is not None


async def test_a_check_expecting_the_budget_to_run_out_makes_it_a_pass(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = saved_agent(store)
    ends_over = {"kind": "end_state", "state": "over_budget"}
    store.create_case(agent.agent_id, fields("Over", "a good prompt", checks=[ends_over]))

    evaluation = await lab(store, fake_models(FakeLLM([BIG]))).start(agent.agent_id, repeats=1)
    await done(store, evaluation)

    assert store.attempts(evaluation.eval_id)[0].outcome == "pass"


async def test_the_judges_call_does_not_count_against_the_agents_budget(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="react",
        name="One call",
        description="",
        sample_prompt="hi",
        config={"reasoning": False},
        harness={
            "budget": {"model_calls": 1, "tokens": 1000, "tool_calls": 1, "seconds": 60},
            "ask_first": [],
        },
    )
    judged = {"kind": "judge", "question": "Is it right?"}
    store.create_case(agent.agent_id, fields("Judged", "a good prompt", checks=[judged]))
    llm = FakeLLM([answer("right"), json_answer({"answer": "yes"})])

    evaluation = await lab(store, fake_models(llm)).start(agent.agent_id, repeats=1)
    finished = await done(store, evaluation)

    assert store.attempts(evaluation.eval_id)[0].outcome == "pass"
    assert finished.harness["default_budget"] is False
    assert finished.harness["budget"]["model_calls"] == 1


async def test_a_case_says_what_happens_to_approval_requests(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="react",
        name="Asks first",
        description="",
        sample_prompt="hi",
        config={"reasoning": False, "tools": ["calculator"]},
        harness={"budget": None, "ask_first": ["calculator"]},
    )
    calls = {"kind": "tool_called", "tool": "calculator"}
    store.create_case(agent.agent_id, fields("Denied", "first", checks=[calls]))
    store.create_case(
        agent.agent_id, fields("Approved", "second", checks=[calls], approvals="approve")
    )
    add = '{"expression": "1+1"}'
    script: list[ScriptItem] = [
        tool_call("calculator", add),  # Approved, by name
        answer("2"),
        tool_call("calculator", add),  # Denied
        answer("All right."),
    ]

    evaluation = await lab(store, fake_models(FakeLLM(script))).start(agent.agent_id, repeats=1)
    await done(store, evaluation)

    outcomes = {a.case_id: a for a in store.attempts(evaluation.eval_id)}
    by_name = {c.name: outcomes[c.case_id] for c in store.list_cases(agent.agent_id)}
    assert by_name["Approved"].outcome == "pass"
    assert by_name["Denied"].outcome == "fail"  # the tool was not called
    assert by_name["Denied"].tool_calls == 0
    run_id = by_name["Denied"].run_id
    assert run_id is not None
    decision = next(s for s in store.get_spans(run_id) if s.name.startswith("approval "))
    assert decision.attributes["lab.approval.by"] == "case"
