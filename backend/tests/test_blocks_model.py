"""Block shapes, field limits and the layout rules across blocks (FR-003 to FR-010, FR-017)."""

from typing import Any

import pytest
from helpers import (
    BlockDict,
    blocks_config,
    branches_block,
    check_block,
    loop_block,
    model_block,
    per_item_block,
    router_block,
    tool_block,
)
from pydantic import ValidationError

from agent_lab.blocks.model import BlocksConfig, layout_errors


def field_error_locs(*blocks: BlockDict) -> list[tuple[Any, ...]]:
    with pytest.raises(ValidationError) as exc:
        blocks_config(*blocks)
    return [e["loc"] for e in exc.value.errors()]


def layout(*blocks: BlockDict) -> list[tuple[tuple[str | int, ...], str]]:
    return layout_errors(blocks_config(*blocks))


def test_valid_layout_of_every_kind() -> None:
    config = blocks_config(
        model_block("draft", tools=["calculator"], max_iterations=10),
        tool_block("calc", expression="{draft}"),
        check_block("enough", "max_words", 1000),
        router_block("route", {"math": [model_block("m")], "other": [model_block("o")]}),
        branches_block("reviews", {"a": [model_block("ra")], "b": [model_block("rb")]}),
        per_item_block("plan", [model_block("work", message="{item}")], max_items=6),
        loop_block("improve", [model_block("gen", message="{input}\n{feedback}")], max_rounds=5),
        model_block("final", message="{route}\n{reviews}\n{plan}\n{improve}\n{calc}"),
    )
    assert layout_errors(config) == []
    assert config.blocks[0].kind == "model"


@pytest.mark.parametrize(
    ("block", "loc"),
    [
        (model_block("a", system=" "), ("blocks", 0, "model", "system")),
        (model_block("a", message="x" * 4001), ("blocks", 0, "model", "message")),
        (model_block("a", tools=["read_file"]), ("blocks", 0, "model", "tools", 0)),
        (model_block("a", tools=["calculator", "calculator"]), ("blocks", 0, "model", "tools")),
        (model_block("a", max_iterations=11), ("blocks", 0, "model", "max_iterations")),
        (model_block("Bad"), ("blocks", 0, "model", "name")),
        (model_block("input"), ("blocks", 0, "model", "name")),
        (tool_block("t", tool="read_file"), ("blocks", 0, "tool", "tool")),
        (check_block("c", "is_short"), ("blocks", 0, "check", "rule")),
        (router_block("r", {"only": [model_block("m")]}), ("blocks", 0, "router", "routes")),
        (
            router_block("r", {"a": [model_block("m")], "b": []}),
            ("blocks", 0, "router", "routes", 1, "blocks"),
        ),
        (
            branches_block("p", {f"b{i}": [model_block(f"m{i}")] for i in range(7)}),
            ("blocks", 0, "parallel", "branches"),
        ),
        (
            per_item_block("p", [model_block("m")], max_items=0),
            ("blocks", 0, "parallel", "max_items"),
        ),
        (loop_block("l", [model_block("m")], max_rounds=6), ("blocks", 0, "loop", "max_rounds")),
        (loop_block("l", []), ("blocks", 0, "loop", "body")),
    ],
)
def test_field_limits(block: BlockDict, loc: tuple[Any, ...]) -> None:
    assert loc in field_error_locs(block)


def test_no_blocks_rejected() -> None:
    with pytest.raises(ValidationError):
        BlocksConfig.model_validate({"model": "m", "blocks": []})


