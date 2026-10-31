"""ReAct: the model reasons, calls tools, sees their results, and repeats until it answers."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from agent_lab.agents import steps
from agent_lab.agents.config_fields import LOCAL, Prompt, Provider, known_tool, unique
from agent_lab.agents.steps import StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient, Message
from agent_lab.store import RunStatus
from agent_lab.tools.base import Tool
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "react"

SYSTEM_PROMPT = (
    "You are a precise assistant. Use the provided tools for arithmetic and weather instead "
    "of guessing. When you have everything you need, answer briefly without calling tools."
)


class ReActConfig(BaseModel):
    """Everything that changes behavior; hashed into `config_version`."""

    model: str
    provider: Provider = LOCAL
    system_prompt: Prompt = SYSTEM_PROMPT
    tools: list[str] = ["calculator", "get_weather"]
    max_iterations: int = Field(default=6, ge=1, le=10)
    reasoning: bool = True

    @field_validator("tools")
    @classmethod
    def known_unique_tools(cls, tools: list[str]) -> list[str]:
        unique(tools, "tool")
        return [known_tool(t) for t in tools]


def build_graph(tool_names: list[str]) -> Graph:
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=0),
        Node(id="llm", label="reason (LLM)", kind="llm", x=240, y=0),
        Node(id="end", label="end", kind="end", x=480, y=0),
    ]
    edges = [Edge(source="start", target="llm"), Edge(source="llm", target="end")]
    for i, name in enumerate(tool_names):
        node_id = f"tool:{name}"
        x = 240 + (i - (len(tool_names) - 1) / 2) * 220
        nodes.append(Node(id=node_id, label=name, kind="tool", x=x, y=180))
        edges += [Edge(source="llm", target=node_id), Edge(source=node_id, target="llm")]
    return Graph(nodes=nodes, edges=edges)


@dataclass
class ReActState:
    messages: list[Message]
    iteration: int = 0
    done: bool = False
    status: RunStatus = "running"
    answer: str | None = None
    # Node(s) the next visit comes from: start, then the tools of the previous turn.
    came_from: list[str] = field(default_factory=lambda: ["start"])


class ReActAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        tools: list[Tool],
        config: ReActConfig,
        tracer: Tracer,
        granted_scopes: frozenset[str] = frozenset(),
    ) -> None:
        for tool in tools:
            if not tool.scopes <= granted_scopes:
                missing = sorted(tool.scopes - granted_scopes)
                raise ValueError(f"tool {tool.name!r} needs ungranted scopes {missing}")
        self.tools = {t.name: t for t in tools}
        self.config = config
        self.tracer = tracer
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)
        self.graph = build_graph(list(self.tools))

    def start(self, prompt: str) -> ReActState:
        return ReActState(messages=steps.messages(self.config.system_prompt, prompt))

    async def run(self, prompt: str) -> ReActState:
        """Loop `step` until the model answers or the iteration cap is hit.

        A Phase 2 tick runner replaces this loop and calls `step` once per tick.
        """
        state = self.start(prompt)
        async with self.tracer.span(
            SpanKind.STEP,
            f"invoke_agent {self.tracer.agent_id}",
            node_id="start",
            input=prompt,
            attributes={"gen_ai.operation.name": "invoke_agent"},
        ) as root:
            while not state.done and state.iteration < self.config.max_iterations:
                await self.step(state)
            async with self.tracer.span(
                SpanKind.STEP,
                "final answer",
                node_id="end",
                # The answer and the iteration cap are both decided at the llm node.
                attributes=steps.came_from(["llm"]),
            ) as end:
                if state.done:
                    end.output = state.answer
                else:
                    state.status = "max_iterations"
                    end.error = f"max iterations ({self.config.max_iterations}) reached"
            root.output = state.answer
            root.error = end.error
        return state

    async def step(self, state: ReActState) -> ReActState:
        """One iteration: a model call, then every tool call it requested."""
        state.iteration += 1
        async with self.tracer.span(
            SpanKind.STEP,
            f"iteration {state.iteration}",
            node_id="llm",
            attributes=steps.came_from(state.came_from),
        ):
            response = await steps.chat(
                self.ctx, "llm", state.messages, tools=list(self.tools.values())
            )
            state.messages.append(response.as_message())
            if not response.tool_calls:
                state.done = True
                state.status = "completed"
                state.answer = response.content or ""
                return state
            # Unknown tools have no node, so they never become an edge.
            state.came_from = [
                f"tool:{c.name}" for c in response.tool_calls if c.name in self.tools
            ]
            for call in response.tool_calls:
                result = await steps.call_tool(
                    self.ctx, self.tools, call, caller="llm", came_from=["llm"]
                )
                state.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return state
