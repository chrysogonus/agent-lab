"""Parallelization (sectioning): one review per aspect runs concurrently, then one merge call."""

import asyncio

from pydantic import BaseModel, Field

from agent_lab.agents import steps
from agent_lab.agents.config_fields import ItemName, Prompt, ShortText, fill
from agent_lab.agents.steps import Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "parallel"
NAME = "Parallelization"
DESCRIPTION = "Review a text for clarity, tone and claims at the same time, then merge the reviews."
SAMPLE_PROMPT = (
    "Our new app is the best in the world. It saves everyone 10 hours a week and its totally "
    "free forever, no catch, trust us!!!"
)


class Config(BaseModel):
    model: str
    reasoning: bool = False
    # aspect -> what its reviewer looks for; one graph node per aspect.
    aspects: dict[ItemName, ShortText] = Field(
        default={
            "clarity": "Is it easy to understand? Point out confusing sentences.",
            "tone": "Is the tone consistent and right for its audience?",
            "claims": "Which claims are unsupported, exaggerated or possibly false?",
        },
        min_length=1,
        max_length=6,
    )
    review_prompt: Prompt = (
        "You review a short text for {aspect} only. {focus} Reply with at most 3 short bullet "
        "points."
    )
    merge_prompt: Prompt = (
        "Merge the reviews into one short list of the most important improvements, most "
        "important first."
    )


def build_graph(config: Config) -> Graph:
    aspects = list(config.aspects)
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=110),
        *(
            Node(id=a, label=f"{a} (LLM)", kind="llm", x=220, y=i * 110)
            for i, a in enumerate(aspects)
        ),
        Node(id="merge", label="merge (LLM)", kind="llm", x=440, y=110),
        Node(id="end", label="end", kind="end", x=660, y=110),
    ]
    edges = [Edge(source="merge", target="end")]
    for a in aspects:
        edges += [
            Edge(source="start", target=a),
            Edge(source=a, target="merge"),
            Edge(source=a, target="end"),  # every review failed: no merge
        ]
    return Graph(nodes=nodes, edges=edges)


class ParallelWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _review(self, aspect: str, focus: str, text: str) -> str:
        system = fill(self.config.review_prompt, aspect=aspect, focus=focus)
        reply = await steps.chat(
            self.ctx, aspect, steps.messages(system, text), came_from=["start"]
        )
        return reply.content or ""

    async def _flow(self, prompt: str) -> Outcome:
        aspects = self.config.aspects
        async with self.ctx.tracer.span(SpanKind.STEP, "sections", node_id="start"):
            # A failed review does not cancel the others; its span already holds the error.
            results = await asyncio.gather(
                *(self._review(a, focus, prompt) for a, focus in aspects.items()),
                return_exceptions=True,
            )
        reviews = {a: r for a, r in zip(aspects, results, strict=True) if isinstance(r, str)}
        if not reviews:
            return Outcome("error", None, list(aspects), f"all {len(aspects)} reviews failed")
        body = "\n\n".join(f"{a} review:\n{r}" for a, r in reviews.items())
        merged = await steps.chat(
            self.ctx,
            "merge",
            steps.messages(self.config.merge_prompt, f"Text:\n{prompt}\n\n{body}"),
            came_from=list(reviews),
        )
        return Outcome("completed", merged.content or "", ["merge"])
