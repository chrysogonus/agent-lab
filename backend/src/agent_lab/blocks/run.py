"""Run a block agent: blocks top to bottom, only through the traced step helpers.

`lab.came_from` on the first span of each node visit holds the nodes that actually ran before
it, so every recorded transition is an edge of `blocks.graph.build_graph`.
"""

import asyncio
import json
from collections.abc import Iterable, Sequence
from typing import Any, cast

from agent_lab.agents import steps
from agent_lab.agents.config_fields import fill
from agent_lab.agents.steps import DecisionError, Outcome, StepContext
from agent_lab.blocks.model import (
    Block,
    BlocksConfig,
    CheckBlock,
    CheckRule,
    LoopBlock,
    ModelBlock,
    ParallelBlock,
    RouterBlock,
    ToolBlock,
)
from agent_lab.llm.base import LLMClient, Message, ToolCall
from agent_lab.tools.catalog import TOOLS
from agent_lab.tracing.span import SpanKind
from agent_lab.tracing.tracer import Tracer
from agent_lab.workflows.chain import check_outline
from agent_lab.workflows.evaluator import Verdict
from agent_lab.workflows.orchestrator import plan_model
from agent_lab.workflows.routing import route_model

Scope = dict[str, str]  # reference name -> its value
Result = tuple[str, list[str], Scope]  # output, nodes it ended at, the list's scope


class Stop(Exception):
    """Ends the run from any depth: a failed check, an unusable plan or a cap."""

    def __init__(self, outcome: Outcome) -> None:
        super().__init__(outcome.error)
        self.outcome = outcome


def check(rule: CheckRule, text: str) -> str | None:
    """Why `text` fails the rule, or None when it passes."""
    value = rule.value
    if rule.rule == "min_bullets":
        result = check_outline(text, cast(int, value))
        return None if result.passed else result.reason
    if rule.rule == "max_words":
        words = len(text.split())
        return None if words <= cast(int, value) else f"{words} words, at most {value}"
    if rule.rule == "contains":
        return None if cast(str, value) in text else f"does not contain {value!r}"
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return f"not valid JSON: {exc.msg}"
    return None


def _joined(parts: Sequence[tuple[str, str]]) -> str:
    return "\n\n".join(f"{name}:\n{output}" for name, output in parts)


def _unique(nodes: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(nodes))


