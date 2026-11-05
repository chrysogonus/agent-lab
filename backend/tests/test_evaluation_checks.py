"""Test cases and their checks: what may be saved, and what each check sees (FR-001, FR-002)."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_lab.agents.react import build_graph
from agent_lab.evaluation.checks import run_check
from agent_lab.evaluation.model import CaseFields, LocalCheck
from agent_lab.store import Run, RunStatus, RunTotals
from agent_lab.tracing.span import Span, SpanKind


def case(**changes: Any) -> dict[str, Any]:
    fields = {
        "name": "Multiplies",
        "prompt": "17*23?",
        "checks": [{"kind": "contains", "text": "1"}],
    }
    return {**fields, **changes}


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"name": "x" * 81},
        {"prompt": ""},
        {"prompt": "x" * 4001},
        {"checks": []},
        {"checks": [{"kind": "contains", "text": "1"}] * 11},
        {"approvals": "maybe"},
        {"surprise": 1},
        {"checks": [{"kind": "matches", "pattern": "("}]},
        {"checks": [{"kind": "matches", "pattern": "x" * 501}]},
        {"checks": [{"kind": "contains", "text": ""}]},
        {"checks": [{"kind": "tool_called", "tool": "not a tool"}]},
        {"checks": [{"kind": "end_state", "state": "running"}]},
        {"checks": [{"kind": "max_tokens", "limit": 0}]},
        {"checks": [{"kind": "judge", "question": ""}]},
        {"checks": [{"kind": "guess"}]},
    ],
)
def test_a_case_breaking_a_rule_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CaseFields.model_validate(case(**bad))


def test_approval_requests_are_denied_unless_a_case_says_otherwise() -> None:
    assert CaseFields.model_validate(case()).approvals == "deny"


def test_an_invalid_pattern_says_why() -> None:
    with pytest.raises(ValidationError, match="invalid pattern"):
        CaseFields.model_validate(case(checks=[{"kind": "matches", "pattern": "("}]))


def make_run(
    *,
    answer: str | None = "The answer is 391.",
    status: RunStatus = "completed",
    llm_calls: int = 2,
    tokens: tuple[int, int] = (100, 20),
) -> Run:
    return Run(
        run_id="r",
        agent_id="react",
        config_version="v",
        prompt="p",
        status=status,
        answer=answer,
        graph=build_graph([]),
        config={},
        started_at=1.0,
        totals=RunTotals(
            llm_calls=llm_calls, tool_calls=1, tokens_in=tokens[0], tokens_out=tokens[1], wall_ms=5
        ),
    )


def span(kind: SpanKind, tokens_in: int | None = 1, tool: str | None = None) -> Span:
    return Span(
        trace_id="t",
        span_id="s",
        parent_span_id=None,
        run_id="r",
        agent_id="react",
        node_id="n",
        config_version="v",
        kind=kind,
        name="n",
        started_at=1.0,
        tokens_in=tokens_in,
        attributes={"gen_ai.tool.name": tool} if tool else {},
    )


def check(**fields: Any) -> LocalCheck:
    parsed = CaseFields.model_validate(case(checks=[fields])).checks[0]
    assert parsed.kind != "judge"
    return parsed


@pytest.mark.parametrize(
    ("fields", "result"),
    [
        ({"kind": "contains", "text": "391"}, "pass"),
        ({"kind": "contains", "text": "392"}, "fail"),
        ({"kind": "not_contains", "text": "392"}, "pass"),
        ({"kind": "not_contains", "text": "391"}, "fail"),
        ({"kind": "matches", "pattern": r"\b391\b"}, "pass"),
        ({"kind": "matches", "pattern": r"^391$"}, "fail"),
        ({"kind": "end_state", "state": "completed"}, "pass"),
        ({"kind": "end_state", "state": "over_budget"}, "fail"),
        ({"kind": "max_model_calls", "limit": 2}, "pass"),
        ({"kind": "max_model_calls", "limit": 1}, "fail"),
        ({"kind": "max_tokens", "limit": 120}, "pass"),
        ({"kind": "max_tokens", "limit": 119}, "fail"),
    ],
)
def test_each_check_against_a_run(fields: dict[str, Any], result: str) -> None:
    assert run_check(check(**fields), make_run(), [span(SpanKind.LLM)]).result == result


def test_tool_checks_read_the_tools_that_really_ran() -> None:
    ran = [span(SpanKind.TOOL, tool="calculator"), span(SpanKind.LLM)]
    assert run_check(check(kind="tool_called", tool="calculator"), make_run(), ran).result == "pass"
    assert (
        run_check(check(kind="tool_called", tool="get_weather"), make_run(), ran).result == "fail"
    )
    assert (
        run_check(check(kind="tool_not_called", tool="get_weather"), make_run(), ran).result
        == "pass"
    )
    assert (
        run_check(check(kind="tool_not_called", tool="calculator"), make_run(), ran).result
        == "fail"
    )


def test_a_denied_call_has_no_tool_span_so_it_counts_as_not_called() -> None:
    denied = [span(SpanKind.STEP, tool="notes/write_note")]
    result = run_check(check(kind="tool_called", tool="notes/write_note"), make_run(), denied)
    assert result.result == "fail"


def test_a_run_without_an_answer_reads_as_empty() -> None:
    silent = make_run(answer=None)
    assert run_check(check(kind="contains", text="391"), silent, []).result == "fail"
    assert run_check(check(kind="not_contains", text="391"), silent, []).result == "pass"
    assert run_check(check(kind="matches", pattern=".+"), silent, []).result == "fail"


def test_a_failed_check_says_what_it_expected_and_what_the_run_did() -> None:
    result = run_check(check(kind="contains", text="392"), make_run(), [])
    assert result.expected == "contains '392'"
    assert result.reason == "the answer does not contain '392': 'The answer is 391.'"


def test_tokens_nobody_reported_cannot_pass_a_token_check() -> None:
    unknown = [span(SpanKind.LLM, tokens_in=None)]
    result = run_check(check(kind="max_tokens", limit=1000), make_run(), unknown)
    assert result.result == "error"
    assert result.reason == "the provider reported no tokens"