@pytest.mark.parametrize(
    ("blocks", "loc", "message"),
    [
        (
            [model_block("a"), model_block("a")],
            ("blocks", 1, "name"),
            "duplicate block name 'a'",
        ),
        (
            [router_block("r", {"x": [model_block("a")], "y": [model_block("a")]})],
            ("blocks", 0, "routes", 1, "blocks", 0, "name"),
            "duplicate block name 'a'",
        ),
        (
            [router_block("r", {"x": [model_block("m")], "y": [model_block("n")]}, "z")],
            ("blocks", 0, "fallback"),
            "the fallback must be one of the routes",
        ),
        (
            [tool_block("t", expression="1", extra="2")],
            ("blocks", 0, "arguments"),
            "arguments must be exactly: expression",
        ),
        (
            [check_block("c", "min_bullets", "three")],
            ("blocks", 0, "value"),
            "min_bullets needs a whole number from 1 to 1000",
        ),
        (
            [check_block("c", "valid_json", 3)],
            ("blocks", 0, "value"),
            "valid_json takes no value",
        ),
        (
            [{**branches_block("p", {"a": [model_block("m")]}), "planner": "Plan."}],
            ("blocks", 0, "planner"),
            "not used in branches mode",
        ),
        (
            [{**per_item_block("p", [model_block("m")]), "body": None}],
            ("blocks", 0, "body"),
            "required in per_item mode",
        ),
        (
            [loop_block("l", [model_block("m")], exit="judge")],
            ("blocks", 0, "judge"),
            "a judge exit needs a judge prompt",
        ),
        (
            [loop_block("l", [model_block("m")], exit="check", check={"rule": "contains"})],
            ("blocks", 0, "check", "value"),
            "contains needs a text of 1 to 300 characters",
        ),
    ],
)
def test_rules_across_fields(
    blocks: list[BlockDict], loc: tuple[str | int, ...], message: str
) -> None:
    assert (loc, message) in layout(*blocks)


@pytest.mark.parametrize(
    ("blocks", "loc", "message"),
    [
        (
            [model_block("a", message="{b}"), model_block("b")],
            ("blocks", 0, "message"),
            "{b} is not available here",
        ),
        (
            [model_block("a", system="Use {nothing}.")],
            ("blocks", 0, "system"),
            "unknown reference {nothing}",
        ),
        (
            [model_block("a", message="{feedback}")],
            ("blocks", 0, "message"),
            "{feedback} is not available here",
        ),
        (
            [model_block("a", message="{item}")],
            ("blocks", 0, "message"),
            "{item} is not available here",
        ),
        (
            [
                router_block("r", {"x": [model_block("inner")], "y": [model_block("o")]}),
                model_block("after", message="{inner}"),
            ],
            ("blocks", 1, "message"),
            "{inner} is not available here",
        ),
        (
            [
                branches_block(
                    "p", {"a": [model_block("ma")], "b": [model_block("mb", message="{ma}")]}
                )
            ],
            ("blocks", 0, "branches", 1, "blocks", 0, "message"),
            "{ma} is not available here",
        ),
        (
            [tool_block("t", expression="{later}"), model_block("later")],
            ("blocks", 0, "arguments", "expression"),
            "{later} is not available here",
        ),
    ],
)
def test_reference_errors(
    blocks: list[BlockDict], loc: tuple[str | int, ...], message: str
) -> None:
    assert (loc, message) in layout(*blocks)


def test_references_allowed() -> None:
    assert (
        layout(
            model_block("first"),
            router_block(
                "r",
                {
                    "x": [model_block("in-route", message="{first} {previous} {input}")],
                    "y": [model_block("o")],
                },
            ),
            model_block("after", message="{r} {first}"),  # the router's own output, not its insides
            loop_block(
                "l",
                [model_block("gen", message="{feedback} {r}")],
                exit="judge",
                judge="Is {gen} good?",
            ),
            per_item_block("p", [model_block("w", message="{item} {l}")]),
            model_block(
                "json", system='Reply as {"answer": 1}.'
            ),  # braces that are not names are text
        )
        == []
    )


def test_at_most_30_blocks() -> None:
    assert layout(*(model_block(f"b{i}") for i in range(30))) == []
    assert (("blocks",), "at most 30 blocks, got 31") in layout(
        *(model_block(f"b{i}") for i in range(31))
    )


def test_nesting_at_most_three_levels() -> None:
    three = branches_block("p", {"a": [loop_block("l", [model_block("m")])]})
    assert layout(three) == []
    four = branches_block("p", {"a": [loop_block("l", [loop_block("inner", [model_block("m")])])]})
    assert (
        ("blocks", 0, "branches", 0, "blocks", 0, "body", 0, "kind"),
        "nesting is limited to 3 levels",
    ) in layout(four)


def test_a_model_call_block_offers_up_to_six_tools() -> None:
    six = [f"s/t{i}" for i in range(6)]
    blocks_config(model_block("a", tools=six))
    assert ("blocks", 0, "model", "tools") in field_error_locs(
        model_block("a", tools=[*six, "s/t6"])
    )


def test_server_tools_are_checked_when_called() -> None:
    assert layout(tool_block("t", tool="notes/write_note", title="n", text="hi")) == []
    assert layout(tool_block("t", tool="lab/calculator", x="1")) == [
        (("blocks", 0, "arguments"), "arguments must be exactly: expression")
    ]
