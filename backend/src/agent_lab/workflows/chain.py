"""Prompt chaining: outline -> gate (code) -> draft -> polish, each step feeding the next."""

import re
from itertools import pairwise

from pydantic import BaseModel

from agent_lab.agents import steps
from agent_lab.agents.steps import Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "chain"
NAME = "Prompt chaining"
DESCRIPTION = "Outline, check, draft and polish a product blurb; a code gate can stop the chain."
SAMPLE_PROMPT = "A reusable water bottle that tracks how much you drink"

MIN_BULLETS = 3
_BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")


class Config(BaseModel):
    model: str
    reasoning: bool = False
    outline_prompt: str = (
        "Write an outline for a short product blurb about the user's product: 3 to 5 bullet "
        "points, one per line, each starting with '- '. Output only the bullets."
    )
    draft_prompt: str = "Write a product blurb of at most 80 words that follows the outline."
    polish_prompt: str = (
        "Polish the blurb: fix grammar and tighten the wording, keep it under 80 words. "
        "Output only the blurb."
    )


class GateResult(BaseModel):
    passed: bool
    reason: str


def check_outline(outline: str) -> GateResult:
    bullets = sum(1 for line in outline.splitlines() if _BULLET.match(line))
    if bullets >= MIN_BULLETS:
        return GateResult(passed=True, reason=f"{bullets} bullet lines")
    return GateResult(
        passed=False, reason=f"outline has {bullets} bullet lines, needs at least {MIN_BULLETS}"
    )


def build_graph() -> Graph:
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=0),
        Node(id="outline", label="outline (LLM)", kind="llm", x=200, y=0),
        Node(id="gate", label="gate (code)", kind="code", x=400, y=0),
        Node(id="draft", label="draft (LLM)", kind="llm", x=600, y=0),
        Node(id="polish", label="polish (LLM)", kind="llm", x=800, y=0),
        Node(id="end", label="end", kind="end", x=1000, y=110),
    ]
    path = ["start", "outline", "gate", "draft", "polish", "end"]
    edges = [Edge(source=a, target=b) for a, b in pairwise(path)]
    edges.append(Edge(source="gate", target="end"))  # gate failed
    return Graph(nodes=nodes, edges=edges)


class ChainWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, AGENT_ID, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        ctx, c = self.ctx, self.config
        reply = await steps.chat(
            ctx, "outline", steps.messages(c.outline_prompt, prompt), came_from=["start"]
        )
        outline = reply.content or ""
        async with ctx.tracer.span(
            SpanKind.STEP,
            "gate",
            node_id="gate",
            input=outline,
            attributes=steps.came_from(["outline"]),
        ) as span:
            gate = check_outline(outline)
            span.output = gate.model_dump()
            if not gate.passed:
                span.error = gate.reason
        if not gate.passed:
            return Outcome("error", None, ["gate"], f"gate failed: {gate.reason}")
        user = f"Product: {prompt}\n\nOutline:\n{outline}"
        draft = await steps.chat(
            ctx, "draft", steps.messages(c.draft_prompt, user), came_from=["gate"]
        )
        polished = await steps.chat(
            ctx, "polish", steps.messages(c.polish_prompt, draft.content or ""), came_from=["draft"]
        )
        return Outcome("completed", polished.content or "", ["polish"])
