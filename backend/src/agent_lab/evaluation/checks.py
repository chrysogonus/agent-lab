"""Checks that can be read off a finished run. The judge needs a model: `evaluation/judge.py`."""

import re
from collections.abc import Sequence

from agent_lab.evaluation.model import (
    CheckResult,
    Contains,
    EndState,
    Judge,
    LocalCheck,
    Matches,
    MaxModelCalls,
    MaxTokens,
    NotContains,
    Result,
    ToolCalled,
)
from agent_lab.store import Run
from agent_lab.tracing.span import Span, SpanKind


def expected(check: LocalCheck | Judge) -> str:
    match check:
        case Contains(text=text):
            return f"contains {text!r}"
        case NotContains(text=text):
            return f"does not contain {text!r}"
        case Matches(pattern=pattern):
            return f"matches {pattern!r}"
        case ToolCalled(tool=tool):
            return f"calls {tool}"
        case EndState(state=state):
            return f"ends {state}"
        case MaxModelCalls(limit=limit):
            return f"at most {limit:,} model calls"
        case MaxTokens(limit=limit):
            return f"at most {limit:,} tokens"
        case Judge(question=question):
            return f"the judge says yes to {question!r}"
        case _:  # ToolNotCalled, the one left
            return f"does not call {check.tool}"


def _quoted(answer: str) -> str:
    return repr(answer[:200])


def _verdict(check: LocalCheck, run: Run, spans: Sequence[Span]) -> tuple[Result, str | None]:
    answer = run.answer or ""
    totals = run.totals
    match check:
        case Contains(text=text):
            passed = text in answer
            return _either(passed, f"the answer does not contain {text!r}: {_quoted(answer)}")
        case NotContains(text=text):
            return _either(text not in answer, f"the answer contains {text!r}")
        case Matches(pattern=pattern):
            found = re.search(pattern, answer) is not None
            return _either(found, f"the answer does not match {pattern!r}: {_quoted(answer)}")
        case ToolCalled(tool=tool):
            return _either(tool in _tools(spans), f"{tool} was not called")
        case EndState(state=state):
            return _either(run.status == state, f"the run ended {run.status}")
        case MaxModelCalls(limit=limit):
            used = totals.llm_calls if totals else 0
            return _either(used <= limit, f"{used:,} model calls")
        case MaxTokens(limit=limit):
            if any(s.kind == SpanKind.LLM and s.tokens_in is None for s in spans):
                return "error", "the provider reported no tokens"
            used = totals.tokens_in + totals.tokens_out if totals else 0
            return _either(used <= limit, f"{used:,} tokens")
        case _:  # ToolNotCalled, the one left
            return _either(check.tool not in _tools(spans), f"{check.tool} was called")


def _either(passed: bool, reason: str) -> tuple[Result, str | None]:
    return ("pass", None) if passed else ("fail", reason)


def _tools(spans: Sequence[Span]) -> set[str]:
    """A tool span means the tool was called: a denied call has only its approval span."""
    return {str(s.attributes.get("gen_ai.tool.name")) for s in spans if s.kind == SpanKind.TOOL}


def run_check(check: LocalCheck, run: Run, spans: Sequence[Span]) -> CheckResult:
    result, reason = _verdict(check, run, spans)
    return CheckResult(kind=check.kind, expected=expected(check), result=result, reason=reason)
