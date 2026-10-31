"""Routing: one model decision picks a route; only that route's handler runs."""

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model, field_validator, model_validator

from agent_lab.agents import steps
from agent_lab.agents.config_fields import (
    LOCAL,
    ItemName,
    Prompt,
    Provider,
    ShortText,
    known_tool,
    unique,
)
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import LLMClient
from agent_lab.tools.base import Tool
from agent_lab.tools.catalog import TOOLS
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer

AGENT_ID = "routing"
NAME = "Routing"
DESCRIPTION = "Classify the question as math, weather or general, then hand it to that handler."
SAMPLE_PROMPT = "What is 2**10 minus 24?"


class RouteSpec(BaseModel):
    name: ItemName
    description: ShortText  # what the router reads about this route
    prompt: Prompt
    tool: str | None = None

    @field_validator("tool")
    @classmethod
    def tool_known(cls, tool: str | None) -> str | None:
        return None if tool is None else known_tool(tool)


class Config(BaseModel):
    model: str
    provider: Provider = LOCAL
    reasoning: bool = False
    router_prompt: Prompt = "Classify the user's question."
    routes: list[RouteSpec] = Field(
        default=[
            RouteSpec(
                name="math",
                description="arithmetic or a calculation",
                prompt="Answer the arithmetic question. Use the calculator tool for every "
                "calculation, then answer briefly.",
                tool="calculator",
            ),
            RouteSpec(
                name="general",
                description="anything else",
                prompt="Answer the question briefly and accurately.",
            ),
            RouteSpec(
                name="weather",
                description="the weather or temperature in a city",
                prompt="Answer the weather question. Use the get_weather tool, then answer "
                "briefly.",
                tool="get_weather",
            ),
        ],
        min_length=2,
        max_length=6,
    )
    fallback: str = "general"  # used when the router's answer is unusable

    @field_validator("routes")
    @classmethod
    def unique_names(cls, routes: list[RouteSpec]) -> list[RouteSpec]:
        unique((r.name for r in routes), "route")
        return routes

    @model_validator(mode="after")
    def fallback_is_a_route(self) -> "Config":
        if self.fallback not in {r.name for r in self.routes}:
            raise ValueError(f"fallback {self.fallback!r} is not one of the routes")
        return self


def router_order(config: Config) -> list[RouteSpec]:
    """The routes as the router sees them: the fallback ("anything else") last."""
    others = [r for r in config.routes if r.name != config.fallback]
    return [*others, *(r for r in config.routes if r.name == config.fallback)]


def router_system(config: Config) -> str:
    lines = (f" {r.name}: {r.description.rstrip('.')}." for r in router_order(config))
    return config.router_prompt + "".join(lines)


def route_model(names: list[str]) -> type[BaseModel]:
    """The decision schema lists exactly the agent's route names."""
    label: Any = Literal[tuple(names)]  # names are only known at run time
    return create_model("Route", label=(label, ...))


def build_graph(config: Config) -> Graph:
    # One column: each route, then its tool where that tool first appears (a shared tool is one
    # node).
    items: list[tuple[str, str, Literal["llm", "tool"]]] = []
    for route in config.routes:
        items.append((route.name, f"{route.name} (LLM)", "llm"))
        if route.tool and f"tool:{route.tool}" not in {i for i, _, _ in items}:
            items.append((f"tool:{route.tool}", route.tool, "tool"))
    column = [
        Node(id=id_, label=label, kind=kind, x=450, y=i * 110)
        for i, (id_, label, kind) in enumerate(items)
    ]
    mid = (len(column) - 1) * 55
    nodes = [
        Node(id="start", label="start", kind="start", x=0, y=mid),
        Node(id="router", label="router (LLM)", kind="llm", x=200, y=mid),
        *column,
        Node(id="end", label="end", kind="end", x=700, y=mid),
    ]
    edges = [Edge(source="start", target="router")]
    for route in config.routes:
        edges += [Edge(source="router", target=route.name), Edge(source=route.name, target="end")]
    for route in config.routes:
        if route.tool:
            tool = f"tool:{route.tool}"
            edges += [Edge(source=route.name, target=tool), Edge(source=tool, target=route.name)]
    return Graph(nodes=nodes, edges=edges)


class RoutingWorkflow:
    def __init__(self, *, llm: LLMClient, config: Config, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        ctx, c = self.ctx, self.config
        routes = {r.name: r for r in c.routes}
        try:
            decision = await steps.decide(
                ctx,
                "router",
                "route",
                steps.messages(router_system(c), prompt),
                route_model([r.name for r in router_order(c)]),
                kind=SpanKind.ROUTE,
                came_from=["start"],
            )
            label: str = decision.model_dump()["label"]
        except DecisionError:
            label = c.fallback  # always safe; the route span keeps the error
        route = routes[label]
        if route.tool is None:
            reply = await steps.chat(
                ctx, route.name, steps.messages(route.prompt, prompt), came_from=["router"]
            )
            return Outcome("completed", reply.content or "", [route.name])
        return await self._with_tool(route.name, TOOLS[route.tool], route.prompt, prompt)

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
