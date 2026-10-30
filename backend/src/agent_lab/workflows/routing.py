"""Routing: one model decision picks math, weather or general; only that handler runs."""

from typing import Literal

from pydantic import BaseModel

from agent_lab.agents import steps
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tools.base import Tool
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "routing"
NAME = "Routing"
DESCRIPTION = "Classify the question as math, weather or general, then hand it to that handler."
SAMPLE_PROMPT = "What is 2**10 minus 24?"

# The tool each tool-using handler gets.
HANDLER_TOOLS: dict[str, Tool] = {"math": CALCULATOR, "weather": WEATHER}


class Config(BaseModel):
    model: str
    reasoning: bool = False
    router_prompt: str = (
        "Classify the user's question. math: arithmetic or a calculation. weather: the weather "
        "or temperature in a city. general: anything else."
    )
    math_prompt: str = (
        "Answer the arithmetic question. Use the calculator tool for every calculation, "
        "then answer briefly."
    )
    weather_prompt: str = (
        "Answer the weather question. Use the get_weather tool, then answer briefly."
    )
    general_prompt: str = "Answer the question briefly and accurately."


class Route(BaseModel):
    label: Literal["math", "weather", "general"]


def build_graph() -> Graph:
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=220),
        Node(id="router", label="router (LLM)", kind="llm", x=200, y=220),
        Node(id="math", label="math (LLM)", kind="llm", x=450, y=0),
        Node(id="tool:calculator", label="calculator", kind="tool", x=450, y=110),
        Node(id="general", label="general (LLM)", kind="llm", x=450, y=220),
        Node(id="weather", label="weather (LLM)", kind="llm", x=450, y=330),
        Node(id="tool:get_weather", label="get_weather", kind="tool", x=450, y=440),
        Node(id="end", label="end", kind="end", x=700, y=220),
    ]
    edges = [Edge(source="start", target="router")]
    for handler in ("math", "general", "weather"):
        edges += [Edge(source="router", target=handler), Edge(source=handler, target="end")]
    for handler, tool in HANDLER_TOOLS.items():
        node = f"tool:{tool.name}"
        edges += [Edge(source=handler, target=node), Edge(source=node, target=handler)]
    return Graph(nodes=nodes, edges=edges)


class RoutingWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, AGENT_ID, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        ctx, c = self.ctx, self.config
        try:
            route = await steps.decide(
                ctx,
                "router",
                "route",
                steps.messages(c.router_prompt, prompt),
                Route,
                kind=SpanKind.ROUTE,
                came_from=["start"],
            )
            label = route.label
        except DecisionError:
            label = "general"  # always safe; the route span keeps the error
        if label == "general":
            reply = await steps.chat(
                ctx, "general", steps.messages(c.general_prompt, prompt), came_from=["router"]
            )
            return Outcome("completed", reply.content or "", ["general"])
        system = c.math_prompt if label == "math" else c.weather_prompt
        return await self._with_tool(label, HANDLER_TOOLS[label], system, prompt)

    async def _with_tool(self, node: str, tool: Tool, system: str, prompt: str) -> Outcome:
        """One model call with the handler's tool, its tool calls, then the answer."""
        messages = steps.messages(system, prompt)
        first = await steps.chat(self.ctx, node, messages, tools=[tool], came_from=["router"])
        if not first.tool_calls:
            return Outcome("completed", first.content or "", [node])
        messages.append(first.as_message())
        ran = False
        for call in first.tool_calls:
            result = await steps.call_tool(
                self.ctx, {tool.name: tool}, call, caller=node, came_from=[node]
            )
            ran = ran or call.name == tool.name
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        # Only a tool that ran is an edge back; after unknown tools the call stays on the node.
        final = await steps.chat(
            self.ctx, node, messages, came_from=[f"tool:{tool.name}"] if ran else None
        )
        return Outcome("completed", final.content or "", [node])
