"""An evaluation: an agent's cases, each run several times as ordinary runs, one after another.

Attempts use the copy taken at the start, never the stored agent (FR-003a). One at a time, in one
task: this helps keep a hosted model within its rate limits and the results easy to read.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from agent_lab.agents.registry import AgentSpec, config_tools, model_of
from agent_lab.agents.steps import config_version
from agent_lab.bus import Bus
from agent_lab.evaluation.checks import expected, run_check
from agent_lab.evaluation.examples import EXAMPLES
from agent_lab.evaluation.judge import run_judge
from agent_lab.evaluation.model import (
    Attempt,
    Case,
    Check,
    CheckResult,
    Evaluation,
    EvaluationState,
    FrozenCase,
    Judge,
)
from agent_lab.evaluation.results import attempt_outcome, frozen_case
from agent_lab.harness.approvals import CaseDecider
from agent_lab.harness.budget import DEFAULT_BUDGET, Harness
from agent_lab.harness.guard import RunGuard
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.base import LLMClient
from agent_lab.llm.models import ModelRef, Models
from agent_lab.mcp.host import Host, ToolsUnavailable
from agent_lab.runs import build_run, execute_run, resolve
from agent_lab.store import Run, Store
from agent_lab.tracing.redact import redact
from agent_lab.tracing.span import Span

log = logging.getLogger(__name__)


class EvaluationConflict(Exception):
    """Only one evaluation runs at a time."""


class NothingToEvaluate(Exception):
    """No cases, or a case that does not exist."""


@dataclass(frozen=True)
class _Copy:
    """What every attempt runs: taken once, when the evaluation starts."""

    evaluation: Evaluation
    spec: AgentSpec
    config: BaseModel
    llm: LLMClient
    harness: Harness


class Evaluations:
    def __init__(
        self,
        *,
        store: Store,
        models: Models,
        host: Host,
        bus: Bus,
        secrets: tuple[str, ...],
        live: LiveRuns,
    ) -> None:
        self.store, self.models, self.host, self.bus = store, models, host, bus
        self.secrets, self.live = secrets, live
        self._running: Evaluation | None = None
        self._run_id: str | None = None  # the attempt under way
        self._stopping = False
        self._task: asyncio.Task[None] | None = None  # a strong ref, so it is not collected

    def cases_of(self, agent_id: str) -> list[Case]:
        """A template's examples first, then the owner's cases by name."""
        return [*EXAMPLES.get(agent_id, []), *self.store.list_cases(agent_id)]

    def running_for(self, agent_id: str) -> bool:
        return self._running is not None and self._running.agent_id == agent_id

    async def start(
        self,
        agent_id: str,
        *,
        repeats: int,
        case_ids: list[str] | None = None,
        model: ModelRef | None = None,
    ) -> Evaluation:
        """Raises `EvaluationConflict`, `NothingToEvaluate`, `UnknownAgent`, `UnavailableModel`."""
        if self._running is not None:
            raise EvaluationConflict("an evaluation is already running")
        spec, config, name, llm = resolve(agent_id, self.store, self.models, model)
        cases = self._chosen(agent_id, case_ids)
        agent = self.store.get_agent(agent_id)
        harness = Harness.model_validate(agent.harness if agent and agent.harness else {})
        default_budget = harness.budget is None
        harness = harness.model_copy(update={"budget": harness.budget or DEFAULT_BUDGET})
        evaluation = Evaluation(
            eval_id=f"eval-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            agent_name=name,
            config_version=config_version(config),
            config=redact(config.model_dump(), self._secrets()),
            harness={**harness.model_dump(), "default_budget": default_budget},
            model=model_of(config),
            repeats=repeats,
            cases=cases,
            state="running",
            started_at=time.time(),
        )
        self.store.create_evaluation(evaluation)
        self._running, self._stopping = evaluation, False
        copy = _Copy(evaluation, spec, config, llm, harness)
        self._task = asyncio.create_task(self._run(copy))
        return evaluation

    def stop(self, eval_id: str) -> bool:
        """No further attempt starts, and the running one is stopped; False when not running."""
        if self._running is None or self._running.eval_id != eval_id:
            return False
        self._stopping = True
        if self._run_id:
            self.live.stop(self._run_id)
        return True

    def _chosen(self, agent_id: str, case_ids: list[str] | None) -> list[FrozenCase]:
        cases = self.cases_of(agent_id)
        if case_ids is not None:
            unknown = set(case_ids) - {c.case_id for c in cases}
            if unknown:
                raise NothingToEvaluate(f"unknown cases: {', '.join(sorted(unknown))}")
            cases = [c for c in cases if c.case_id in case_ids]
        if not cases:
            raise NothingToEvaluate("no cases to run")
        return [frozen_case(c.case_id, c) for c in cases]

    def _secrets(self) -> tuple[str, ...]:
        return (*self.secrets, *self.host.secrets())

    async def _run(self, copy: _Copy) -> None:
        evaluation = copy.evaluation
        state: EvaluationState = "finished"
        try:
            for case in evaluation.cases:
                for number in range(1, evaluation.repeats + 1):
                    if not self._stopping:
                        await self._attempt(copy, case, number)
            if self._stopping:
                state = "stopped"
        except Exception:
            log.exception("evaluation %s failed", evaluation.eval_id)
            state = "interrupted"
        self.store.finish_evaluation(evaluation.eval_id, state, time.time())
        self._running, self._run_id = None, None

    async def _attempt(self, copy: _Copy, case: FrozenCase, number: int) -> None:
        evaluation = copy.evaluation
        await self.host.start()
        secrets = self._secrets()
        try:
            tools = self.host.resolve(config_tools(copy.config))
        except ToolsUnavailable as exc:
            reason = str(exc)
            checks = [_not_run(c, reason) for c in case.checks]
            self.store.add_attempt(
                Attempt(
                    eval_id=evaluation.eval_id,
                    case_id=case.case_id,
                    number=number,
                    outcome="error",
                    reason=redact(reason, secrets),
                    checks=checks,
                )
            )
            return
        run = build_run(
            case.prompt,
            evaluation.agent_id,
            copy.spec,
            copy.config,
            evaluation.agent_name,
            secrets,
            eval_id=evaluation.eval_id,
        )
        run.harness = evaluation.harness
        self.store.create_run(run)
        guard = RunGuard(copy.harness, decider=CaseDecider(case.approvals))
        task = asyncio.create_task(
            execute_run(
                run=run,
                prompt=case.prompt,
                config=copy.config,
                spec=copy.spec,
                llm=copy.llm,
                store=self.store,
                bus=self.bus,
                secrets=secrets,
                tools=tools,
                guard=guard,
            )
        )
        self._run_id = run.run_id
        self.live.add(run.run_id, task, guard)
        if self._stopping:  # asked for while this attempt was being set up
            self.live.stop(run.run_id)
        try:
            await task
        finally:
            self.live.remove(run.run_id)
            self._run_id = None
        done = self.store.get_run(run.run_id)
        assert done is not None
        spans = self.store.get_spans(run.run_id)
        results = [await self._check(check, done, spans, evaluation) for check in case.checks]
        outcome, reason = attempt_outcome(done, results)
        if (
            outcome == "fail"
            and done.status == "over_budget"
            and evaluation.harness["default_budget"]
        ):
            reason = f"{reason} (the default budget)"  # the agent itself has none: say whose it was
        totals = done.totals
        self.store.add_attempt(
            Attempt(
                eval_id=evaluation.eval_id,
                case_id=case.case_id,
                number=number,
                run_id=run.run_id,
                outcome=outcome,
                reason=redact(reason, secrets),
                checks=[_redacted(r, secrets) for r in results],
                llm_calls=totals.llm_calls if totals else None,
                tool_calls=totals.tool_calls if totals else None,
                tokens=totals.tokens_in + totals.tokens_out if totals else None,
                wall_ms=totals.wall_ms if totals else None,
            )
        )

    async def _check(
        self, check: Check, run: Run, spans: list[Span], evaluation: Evaluation
    ) -> CheckResult:
        if not isinstance(check, Judge):
            return run_check(check, run, spans)
        if run.status in ("error", "stopped"):  # the outcome is settled: spend nothing more
            return _not_run(check, "not judged: the run did not finish")
        return await run_judge(
            check,
            run.answer or "",
            model=evaluation.model,
            eval_id=evaluation.eval_id,
            store=self.store,
            models=self.models,
            bus=self.bus,
            secrets=self._secrets(),
        )


def _not_run(check: Check, reason: str) -> CheckResult:
    return CheckResult(kind=check.kind, expected=expected(check), result="error", reason=reason)


def _redacted(result: CheckResult, secrets: tuple[str, ...]) -> CheckResult:
    update: dict[str, Any] = {"reason": redact(result.reason, secrets)}
    return result.model_copy(update=update)
