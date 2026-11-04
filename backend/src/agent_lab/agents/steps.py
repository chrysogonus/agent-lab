"""Traced building blocks shared by every agent and workflow (contracts/trace-conventions.md).

`chat`, `call_tool` and `decide` are the only paths to the model and the tools, so every call
gets a span. `lab.came_from` on the first span of a node visit records the graph edge taken.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from agent_lab.llm.base import ChatResponse, LLMClient, Message, ToolCall
from agent_lab.mcp.host import HostTool
from agent_lab.store import RunStatus
from agent_lab.tools.base import ToolError
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer


@dataclass
class StepContext:
    llm: LLMClient
    tracer: Tracer
    reasoning: bool  # sent with every model call; False turns model thinking off


@dataclass
class Outcome:
    status: RunStatus
    answer: str | None
    last: list[str]  # node(s) the final step is reached from
    error: str | None = None  # why the run did not complete


class DecisionError(Exception):
    """The model's decision could not be read or failed validation."""


def config_version(config: BaseModel) -> str:
    """Hash of everything that changes behavior, so runs of different configs stay apart."""
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:12]


def came_from(nodes: Sequence[str] | None) -> dict[str, Any]:
    """Span attributes for the first span of a node visit; omitted when there is no edge."""
    return {"lab.came_from": list(dict.fromkeys(nodes))} if nodes else {}


def messages(system: str, user: str) -> list[Message]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def chat(
    ctx: StepContext,
    node_id: str,
    messages: list[Message],
    *,
    tools: Mapping[str, HostTool] | None = None,
    response_format: dict[str, Any] | None = None,
    came_from: Sequence[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> ChatResponse:
    model = ctx.llm.model
    extra = {"gen_ai.request.response_format": response_format} if response_format else {}
    async with ctx.tracer.span(
        SpanKind.LLM,
        f"chat {model}",
        node_id=node_id,
        input=list(messages),
        attributes={
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": ctx.llm.provider,
            "gen_ai.request.model": model,
            "lab.reasoning": ctx.reasoning,
            **extra,
            **_came_from(came_from),
            **(attributes or {}),
        },
    ) as span:
        response = await ctx.llm.chat(
            messages,
            [t.schema(name) for name, t in (tools or {}).items()],
            response_format=response_format,
            reasoning=ctx.reasoning,
        )
        span.output = response.as_message()
        if response.reasoning:
            span.output["reasoning"] = response.reasoning
        span.model = response.model or model
        span.tokens_in = response.tokens_in
        span.tokens_out = response.tokens_out
        span.attributes |= {
            "gen_ai.response.model": span.model,
            "gen_ai.usage.input_tokens": response.tokens_in,
            "gen_ai.usage.output_tokens": response.tokens_out,
        }
        if response.tokens_cache_read is not None:
            span.attributes |= {
                "gen_ai.usage.cache_read.input_tokens": response.tokens_cache_read,
                "gen_ai.usage.cache_creation.input_tokens": response.tokens_cache_write,
            }
    return response


async def call_tool(
    ctx: StepContext,
    tools: Mapping[str, HostTool],
    call: ToolCall,
    *,
    caller: str,
    came_from: Sequence[str] | None = None,
    node_id: str | None = None,
) -> str:
    """Send one tool call to its server; errors become the result text so the model can recover.

    `tools` maps the names the model sees to the tools. `node_id` replaces the shared
    `tool:<config name>` node (a block agent's tool-call block).
    """
    tool = tools.get(call.name)
    async with ctx.tracer.span(
        SpanKind.TOOL,
        f"execute_tool {tool.config_name if tool else call.name}",
        # An unknown tool has no node; attribute the span to the node that requested it.
        node_id=(node_id or f"tool:{tool.config_name}") if tool else caller,
        input=call.arguments,
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool.config_name if tool else call.name,
            "gen_ai.tool.call.id": call.id,
            **(_came_from(came_from) if tool else {}),
        },
    ) as span:
        try:
            if tool is None:
                raise ToolError(f"unknown tool {call.name!r}")
            arguments = _parse_arguments(call.arguments)
        except ToolError as exc:
            # Fed back to the model as the tool result, so it can recover.
            span.error = str(exc)
            span.output = f"error: {exc}"
            return span.output
        result = await tool.call(arguments)
        span.attributes |= {
            "mcp.method.name": "tools/call",
            "mcp.protocol.version": tool.connection.protocol_version,
            "jsonrpc.request.id": result.request["id"],
            "lab.mcp.server": tool.server,
            "lab.mcp.request": result.request,
            "lab.mcp.response": result.response,
        }
        span.error = result.error
        span.output = result.text
    return result.text


async def decide[T: BaseModel](
    ctx: StepContext,
    node_id: str,
    name: str,
    messages: list[Message],
    model_cls: type[T],
    *,
    kind: SpanKind = SpanKind.STEP,
    came_from: Sequence[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> T:
    """Ask for a JSON-schema decision and validate it; raises `DecisionError` if unusable."""
    schema = model_cls.model_json_schema()
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": name, "schema": schema, "strict": True},
    }
    async with ctx.tracer.span(
        kind,
        name,
        node_id=node_id,
        input={"messages": list(messages), "schema": schema},
        attributes={**_came_from(came_from), **(attributes or {})},
    ) as span:
        response = await chat(ctx, node_id, messages, response_format=response_format)
        content = response.content or ""
        try:
            decision = _parse_decision(content, model_cls)
        except DecisionError as exc:
            span.error = f"invalid {name}: {exc}; got {content[:200]!r}"
            raise DecisionError(span.error) from exc
        span.output = decision.model_dump()
    return decision


async def invoke(
    ctx: StepContext, prompt: str, flow: Callable[[str], Awaitable[Outcome]]
) -> Outcome:
    """Run `flow` between the root span at `start` and the final span at `end`."""
    async with ctx.tracer.span(
        SpanKind.STEP,
        f"invoke_agent {ctx.tracer.agent_id}",  # the run's agent: a template or a custom agent
        node_id="start",
        input=prompt,
        attributes={"gen_ai.operation.name": "invoke_agent"},
    ) as root:
        outcome = await flow(prompt)
        async with ctx.tracer.span(
            SpanKind.STEP, "final answer", node_id="end", attributes=_came_from(outcome.last)
        ) as end:
            end.output = outcome.answer
            end.error = outcome.error
        root.output = outcome.answer
        root.error = outcome.error
    return outcome


_came_from = came_from  # helpers shadow the name with their parameter


def _parse_decision[T: BaseModel](content: str, model_cls: type[T]) -> T:
    try:
        return model_cls.model_validate_json(content)
    except ValidationError as exc:
        objects = _json_objects(content)
        if len(objects) != 1:
            raise DecisionError(_errors(exc)) from exc
    try:
        # The model wrapped the JSON in prose or a code fence.
        return model_cls.model_validate(objects[0])
    except ValidationError as exc:
        raise DecisionError(_errors(exc)) from exc


def _json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object embedded in `text`."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    i = text.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found.append(cast(dict[str, Any], obj))
        i = text.find("{", end)
    return found


def _errors(exc: ValidationError) -> str:
    return "; ".join(e["msg"] for e in exc.errors())


def _parse_arguments(raw: str) -> dict[str, Any]:
    """The model's argument text as an object; the server checks the arguments themselves."""
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"arguments are not valid JSON: {exc.msg}") from exc
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    return cast(dict[str, Any], args)  # JSON object keys are always strings
