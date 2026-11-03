"""Block types, their field limits, and the layout rules that span blocks (data-model.md)."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator

from agent_lab.agents.config_fields import (
    LOCAL,
    BlockName,
    Prompt,
    Provider,
    ShortText,
    known_tool,
    unique,
)
from agent_lab.mcp.lab_server import LAB

MAX_BLOCKS = 30
MAX_DEPTH = 3
REFERENCE = re.compile(r"\{([a-z0-9-]{1,30})\}")

ToolName = Annotated[str, AfterValidator(known_tool)]
Loc = tuple[str | int, ...]


class CheckRule(BaseModel):
    rule: Literal["min_bullets", "max_words", "contains", "valid_json"]
    value: int | str | None = None


class ModelBlock(BaseModel):
    kind: Literal["model"] = "model"
    name: BlockName
    system: Prompt
    message: Prompt = "{previous}"
    tools: list[ToolName] = Field(default=[], max_length=6)
    max_iterations: int = Field(default=4, ge=1, le=10)  # model calls; used only with tools
    answer_on_last_call: bool = False  # the last call offers no tools, so the model must answer

    @field_validator("tools")
    @classmethod
    def unique_tools(cls, tools: list[str]) -> list[str]:
        unique(tools, "tool")
        return tools


class ToolBlock(BaseModel):
    kind: Literal["tool"] = "tool"
    name: BlockName
    tool: ToolName
    arguments: dict[str, Prompt]  # one template per tool parameter


class CheckBlock(CheckRule):
    kind: Literal["check"] = "check"
    name: BlockName


class Route(BaseModel):
    name: BlockName
    description: ShortText
    blocks: "list[Block]" = Field(min_length=1)


class RouterBlock(BaseModel):
    kind: Literal["router"] = "router"
    name: BlockName
    prompt: Prompt
    routes: list[Route] = Field(min_length=2, max_length=6)
    fallback: str


class Branch(BaseModel):
    name: BlockName
    blocks: "list[Block]" = Field(min_length=1)


class ParallelBlock(BaseModel):
    kind: Literal["parallel"] = "parallel"
    name: BlockName
    mode: Literal["branches", "per_item"]
    branches: list[Branch] | None = Field(default=None, min_length=1, max_length=6)
    planner: Prompt | None = None
    max_items: int | None = Field(default=None, ge=1, le=6)
    body: "list[Block] | None" = Field(default=None, min_length=1)


class LoopBlock(BaseModel):
    kind: Literal["loop"] = "loop"
    name: BlockName
    body: "list[Block]" = Field(min_length=1)
    exit: Literal["judge", "check"]
    judge: Prompt | None = None
    check: CheckRule | None = None
    max_rounds: int = Field(default=3, ge=1, le=5)


Block = Annotated[
    ModelBlock | ToolBlock | CheckBlock | RouterBlock | ParallelBlock | LoopBlock,
    Field(discriminator="kind"),
]
KIND_NAMES = frozenset({"model", "tool", "check", "router", "parallel", "loop"})
for _container in (Route, Branch, ParallelBlock, LoopBlock):
    _container.model_rebuild()


class BlocksConfig(BaseModel):
    model: str
    provider: Provider = LOCAL
    reasoning: bool = False
    blocks: list[Block] = Field(min_length=1)


DEFAULT_BLOCKS: list[Block] = [
    ModelBlock(name="answer", system="Answer the user's question briefly.")
]


class LayoutError(Exception):
    """Rules across blocks failed; each error has the loc of its field under `config`."""

    def __init__(self, errors: list[tuple[Loc, str]]) -> None:
        super().__init__("; ".join(msg for _, msg in errors))
        self.errors = errors


def children(block: Block) -> list[tuple[Loc, list[Block]]]:
    """The block lists a container holds, with their loc relative to the block."""
    if isinstance(block, RouterBlock):
        return [(("routes", i, "blocks"), r.blocks) for i, r in enumerate(block.routes)]
    if isinstance(block, ParallelBlock):
        if block.mode == "branches":
            return [
                (("branches", i, "blocks"), b.blocks) for i, b in enumerate(block.branches or [])
            ]
        return [(("body",), block.body)] if block.body else []
    if isinstance(block, LoopBlock):
        return [(("body",), block.body)]
    return []


def texts(block: Block) -> list[tuple[Loc, str]]:
    """Every prompt or template of a block that may hold references."""
    if isinstance(block, ModelBlock):
        return [(("system",), block.system), (("message",), block.message)]
    if isinstance(block, ToolBlock):
        return [(("arguments", k), v) for k, v in block.arguments.items()]
    if isinstance(block, RouterBlock):
        return [(("prompt",), block.prompt)]
    if isinstance(block, ParallelBlock):
        return [(("planner",), block.planner)] if block.planner else []
    if isinstance(block, LoopBlock):
        return [(("judge",), block.judge)] if block.judge else []
    return []


def rule_error(rule: CheckRule) -> str | None:
    value = rule.value
    if rule.rule in ("min_bullets", "max_words"):
        ok = isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 1000
        return None if ok else f"{rule.rule} needs a whole number from 1 to 1000"
    if rule.rule == "contains":
        ok = isinstance(value, str) and 1 <= len(value.strip()) <= 300
        return None if ok else "contains needs a text of 1 to 300 characters"
    return None if value is None else "valid_json takes no value"


def own_errors(block: Block) -> list[tuple[Loc, str]]:
    """Rules between the fields of one block."""
    errors: list[tuple[Loc, str]] = []
    if isinstance(block, ToolBlock):
        # Only the built-ins are known when saving; other servers check arguments when called.
        built_in = LAB.tools.get(block.tool.removeprefix("lab/"))
        expected: set[str] = set(built_in.parameters.get("properties", {})) if built_in else set()
        if built_in and set(block.arguments) != expected:
            errors.append(
                (("arguments",), f"arguments must be exactly: {', '.join(sorted(expected))}")
            )
    elif isinstance(block, CheckBlock):
        if message := rule_error(block):
            errors.append((("value",), message))
    elif isinstance(block, RouterBlock):
        seen: set[str] = set()
        for i, route in enumerate(block.routes):
            if route.name in seen:
                errors.append((("routes", i, "name"), f"duplicate route {route.name!r}"))
            seen.add(route.name)
        if block.fallback not in seen:
            errors.append((("fallback",), "the fallback must be one of the routes"))
    elif isinstance(block, ParallelBlock):
        per_item = block.mode == "per_item"
        fields = {"branches": block.branches, "planner": block.planner}
        fields |= {"max_items": block.max_items, "body": block.body}
        for field, value in fields.items():
            if (field != "branches") == per_item and value is None:
                errors.append(((field,), f"required in {block.mode} mode"))
            if (field != "branches") != per_item and value is not None:
                errors.append(((field,), f"not used in {block.mode} mode"))
        if block.branches:
            names = [b.name for b in block.branches]
            for i, name in enumerate(names):
                if name in names[:i]:
                    errors.append((("branches", i, "name"), f"duplicate branch {name!r}"))
    elif isinstance(block, LoopBlock):
        if block.exit == "judge" and block.judge is None:
            errors.append((("judge",), "a judge exit needs a judge prompt"))
        if block.exit == "check":
            if block.check is None:
                errors.append((("check",), "a check exit needs a check"))
            elif message := rule_error(block.check):
                errors.append((("check", "value"), message))
    return errors


def all_names(blocks: list[Block]) -> set[str]:
    names: set[str] = set()
    for block in blocks:
        names.add(block.name)
        for _, sub in children(block):
            names |= all_names(sub)
    return names


def layout_errors(config: BlocksConfig) -> list[tuple[Loc, str]]:
    """Limits, unique names, per-block rules and references, each at its field's loc."""
    errors: list[tuple[Loc, str]] = []
    everywhere = all_names(config.blocks)
    named: set[str] = set()
    count = 0

    def check_refs(loc: Loc, text: str, allowed: set[str]) -> None:
        for ref in REFERENCE.findall(text):
            if ref in allowed:
                continue
            known = ref in everywhere or ref in ("feedback", "item")
            message = (
                f"{{{ref}}} is not available here" if known else f"unknown reference {{{ref}}}"
            )
            errors.append((loc, message))

    def walk(blocks: list[Block], loc: Loc, depth: int, visible: set[str], words: set[str]) -> None:
        nonlocal count
        seen = set(visible)  # blocks that have run before this point on every path
        for i, block in enumerate(blocks):
            here = (*loc, i)
            count += 1
            if block.name in named:
                errors.append(((*here, "name"), f"duplicate block name {block.name!r}"))
            named.add(block.name)
            errors.extend(((*here, *field), message) for field, message in own_errors(block))
            allowed = seen | words | {"input", "previous"}
            for field, text in texts(block):
                extra: set[str] = (
                    {b.name for b in block.body} if isinstance(block, LoopBlock) else set()
                )
                check_refs((*here, *field), text, allowed | extra)  # a judge sees its body
            lists = children(block)
            if lists and depth >= MAX_DEPTH:
                errors.append(((*here, "kind"), f"nesting is limited to {MAX_DEPTH} levels"))
            inner = set(words)
            if isinstance(block, LoopBlock):
                inner.add("feedback")
            if isinstance(block, ParallelBlock) and block.mode == "per_item":
                inner.add("item")
            for suffix, sub in lists:
                walk(sub, (*here, *suffix), depth + 1, seen, inner)
            seen.add(block.name)

    walk(config.blocks, ("blocks",), 1, set(), set())
    if count > MAX_BLOCKS:
        errors.insert(0, (("blocks",), f"at most {MAX_BLOCKS} blocks, got {count}"))
    return errors
