"""Every invalid layout is rejected at its block and field; nothing is stored (US3, SC-004)."""

from pathlib import Path
from typing import Any

import pytest
from helpers import (
    BlockDict,
    branches_block,
    check_block,
    loop_block,
    model_block,
    per_item_block,
    router_block,
    tool_block,
)
from test_blocks_api import block_agent, client_for, save

from agent_lab.store import Store

Loc = list[str | int]


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lab.db")


def deep() -> BlockDict:
    """parallel > loop > router: a container at level 3."""
    return branches_block(
        "p",
        {
            "a": [
                loop_block(
                    "l", [router_block("r", {"x": [model_block("m")], "y": [model_block("n")]})]
                )
            ]
        },
    )


CASES: list[tuple[str, list[BlockDict], Loc]] = [
    ("empty system prompt", [model_block("a", system=" ")], ["blocks", 0, "system"]),
    ("empty message", [model_block("a", message="")], ["blocks", 0, "message"]),
    ("31 blocks", [model_block(f"b{i}") for i in range(31)], ["blocks"]),
    (
        "container at level 3",
        [deep()],
        ["blocks", 0, "branches", 0, "blocks", 0, "body", 0, "kind"],
    ),
    ("duplicate block name", [model_block("a"), model_block("a")], ["blocks", 1, "name"]),
    ("reserved name input", [model_block("input")], ["blocks", 0, "name"]),
    ("unknown tool", [tool_block("t", tool="read_file")], ["blocks", 0, "tool"]),
    ("tool argument missing", [{**tool_block("t"), "arguments": {}}], ["blocks", 0, "arguments"]),
    (
        "tool argument extra",
        [tool_block("t", expression="1", other="2")],
        ["blocks", 0, "arguments"],
    ),
    ("min_bullets with text", [check_block("c", "min_bullets", "three")], ["blocks", 0, "value"]),
    (
        "router with 1 route",
        [router_block("r", {"x": [model_block("m")]})],
        ["blocks", 0, "routes"],
    ),
    (
        "router with 7 routes",
        [router_block("r", {f"r{i}": [model_block(f"m{i}")] for i in range(7)})],
        ["blocks", 0, "routes"],
    ),
    (
        "fallback not a route",
        [router_block("r", {"x": [model_block("m")], "y": [model_block("n")]}, fallback="z")],
        ["blocks", 0, "fallback"],
    ),
    (
        "empty route",
        [router_block("r", {"x": [model_block("m")], "y": []})],
        ["blocks", 0, "routes", 1, "blocks"],
    ),
    (
        "7 branches",
        [branches_block("p", {f"b{i}": [model_block(f"m{i}")] for i in range(7)})],
        ["blocks", 0, "branches"],
    ),
    (
        "branches mode with planner",
        [{**branches_block("p", {"a": [model_block("m")]}), "planner": "Plan."}],
        ["blocks", 0, "planner"],
    ),
    (
        "per-item with 0 items",
        [per_item_block("p", [model_block("m")], max_items=0)],
        ["blocks", 0, "max_items"],
    ),
    (
        "judge exit without judge",
        [loop_block("l", [model_block("m")], exit="judge")],
        ["blocks", 0, "judge"],
    ),
    ("6 rounds", [loop_block("l", [model_block("m")], max_rounds=6)], ["blocks", 0, "max_rounds"]),
    (
        "reference to a later block",
        [model_block("a", message="{b}"), model_block("b")],
        ["blocks", 0, "message"],
    ),
    (
        "reference into a route from after the router",
        [
            router_block("r", {"x": [model_block("in")], "y": [model_block("n")]}),
            model_block("after", message="{in}"),
        ],
        ["blocks", 1, "message"],
    ),
    ("feedback outside a loop", [model_block("a", message="{feedback}")], ["blocks", 0, "message"]),
    (
        "item outside a per-item body",
        [model_block("a", message="{item}")],
        ["blocks", 0, "message"],
    ),
]


@pytest.mark.parametrize(("case", "blocks", "loc"), CASES, ids=[c[0] for c in CASES])
def test_rejected_on_create_and_update(
    store: Store, case: str, blocks: list[BlockDict], loc: Loc
) -> None:
    client, _ = client_for(store)
    with client:
        kept = save(client, block_agent(model_block("kept"), name="Kept"))
        before = client.get("/agents").json()
        body = block_agent(*blocks)
        created = client.post("/agents", json=body)
        update = {k: v for k, v in body.items() if k != "template_id"}
        updated = client.put(f"/agents/{kept['id']}", json=update)
        after = client.get("/agents").json()
    for response in (created, updated):
        assert response.status_code == 422, case
        assert response.json()["detail"][0]["loc"] == ["body", "config", *loc], case
    assert after == before


@pytest.mark.parametrize("key", ["model", "provider"])
def test_model_keys_inside_config_rejected(store: Store, key: str) -> None:
    client, _ = client_for(store)
    body: dict[str, Any] = block_agent(model_block("a"))
    body["config"][key] = "x"
    with client:
        response = client.post("/agents", json=body)
    assert response.json()["detail"][0]["loc"] == ["body", "config", key]
