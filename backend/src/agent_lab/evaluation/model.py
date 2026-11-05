"""Test cases, their checks, evaluations and attempts, as stored and as the API shows them."""

import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from agent_lab.agents.config_fields import known_tool
from agent_lab.llm.models import ModelRef

Result = Literal["pass", "fail", "error"]
Outcome = Result
EvaluationState = Literal["running", "finished", "stopped", "interrupted"]
FinishedStatus = Literal["completed", "max_iterations", "over_budget", "stopped", "error"]

Text = Annotated[str, StringConstraints(min_length=1, max_length=500)]
ToolName = Annotated[str, AfterValidator(known_tool)]


def _compiles(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid pattern: {exc}") from exc
    return pattern


class _Check(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contains(_Check):
    kind: Literal["contains"]
    text: Text


class NotContains(_Check):
    kind: Literal["not_contains"]
    text: Text


class Matches(_Check):
    kind: Literal["matches"]
    pattern: Annotated[Text, AfterValidator(_compiles)]


class ToolCalled(_Check):
    kind: Literal["tool_called"]
    tool: ToolName


class ToolNotCalled(_Check):
    kind: Literal["tool_not_called"]
    tool: ToolName


class EndState(_Check):
    kind: Literal["end_state"]
    state: FinishedStatus


class MaxModelCalls(_Check):
    kind: Literal["max_model_calls"]
    limit: int = Field(ge=1)


class MaxTokens(_Check):
    kind: Literal["max_tokens"]
    limit: int = Field(ge=1)


class Judge(_Check):
    kind: Literal["judge"]
    question: Text
    model: ModelRef | None = None  # None: the evaluation's model (FR-005)


LocalCheck = (
    Contains
    | NotContains
    | Matches
    | ToolCalled
    | ToolNotCalled
    | EndState
    | MaxModelCalls
    | MaxTokens
)
Check = Annotated[LocalCheck | Judge, Field(discriminator="kind")]


class CaseFields(BaseModel):
    """What the owner writes."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    checks: list[Check] = Field(min_length=1, max_length=10)
    approvals: Literal["approve", "deny"] = "deny"


class Case(CaseFields):
    case_id: str
    agent_id: str
    read_only: bool = False  # a template's example


class FrozenCase(CaseFields):
    """A case as an evaluation took it at its start (FR-003a)."""

    case_id: str
    fingerprint: str


class CheckResult(BaseModel):
    kind: str
    expected: str
    result: Result
    reason: str | None = None
    judge_run_id: str | None = None


class Attempt(BaseModel):
    eval_id: str
    case_id: str
    number: int
    run_id: str | None = None  # None: the run was refused before it started
    outcome: Outcome
    reason: str | None = None
    checks: list[CheckResult] = []
    llm_calls: int | None = None
    tool_calls: int | None = None
    tokens: int | None = None
    wall_ms: int | None = None


class Evaluation(BaseModel):
    eval_id: str
    agent_id: str
    agent_name: str
    config_version: str
    config: dict[str, Any]  # redacted: for the record, attempts use the copy in memory
    harness: dict[str, Any]  # {budget, ask_first, default_budget}
    model: ModelRef
    repeats: int
    cases: list[FrozenCase]
    state: EvaluationState
    started_at: float
    ended_at: float | None = None