class BlockAgent:
    def __init__(self, *, llm: LLMClient, config: BlocksConfig, tracer: Tracer) -> None:
        self.config = config
        self.ctx = StepContext(llm=llm, tracer=tracer, reasoning=config.reasoning)

    async def run(self, prompt: str) -> Outcome:
        return await steps.invoke(self.ctx, prompt, self._flow)

    async def _flow(self, prompt: str) -> Outcome:
        try:
            output, last, _ = await self._list(
                self.config.blocks, {"input": prompt}, prompt, ["start"]
            )
        except Stop as stop:
            return stop.outcome
        return Outcome("completed", output, last)

    async def _list(
        self, blocks: list[Block], outer: Scope, previous: str, came: list[str]
    ) -> Result:
        scope = dict(outer)  # names inside a container are not visible after it
        for block in blocks:
            scope["previous"] = previous
            previous, came = await self._block(block, scope, came)
            scope[block.name] = previous
        return previous, came, scope

    async def _all(
        self, lists: Sequence[tuple[list[Block], Scope, list[str]]], previous: str
    ) -> list[Result]:
        """Lists run concurrently; every one finishes (and stays in the trace) before any error."""
        results = await asyncio.gather(
            *(self._list(blocks, scope, previous, came) for blocks, scope, came in lists),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return cast(list[Result], results)

    async def _block(self, block: Block, scope: Scope, came: list[str]) -> tuple[str, list[str]]:
        previous = scope["previous"]
        if isinstance(block, ModelBlock):
            return await self._model(block, scope, came)
        if isinstance(block, ToolBlock):
            arguments = {k: fill(v, **scope) for k, v in block.arguments.items()}
            call = ToolCall(id=block.name, name=block.tool, arguments=json.dumps(arguments))
            result = await steps.call_tool(
                self.ctx, TOOLS, call, caller=block.name, came_from=came, node_id=block.name
            )
            return result, [block.name]
        if isinstance(block, CheckBlock):
            await self._check(block, block, previous, came, stop=True)
            return previous, [block.name]
        if isinstance(block, RouterBlock):
            return await self._router(block, scope, came)
        if isinstance(block, ParallelBlock):
            return await self._parallel(block, scope, came)
        return await self._loop(block, scope, came)

    async def _model(
        self, block: ModelBlock, scope: Scope, came: list[str]
    ) -> tuple[str, list[str]]:
        messages = steps.messages(fill(block.system, **scope), fill(block.message, **scope))
        if not block.tools:
            reply = await steps.chat(self.ctx, block.name, messages, came_from=came)
            return reply.content or "", [block.name]
        tools = {t: TOOLS[t] for t in block.tools}
        for iteration in range(1, block.max_iterations + 1):  # the ReAct loop as one block
            reply = await steps.chat(
                self.ctx,
                block.name,
                messages,
                tools=list(tools.values()),
                came_from=came,
                attributes={"lab.iteration": iteration},
            )
            messages.append(reply.as_message())
            if not reply.tool_calls:
                return reply.content or "", [block.name]
            for call in reply.tool_calls:
                result = await steps.call_tool(
                    self.ctx, tools, call, caller=block.name, came_from=[block.name]
                )
                tool_message: Message = {"role": "tool", "tool_call_id": call.id, "content": result}
                messages.append(tool_message)
            # Unknown tools have no node, so they never become an edge.
            came = _unique(f"tool:{c.name}" for c in reply.tool_calls if c.name in tools)
        raise Stop(
            Outcome(
                "max_iterations",
                None,
                [block.name],
                f"max iterations ({block.max_iterations}) reached in {block.name}",
            )
        )

    async def _check(
        self,
        block: CheckBlock | LoopBlock,
        rule: CheckRule,
        text: str,
        came: list[str],
        *,
        stop: bool,
    ) -> str | None:
        async with self.ctx.tracer.span(
            SpanKind.STEP,
            f"check {rule.rule}",
            node_id=block.name,
            input=text,
            attributes=steps.came_from(came),
        ) as span:
            reason = check(rule, text)
            span.output = {"passed": reason is None, "reason": reason}
        if reason and stop:
            raise Stop(Outcome("error", None, [block.name], f"check {block.name} failed: {reason}"))
        return reason

    async def _router(
        self, block: RouterBlock, scope: Scope, came: list[str]
    ) -> tuple[str, list[str]]:
        # The fallback ("anything else") is listed last, as in the routing template.
        order = [r for r in block.routes if r.name != block.fallback]
        order += [r for r in block.routes if r.name == block.fallback]
        system = fill(block.prompt, **scope)
        system += "".join(f" {r.name}: {r.description.rstrip('.')}." for r in order)
        try:
            decision = await steps.decide(
                self.ctx,
                block.name,
                "route",
                steps.messages(system, scope["previous"]),
                route_model([r.name for r in order]),
                kind=SpanKind.ROUTE,
                came_from=came,
            )
            label: str = decision.model_dump()["label"]
        except DecisionError:
            label = block.fallback  # always safe; the route span keeps the error
        route = next(r for r in block.routes if r.name == label)
        output, last, _ = await self._list(route.blocks, scope, scope["previous"], [block.name])
        return output, last

    async def _parallel(
        self, block: ParallelBlock, scope: Scope, came: list[str]
    ) -> tuple[str, list[str]]:
        previous = scope["previous"]
        if block.mode == "branches":
            branches = block.branches or []
            results = await self._all([(b.blocks, scope, came) for b in branches], previous)
            names = [b.name for b in branches]
        else:
            try:
                plan = await steps.decide(
                    self.ctx,
                    block.name,
                    "plan",
                    steps.messages(fill(block.planner or "", **scope), previous),
                    plan_model(block.max_items or 1),
                    came_from=came,
                )
            except DecisionError as exc:
                raise Stop(Outcome("error", None, [block.name], str(exc))) from exc
            names = cast(list[str], plan.model_dump()["subtasks"])
            body = block.body or []
            results = await self._all(
                [(body, {**scope, "item": n}, [block.name]) for n in names], previous
            )
        output = _joined([(name, r[0]) for name, r in zip(names, results, strict=True)])
        return output, _unique([n for r in results for n in r[1]])

    async def _loop(self, block: LoopBlock, scope: Scope, came: list[str]) -> tuple[str, list[str]]:
        feedback, output = "", scope["previous"]
        for round_ in range(1, block.max_rounds + 1):
            output, last, inner = await self._list(
                block.body, {**scope, "feedback": feedback}, scope["previous"], came
            )
            if block.check is not None and block.exit == "check":
                reason = await self._check(block, block.check, output, last, stop=False)
            else:
                reason = await self._judge(
                    block, {**inner, "previous": output}, output, last, round_
                )
            if reason is None:
                return output, [block.name]
            feedback = f"Previous answer:\n{output}\n\nFeedback:\n{reason}"
            came = [block.name]
        raise Stop(
            Outcome(
                "max_iterations",
                output,
                [block.name],
                f"not approved after {block.max_rounds} rounds",
            )
        )

    async def _judge(
        self, block: LoopBlock, scope: Scope, output: str, came: list[str], round_: int
    ) -> str | None:
        """The judge's feedback, or None when it approves."""
        attributes: dict[str, Any] = {"lab.round": round_}
        try:
            verdict = await steps.decide(
                self.ctx,
                block.name,
                "verdict",
                steps.messages(fill(block.judge or "", **scope), output),
                Verdict,
                came_from=came,
                attributes=attributes,
            )
        except DecisionError as exc:
            # An unreadable verdict counts as a rejection, as in the evaluator template.
            return str(exc)
        return None if verdict.approved else verdict.feedback or "not approved"
