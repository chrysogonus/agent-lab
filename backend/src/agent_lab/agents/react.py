"""ReAct: the model reasons, calls tools, sees their results, and repeats until it answers."""

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel

from agent_lab.graph import Edge, Graph, Node
from agent_lab.llm.base import ChatResponse, LLMClient, Message, ToolCall
from agent_lab.store import RunStatus
from agent_lab.tools.base import Tool, ToolError
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
    system_prompt: str = SYSTEM_PROMPT
    tools: list[str]
    max_iterations: int = 6


def config_version(config: ReActConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:12]


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


class ReActAgent:
    agent_id = AGENT_ID

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
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.config = config
        self.tracer = tracer
        self.graph = build_graph(list(self.tools))

    def start(self, prompt: str) -> ReActState:
        return ReActState(
            messages=[
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": prompt},
            ]
        )

    async def run(self, prompt: str) -> ReActState:
        """Loop `step` until the model answers or the iteration cap is hit.

        A Phase 2 tick runner replaces this loop and calls `step` once per tick.
        """
        state = self.start(prompt)
        async with self.tracer.span(
            SpanKind.STEP,
            f"invoke_agent {self.agent_id}",
            node_id="start",
            input=prompt,
            attributes={"gen_ai.operation.name": "invoke_agent"},
        ) as root:
            while not state.done and state.iteration < self.config.max_iterations:
                await self.step(state)
            async with self.tracer.span(SpanKind.STEP, "final answer", node_id="end") as end:
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
        async with self.tracer.span(SpanKind.STEP, f"iteration {state.iteration}", node_id="llm"):
            response = await self._chat(state.messages)
            state.messages.append(response.as_message())
            if not response.tool_calls:
                state.done = True
                state.status = "completed"
                state.answer = response.content or ""
                return state
            for call in response.tool_calls:
                result = await self._call_tool(call)
                state.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return state

    async def _chat(self, messages: list[Message]) -> ChatResponse:
        model = self.llm.model
        async with self.tracer.span(
            SpanKind.LLM,
            f"chat {model}",
            node_id="llm",
            input=list(messages),
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": self.llm.provider,
                "gen_ai.request.model": model,
            },
        ) as span:
            response = await self.llm.chat(messages, [t.schema() for t in self.tools.values()])
            span.output = response.as_message()
            span.model = response.model or model
            span.tokens_in = response.tokens_in
            span.tokens_out = response.tokens_out
            span.attributes |= {
                "gen_ai.response.model": span.model,
                "gen_ai.usage.input_tokens": response.tokens_in,
                "gen_ai.usage.output_tokens": response.tokens_out,
            }
        return response

    async def _call_tool(self, call: ToolCall) -> str:
        tool = self.tools.get(call.name)
        async with self.tracer.span(
            SpanKind.TOOL,
            f"execute_tool {call.name}",
            # An unknown tool has no node; attribute the span to the node that requested it.
            node_id=f"tool:{call.name}" if tool else "llm",
            input=call.arguments,
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": call.name,
                "gen_ai.tool.call.id": call.id,
            },
        ) as span:
            try:
                if tool is None:
                    raise ToolError(f"unknown tool {call.name!r}")
                result = tool.fn(**_parse_arguments(tool, call.arguments))
            except ToolError as exc:
                # Fed back to the model as the tool result, so it can recover.
                span.error = str(exc)
                result = f"error: {exc}"
            span.output = result
        return result


def _parse_arguments(tool: Tool, raw: str) -> dict[str, object]:
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"arguments are not valid JSON: {exc.msg}") from exc
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    expected = set(tool.parameters.get("properties", {}))
    missing = set(tool.parameters.get("required", [])) - args.keys()
    extra = args.keys() - expected
    if missing or extra:
        raise ToolError(f"invalid arguments: missing {sorted(missing)}, unexpected {sorted(extra)}")
    return args
