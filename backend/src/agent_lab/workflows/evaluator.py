"""Evaluator-optimizer: a generator drafts, an evaluator approves or gives feedback, repeat."""

from itertools import pairwise
from typing import Self

from pydantic import BaseModel, Field, model_validator

from agent_lab.agents import steps
from agent_lab.agents.config_fields import LOCAL, Prompt, Provider
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "evaluator"
NAME = "Evaluator-optimizer"
DESCRIPTION = "Write a slogan; an evaluator approves it or sends feedback, for up to 3 rounds."
SAMPLE_PROMPT = "A solar-powered phone charger called SunSip"


class Config(BaseModel):
    model: str
    provider: Provider = LOCAL
    reasoning: bool = False
    max_rounds: int = Field(default=3, ge=1, le=5)
    generator_prompt: Prompt = (
        "Write one slogan of fewer than 12 words for the product. It must mention the product "
        "name. Output only the slogan."
    )
    evaluator_prompt: Prompt = (
        "Check the slogan: fewer than 12 words, mentions the product name, catchy. Approve only "
        "if all hold; otherwise give one sentence of concrete feedback."
    )


class Verdict(BaseModel):
    approved: bool
    feedback: str

    @model_validator(mode="after")
    def feedback_when_rejected(self) -> Self:
        if not self.approved and not self.feedback.strip():
            raise ValueError("feedback must not be empty when not approved")
        return self


def build_graph() -> Graph:
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=0),
        Node(id="generator", label="generator (LLM)", kind="llm", x=220, y=0),
        Node(id="evaluator", label="evaluator (LLM)", kind="llm", x=440, y=0),
        Node(id="end", label="end", kind="end", x=660, y=0),
    ]
    path = ["start", "generator", "evaluator", "end"]
    edges = [Edge(source=a, target=b) for a, b in pairwise(path)]
    edges.append(Edge(source="evaluator", target="generator"))  # revise with feedback
    return Graph(nodes=nodes, edges=edges)


class EvaluatorWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        c = self.config
        draft, feedback, came = "", "", ["start"]
        for round_ in range(1, c.max_rounds + 1):
            user = prompt
            if feedback:
                user += f"\n\nPrevious slogan: {draft}\nFeedback: {feedback}\nWrite a better one."
            reply = await steps.chat(
                self.ctx,
                "generator",
                steps.messages(c.generator_prompt, user),
                came_from=came,
                attributes={"lab.round": round_},
            )
            draft = (reply.content or "").strip()
            try:
                verdict = await steps.decide(
                    self.ctx,
                    "evaluator",
                    "verdict",
                    steps.messages(c.evaluator_prompt, f"Product: {prompt}\nSlogan: {draft}"),
                    Verdict,
                    came_from=["generator"],
                    attributes={"lab.round": round_},
                )
            except DecisionError as exc:
                # An unreadable verdict counts as a rejection; its error becomes the feedback.
                verdict = Verdict(approved=False, feedback=str(exc))
            if verdict.approved:
                return Outcome("completed", draft, ["evaluator"])
            feedback, came = verdict.feedback, ["evaluator"]
        return Outcome(
            "max_iterations", draft, ["evaluator"], f"not approved after {c.max_rounds} rounds"
        )
