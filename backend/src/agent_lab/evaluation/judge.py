"""A judge check: a model asked a yes-or-no question about an answer, as its own traced run.

Its own run, not a span of the attempt's: the agent's graph has no node for it, and it must not
count against the agent's budget or the attempt's averages (FR-005; research §10).
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from agent_lab.agents import steps
from agent_lab.agents.config_fields import LOCAL, Provider
from agent_lab.agents.registry import AgentSpec
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.bus import Bus
from agent_lab.evaluation.checks import expected
from agent_lab.evaluation.model import CheckResult, Judge
from agent_lab.graph import Edge, Graph, Node
from agent_lab.harness.budget import Harness
from agent_lab.harness.guard import RunGuard
from agent_lab.llm.base import LLMClient
from agent_lab.llm.models import ModelRef, Models, UnavailableModel
from agent_lab.mcp.host import HostTool
from agent_lab.runs import build_run, execute_run
from agent_lab.store import Store
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "judge"
GRAPH = Graph(
    nodes=[
        Node(id="start", label="start", kind="start", x=0, y=0),
        Node(id="judge", label="judge (LLM)", kind="llm", x=240, y=0),
        Node(id="end", label="end", kind="end", x=480, y=0),
    ],
    edges=[Edge(source="start", target="judge"), Edge(source="judge", target="end")],
)


class JudgeConfig(BaseModel):
    model: str
    provider: Provider = LOCAL
    question: str


class Answer(BaseModel):
    answer: Literal["yes", "no"]


class JudgeAgent:
    def __init__(self, llm: LLMClient, config: JudgeConfig, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=False)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        system = (
            "You judge an answer. Read the answer the user gives you and answer yes or no to this "
            f"question about it: {self.config.question}"
        )
        try:
            decision = await steps.decide(
                self.ctx,
                "judge",
                "judge_answer",
                steps.messages(system, prompt),
                Answer,
                came_from=["start"],
            )
        except DecisionError as exc:
            return Outcome("error", None, ["judge"], str(exc))
        return Outcome("completed", decision.answer, ["judge"])


def _create(
    llm: LLMClient, config: JudgeConfig, tracer: Tracer, _tools: Mapping[str, HostTool]
) -> JudgeAgent:
    return JudgeAgent(llm, config, tracer)


# Not a template: it is not listed, and no one can pick it (registry.AGENTS).
JUDGE = AgentSpec(
    id=AGENT_ID,
    name="Judge",
    description="Answers a yes-or-no question about an answer.",
    sample_prompt="",
    config_model=JudgeConfig,
    graph=lambda _config: GRAPH,
    create=_create,
)


async def run_judge(
    check: Judge,
    answer: str,
    *,
    model: ModelRef,
    eval_id: str,
    store: Store,
    models: Models,
    bus: Bus,
    secrets: tuple[str, ...] = (),
) -> CheckResult:
    """Pass on yes, fail on no; a failed call or any other answer is an error, never a pass."""

    def result(outcome: Literal["pass", "fail", "error"], reason: str | None, run_id: str | None):
        return CheckResult(
            kind=check.kind,
            expected=expected(check),
            result=outcome,
            reason=reason,
            judge_run_id=run_id,
        )

    if not answer.strip():
        return result("fail", "the run gave no answer to judge", None)
    chosen = check.model or model
    try:
        llm = models.client(chosen)
    except UnavailableModel as exc:
        return result("error", str(exc), None)
    config = JudgeConfig(model=chosen.model, provider=chosen.provider, question=check.question)
    run = build_run(answer, AGENT_ID, JUDGE, config, JUDGE.name, secrets, eval_id=eval_id)
    store.create_run(run)
    await execute_run(
        run=run,
        prompt=answer,
        config=config,
        spec=JUDGE,
        llm=llm,
        store=store,
        bus=bus,
        secrets=secrets,
        guard=RunGuard(Harness()),  # retries on, no budget
    )
    done = store.get_run(run.run_id)
    assert done is not None
    if done.status == "completed" and done.answer == "yes":
        return result("pass", None, run.run_id)
    if done.status == "completed" and done.answer == "no":
        return result("fail", "the judge answered no", run.run_id)
    errors = (s.error for s in store.get_spans(run.run_id) if s.error)
    return result("error", next(errors, "the judge's call failed"), run.run_id)
