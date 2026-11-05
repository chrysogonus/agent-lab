"""An attempt's outcome, pass rates and comparisons: pure functions of stored results."""

import hashlib
import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from agent_lab.evaluation.model import (
    Attempt,
    CaseFields,
    CheckResult,
    Evaluation,
    FrozenCase,
    Outcome,
)
from agent_lab.llm.models import ModelRef
from agent_lab.store import Run

Change = Literal["new", "removed", "changed", "up", "down", "same", "no_rate"]


def attempt_outcome(run: Run | None, checks: Sequence[CheckResult]) -> tuple[Outcome, str | None]:
    """FR-004, in its order; the reason is for a fail or an error."""
    if run is None:
        return "error", "the run never started"
    if run.status == "error":
        return "error", "the run ended with an error"
    if run.status == "stopped":
        return "error", "the run was stopped"
    expected_end = any(c.kind == "end_state" and c.result == "pass" for c in checks)
    if run.status != "completed" and not expected_end:
        reason = f"the run ended {run.status}"
        return "fail", f"{reason}: {run.stop_reason}" if run.stop_reason else reason
    for wanted in ("fail", "error"):
        for check in checks:
            if check.result == wanted:
                return wanted, check.reason
    return "pass", None


class Rates(BaseModel):
    passed: int = 0
    failed: int = 0
    errors: int = 0
    pass_rate: float | None = None  # None when every attempt is an error (FR-004a)
    avg_llm_calls: float | None = None
    avg_tokens: float | None = None
    avg_wall_ms: float | None = None


class Summary(BaseModel):
    cases: dict[str, Rates]
    overall: Rates


def _average(values: Sequence[int | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _rates(attempts: Sequence[Attempt]) -> Rates:
    passed = sum(a.outcome == "pass" for a in attempts)
    failed = sum(a.outcome == "fail" for a in attempts)
    ran = [a for a in attempts if a.run_id is not None]
    return Rates(
        passed=passed,
        failed=failed,
        errors=sum(a.outcome == "error" for a in attempts),
        pass_rate=passed / (passed + failed) if passed + failed else None,
        avg_llm_calls=_average([a.llm_calls for a in ran]),
        avg_tokens=_average([a.tokens for a in ran]),
        avg_wall_ms=_average([a.wall_ms for a in ran]),
    )


def summarize(attempts: Sequence[Attempt]) -> Summary:
    """The overall rate pools the attempts; it is not an average of the cases' rates."""
    ids = list(dict.fromkeys(a.case_id for a in attempts))
    cases = {i: _rates([a for a in attempts if a.case_id == i]) for i in ids}
    return Summary(cases=cases, overall=_rates(attempts))


def fingerprint(case: CaseFields) -> str:
    """What the case does: renaming it changes nothing a comparison cares about."""
    body = case.model_dump(mode="json", include={"prompt", "checks", "approvals"})
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]


def frozen_case(case_id: str, case: CaseFields) -> FrozenCase:
    fields = case.model_dump(include=set(CaseFields.model_fields))
    return FrozenCase(case_id=case_id, fingerprint=fingerprint(case), **fields)


class ComparisonRow(BaseModel):
    case_id: str
    name: str
    change: Change
    earlier_rate: float | None
    later_rate: float | None


class ComparisonSide(BaseModel):
    eval_id: str
    config_version: str
    model: ModelRef
    harness: dict[str, object]
    started_at: float
    overall: Rates


class Comparison(BaseModel):
    earlier: ComparisonSide
    later: ComparisonSide
    rows: list[ComparisonRow]


def _side(evaluation: Evaluation, overall: Rates) -> ComparisonSide:
    return ComparisonSide(
        eval_id=evaluation.eval_id,
        config_version=evaluation.config_version,
        model=evaluation.model,
        harness=evaluation.harness,
        started_at=evaluation.started_at,
        overall=overall,
    )


def _change(earlier: FrozenCase, later: FrozenCase, was: float | None, now: float | None) -> Change:
    if earlier.fingerprint != later.fingerprint:
        return "changed"
    if was is None or now is None:
        return "no_rate"
    return "up" if now > was else "down" if now < was else "same"


def compare(
    earlier: Evaluation,
    earlier_attempts: Sequence[Attempt],
    later: Evaluation,
    later_attempts: Sequence[Attempt],
) -> Comparison:
    before, after = summarize(earlier_attempts), summarize(later_attempts)
    old = {c.case_id: c for c in earlier.cases}
    new = {c.case_id: c for c in later.cases}

    def rate(summary: Summary, case_id: str) -> float | None:
        rates = summary.cases.get(case_id)
        return rates.pass_rate if rates else None

    rows: list[ComparisonRow] = []
    for case_id, case in new.items():
        was, now = rate(before, case_id), rate(after, case_id)
        change = _change(old[case_id], case, was, now) if case_id in old else "new"
        rows.append(
            ComparisonRow(
                case_id=case_id, name=case.name, change=change, earlier_rate=was, later_rate=now
            )
        )
    for case_id, case in old.items():
        if case_id not in new:
            rows.append(
                ComparisonRow(
                    case_id=case_id,
                    name=case.name,
                    change="removed",
                    earlier_rate=rate(before, case_id),
                    later_rate=None,
                )
            )
    return Comparison(
        earlier=_side(earlier, before.overall), later=_side(later, after.overall), rows=rows
    )
