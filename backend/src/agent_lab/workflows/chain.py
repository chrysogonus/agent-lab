"""Prompt chaining: a list of model steps, each feeding the next; a code gate can stop the chain."""

import re
from itertools import pairwise
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from agent_lab.agents import steps
from agent_lab.agents.config_fields import LOCAL, ItemName, Prompt, Provider, unique
from agent_lab.agents.steps import Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "chain"
NAME = "Prompt chaining"
DESCRIPTION = "Outline, check, draft and polish a product blurb; a code gate can stop the chain."
SAMPLE_PROMPT = "A reusable water bottle that tracks how much you drink"

_BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")


class ChainStep(BaseModel):
    name: ItemName
    prompt: Prompt
    # Later steps get the previous output; this adds the user's input (ignored for the first).
    include_input: bool = False


class Config(BaseModel):
    model: str
    provider: Provider = LOCAL
    reasoning: bool = False
    steps: list[ChainStep] = Field(
        default=[
            ChainStep(
                name="outline",
                prompt="Write an outline for a short product blurb about the user's product: 3 to "
                "5 bullet points, one per line, each starting with '- '. Output only the bullets.",
            ),
            ChainStep(
                name="draft",
                prompt="Write a product blurb of at most 80 words that follows the outline.",
                include_input=True,
            ),
            ChainStep(
                name="polish",
                prompt="Polish the blurb: fix grammar and tighten the wording, keep it under 80 "
                "words. Output only the blurb.",
            ),
        ],
        min_length=1,
        max_length=6,
    )
    input_label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ] = "Product"
    gate: bool = True
    gate_min_bullets: int = Field(default=3, ge=1, le=10)

    @field_validator("steps")
    @classmethod
    def unique_names(cls, value: list[ChainStep]) -> list[ChainStep]:
        unique((s.name for s in value), "step")
        return value


class GateResult(BaseModel):
    passed: bool
    reason: str


def check_outline(outline: str, min_bullets: int) -> GateResult:
    bullets = sum(1 for line in outline.splitlines() if _BULLET.match(line))
    if bullets >= min_bullets:
        return GateResult(passed=True, reason=f"{bullets} bullet lines")
    return GateResult(
        passed=False, reason=f"outline has {bullets} bullet lines, needs at least {min_bullets}"
    )


def _path(config: Config) -> list[str]:
    names = [s.name for s in config.steps]
    if config.gate:
        names.insert(1, "gate")
    return ["start", *names]


def build_graph(config: Config) -> Graph:
    path = _path(config)
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=0),
        *(
            Node(id="gate", label="gate (code)", kind="code", x=200 * i, y=0)
            if node == "gate"
            else Node(id=node, label=f"{node} (LLM)", kind="llm", x=200 * i, y=0)
            for i, node in enumerate(path[1:], start=1)
        ),
        Node(id="end", label="end", kind="end", x=200 * len(path), y=110),
    ]
    edges = [Edge(source=a, target=b) for a, b in pairwise([*path, "end"])]
    if config.gate and len(config.steps) > 1:
        edges.append(Edge(source="gate", target="end"))  # gate failed
    return Graph(nodes=nodes, edges=edges)


class ChainWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _gate(self, outline: str, came_from: str) -> GateResult:
        async with self.ctx.tracer.span(
            SpanKind.STEP,
            "gate",
            node_id="gate",
            input=outline,
            attributes=steps.came_from([came_from]),
        ) as span:
            gate = check_outline(outline, self.config.gate_min_bullets)
            span.output = gate.model_dump()
            if not gate.passed:
                span.error = gate.reason
        return gate

    async def _flow(self, prompt: str) -> Outcome:
        ctx, c = self.ctx, self.config
        first, *rest = c.steps
        reply = await steps.chat(
            ctx, first.name, steps.messages(first.prompt, prompt), came_from=["start"]
        )
        previous, output = first.name, reply.content or ""
        if c.gate:
            gate = await self._gate(output, first.name)
            if not gate.passed:
                return Outcome("error", None, ["gate"], f"gate failed: {gate.reason}")
            previous = "gate"
        prev_name = first.name
        for step in rest:
            user = output
            if step.include_input:
                user = f"{c.input_label}: {prompt}\n\n{prev_name.capitalize()}:\n{output}"
            reply = await steps.chat(
                ctx, step.name, steps.messages(step.prompt, user), came_from=[previous]
            )
            previous = prev_name = step.name
            output = reply.content or ""
        # With the gate after the only step, the chain ends at the gate.
        return Outcome("completed", output, [previous])
