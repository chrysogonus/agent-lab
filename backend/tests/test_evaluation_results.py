"""Outcomes, pass rates and comparisons (M17, FR-004, FR-004a, FR-006, FR-007)."""

from typing import Any

import pytest

from agent_lab.agents.react import build_graph
from agent_lab.evaluation.model import Attempt, CaseFields, CheckResult, Evaluation, Outcome
from agent_lab.evaluation.results import (
    attempt_outcome,
    compare,
    fingerprint,
    frozen_case,
    summarize,
)
from agent_lab.llm.models import ModelRef
from agent_lab.store import Run, RunStatus


def run(status: RunStatus) -> Run:
    return Run(
        run_id="r",
        agent_id="a",
        config_version="v",
        prompt="p",
        status=status,
        graph=build_graph([]),
        config={},
        started_at=1.0,
    )


def result(outcome: str, kind: str = "contains", reason: str | None = None) -> CheckResult:
    return CheckResult.model_validate(
        {"kind": kind, "expected": "x", "result": outcome, "reason": reason}
    )


GOOD, BAD, BROKEN = result("pass"), result("fail", reason="nope"), result("error", reason="broke")
EXPECTS_THE_END = result("pass", kind="end_state")
EXPECTS_ANOTHER_END = result("fail", kind="end_state", reason="other")


@pytest.mark.parametrize(
    ("the_run", "checks", "outcome"),
    [
        (None, [GOOD], "error"),  # refused before its first step
        (run("error"), [GOOD], "error"),
        (run("stopped"), [GOOD], "error"),
        (run("error"), [EXPECTS_THE_END], "error"),  # rule 1 comes before an expected end
        (run("over_budget"), [GOOD], "fail"),
        (run("max_iterations"), [GOOD], "fail"),
        (run("over_budget"), [EXPECTS_THE_END, GOOD], "pass"),
        (run("over_budget"), [EXPECTS_ANOTHER_END, GOOD], "fail"),
        (run("over_budget"), [EXPECTS_THE_END, BAD], "fail"),
        (run("completed"), [BAD], "fail"),
        (run("completed"), [BAD, BROKEN], "fail"),  # a failed check outranks an error
        (run("completed"), [BROKEN, GOOD], "error"),
        (run("completed"), [GOOD, GOOD], "pass"),
    ],
)
def test_an_attempts_outcome_follows_the_order_of_fr_004(
    the_run: Run | None, checks: list[CheckResult], outcome: Outcome
) -> None:
    assert attempt_outcome(the_run, checks)[0] == outcome


def test_an_outcome_says_why() -> None:
    assert attempt_outcome(run("completed"), [GOOD, BAD])[1] == "nope"
    assert attempt_outcome(run("over_budget"), [GOOD])[1] == "the run ended over_budget"
    assert attempt_outcome(run("completed"), [GOOD])[1] is None


def attempt(case_id: str, outcome: Outcome, number: int = 1, **fields: Any) -> Attempt:
    return Attempt(eval_id="e", case_id=case_id, number=number, outcome=outcome, **fields)


def test_rates_leave_errors_out_and_pool_attempts_instead_of_averaging_cases() -> None:
    attempts = [
        attempt("a", "pass"),
        attempt("a", "error", run_id=None),
        attempt("b", "pass"),
        attempt("b", "fail"),
        attempt("b", "fail"),
    ]
    summary = summarize(attempts)
    assert summary.cases["a"].pass_rate == 1.0  # 1 of 1 that is not an error
    assert summary.cases["a"].errors == 1
    assert summary.cases["b"].pass_rate == pytest.approx(1 / 3)
    assert summary.overall.pass_rate == pytest.approx(2 / 4)  # the average of cases would be 2/3


def test_a_case_with_only_errors_has_no_rate_and_adds_nothing_overall() -> None:
    summary = summarize([attempt("a", "error"), attempt("b", "pass")])
    assert summary.cases["a"].pass_rate is None
    assert summary.overall.pass_rate == 1.0
    assert summarize([attempt("a", "error")]).overall.pass_rate is None


def test_averages_cover_attempts_that_ran_only() -> None:
    summary = summarize(
        [
            attempt("a", "pass", run_id="1", llm_calls=2, tokens=100, wall_ms=10, tool_calls=0),
            attempt("a", "fail", run_id="2", llm_calls=4, tokens=300, wall_ms=30, tool_calls=2),
            attempt("a", "error"),
        ]
    )
    assert summary.overall.avg_llm_calls == 3.0
    assert summary.overall.avg_tokens == 200.0
    assert summary.overall.avg_wall_ms == 20.0
    assert summarize([attempt("a", "error")]).overall.avg_tokens is None


FIELDS: dict[str, Any] = {
    "name": "Case",
    "prompt": "p",
    "checks": [{"kind": "contains", "text": "x"}],
}


def case(**changes: Any) -> CaseFields:
    return CaseFields.model_validate({**FIELDS, **changes})


def test_a_fingerprint_changes_with_what_the_case_does_not_its_name() -> None:
    base = fingerprint(case())
    assert fingerprint(case(name="Renamed")) == base
    assert fingerprint(case(prompt="other")) != base
    assert fingerprint(case(approvals="approve")) != base
    assert fingerprint(case(checks=[{"kind": "contains", "text": "y"}])) != base


def evaluation(eval_id: str, version: str, **cases: CaseFields) -> Evaluation:
    return Evaluation(
        eval_id=eval_id,
        agent_id="a",
        agent_name="A",
        config_version=version,
        config={},
        harness={"budget": None, "ask_first": [], "default_budget": False},
        model=ModelRef(provider="local", model="m"),
        repeats=2,
        cases=[frozen_case(case_id, fields) for case_id, fields in cases.items()],
        state="finished",
        started_at=1.0,
    )


def both(case_id: str, *outcomes: Outcome) -> list[Attempt]:
    return [attempt(case_id, o, number=i + 1) for i, o in enumerate(outcomes)]


def test_a_comparison_says_how_each_case_moved() -> None:
    other = case(prompt="edited")
    earlier = evaluation(
        "one",
        "v1",
        better=case(),
        worse=case(),
        steady=case(),
        edited=case(),
        gone=case(),
        broken=case(),
    )
    later = evaluation(
        "two",
        "v2",
        better=case(),
        worse=case(),
        steady=case(),
        edited=other,
        fresh=case(),
        broken=case(),
    )
    comparison = compare(
        earlier,
        both("better", "pass", "fail")
        + both("worse", "pass", "pass")
        + both("steady", "pass", "fail")
        + both("edited", "pass", "pass")
        + both("gone", "pass", "pass")
        + both("broken", "error", "error"),
        later,
        both("better", "pass", "pass")
        + both("worse", "pass", "fail")
        + both("steady", "fail", "pass")
        + both("edited", "fail", "fail")
        + both("fresh", "pass", "pass")
        + both("broken", "pass", "pass"),
    )
    assert {row.case_id: row.change for row in comparison.rows} == {
        "better": "up",
        "worse": "down",
        "steady": "same",
        "edited": "changed",
        "gone": "removed",
        "fresh": "new",
        "broken": "no_rate",
    }
    assert comparison.earlier.config_version == "v1"
    assert comparison.later.config_version == "v2"
    edited = next(r for r in comparison.rows if r.case_id == "edited")
    assert (edited.earlier_rate, edited.later_rate) == (1.0, 0.0)  # shown, not compared
