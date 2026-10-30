"""Orchestrator-workers: the model plans 1-4 subtasks at run time, workers run concurrently."""

import asyncio
from itertools import pairwise
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from agent_lab.agents import steps
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "orchestrator"
NAME = "Orchestrator-workers"
DESCRIPTION = "Split a trip-note request into subtasks at run time, work them, combine the parts."
SAMPLE_PROMPT = "A weekend trip note for Porto in autumn, travelling by train from Lisbon."

MAX_SUBTASKS = 4


class Config(BaseModel):
    model: str
    reasoning: bool = False
    orchestrator_prompt: str = (
        f"Split the user's trip-note request into 2 to {MAX_SUBTASKS} independent subtasks, "
        "e.g. one per topic (getting there, sights, food, practical tips). Each subtask is one "
        "short instruction."
    )
    worker_prompt: str = "Do the subtask for the request in at most 60 words."
    synthesizer_prompt: str = (
        "Combine the parts into one short, well-structured trip note of at most 200 words."
    )


Subtask = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Plan(BaseModel):
    subtasks: list[Subtask] = Field(min_length=1, max_length=MAX_SUBTASKS)


def build_graph() -> Graph:
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=0),
        Node(id="orchestrator", label="orchestrator (LLM)", kind="llm", x=200, y=0),
        Node(id="worker", label="worker (LLM)", kind="llm", x=420, y=0),
        Node(id="synthesizer", label="synthesizer (LLM)", kind="llm", x=640, y=0),
        Node(id="end", label="end", kind="end", x=860, y=110),
    ]
    path = ["start", "orchestrator", "worker", "synthesizer", "end"]
    edges = [Edge(source=a, target=b) for a, b in pairwise(path)]
    edges.append(Edge(source="orchestrator", target="end"))  # invalid plan
    return Graph(nodes=nodes, edges=edges)


class OrchestratorWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, AGENT_ID, prompt, self._flow)

    async def _work(self, index: int, subtask: str, prompt: str) -> str:
        # One node for all workers; the span name and index tell them apart.
        async with self.ctx.tracer.span(
            SpanKind.STEP,
            f"worker {index}",
            node_id="worker",
            input=subtask,
            attributes={**steps.came_from(["orchestrator"]), "lab.worker.index": index},
        ) as span:
            user = f"Request: {prompt}\n\nSubtask: {subtask}"
            reply = await steps.chat(
                self.ctx, "worker", steps.messages(self.config.worker_prompt, user)
            )
            span.output = reply.content
        return reply.content or ""

    async def _flow(self, prompt: str) -> Outcome:
        c = self.config
        try:
            plan = await steps.decide(
                self.ctx,
                "orchestrator",
                "plan",
                steps.messages(c.orchestrator_prompt, prompt),
                Plan,
                came_from=["start"],
            )
        except DecisionError as exc:
            return Outcome("error", None, ["orchestrator"], str(exc))  # no safe default plan
        parts = await asyncio.gather(
            *(self._work(i, s, prompt) for i, s in enumerate(plan.subtasks))
        )
        body = "\n\n".join(
            f"Part {i + 1}: {s}\n{p}"
            for i, (s, p) in enumerate(zip(plan.subtasks, parts, strict=True))
        )
        reply = await steps.chat(
            self.ctx,
            "synthesizer",
            steps.messages(c.synthesizer_prompt, f"Request: {prompt}\n\n{body}"),
            came_from=["worker"],
        )
        return Outcome("completed", reply.content or "", ["synthesizer"])
