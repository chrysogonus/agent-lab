"""Budgets: what one may hold, and what a run does when it reaches one (M17, FR-010, FR-011)."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_lab.harness.budget import DEFAULT_BUDGET, MAX_BUDGET, Budget, OverBudget

FOUR = {"model_calls": 1, "tokens": 1, "tool_calls": 1, "seconds": 1}


@pytest.mark.parametrize(
    "bad",
    [
        {**FOUR, "model_calls": 0},
        {**FOUR, "model_calls": 201},
        {**FOUR, "tokens": 2_000_001},
        {**FOUR, "tool_calls": 201},
        {**FOUR, "seconds": 3_601},
        {**FOUR, "extra": 1},
        {"model_calls": 1, "tokens": 1, "tool_calls": 1},
    ],
)
def test_a_budget_outside_the_limits_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Budget.model_validate(bad)


def test_the_most_a_budget_may_be_is_allowed() -> None:
    biggest = {"model_calls": 200, "tokens": 2_000_000, "tool_calls": 200, "seconds": 3_600}
    assert Budget.model_validate(biggest) == MAX_BUDGET


def test_the_default_budget_is_within_the_limits() -> None:
    assert Budget.model_validate(DEFAULT_BUDGET.model_dump()) == DEFAULT_BUDGET
    assert DEFAULT_BUDGET.model_calls == 30
    assert DEFAULT_BUDGET.tokens == 200_000


@pytest.mark.parametrize(
    ("what", "used", "limit", "reason"),
    [
        ("model calls", 3, 3, "model calls: 3 of 3"),
        ("tokens", 205_120, 200_000, "tokens: 205,120 of 200,000"),
        ("tool calls", 30, 30, "tool calls: 30 of 30"),
    ],
)
def test_the_reason_says_which_limit_and_how_much(
    what: str, used: int, limit: int, reason: str
) -> None:
    assert OverBudget.of(what, used, limit).reason == reason
