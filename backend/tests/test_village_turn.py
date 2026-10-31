"""Observations, actions and the villager agents (FR-004 to FR-008)."""

import json
from typing import Any

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.turn import observation, parse_action, villager_agent
from agent_lab.village.world import VILLAGERS, label_cell, new_world, steps_between


def world_with(**changes: Any) -> dict[str, Any]:
    world = new_world()
    for v in world["villagers"]:
        v.update(changes.get(v["name"], {}))
    return world


def test_observation() -> None:
    market = label_cell("market")
    world = world_with(
        Hilde={"x": market[0], "y": market[1]},
        Jonas={
            "x": market[0] + 1,
            "y": market[1],
            "inbox": [
                {"from": "Hilde", "to": "Jonas", "text": "Fish for the festival?", "tick": 3},
                {"from": "Greta", "to": "Lina", "text": "Rain later.", "tick": 3},
                {"from": "Lina", "to": None, "text": "Hello all!", "tick": 3},
            ],
            "events": [{"tick": 2, "kind": "arrived", "text": "You arrived at the market."}],
        },
    )
    world["tick"] = 4
    text = observation(world, "Jonas")
    assert text.startswith("Day 1, 06:40, morning. You are at the market.")
    assert "Nearby: Mayor Hilde." in text
    places = text.split("Places: ")[1].split("\n")[0]
    steps = steps_between(market[0] + 1, market[1], "town_hall")
    assert f"town hall {steps} steps" in places and "market" not in places
    assert '- Hilde to you: "Fish for the festival?"' in text
    assert '- Greta to Lina: "Rain later."' in text
    assert '- Lina: "Hello all!"' in text
    assert "- 06:20 You arrived at the market." in text
    assert text.endswith("What do you do? Answer with one JSON object.")


def test_observation_on_the_way() -> None:
    world = world_with(Hilde={"x": 4, "y": 1, "destination": "square"})
    assert "You are on the way to the square." in observation(world, "Hilde")
    assert "Nearby: nobody." in observation(world, "Hilde")


@pytest.mark.parametrize(
    ("answer", "action"),
    [
        ('{"action": "move", "place": "market"}', {"action": "move", "place": "market"}),
        (
            '{"action": "move", "place": "the Flower Garden"}',
            {"action": "move", "place": "flower_garden"},
        ),
        (
            '{"action": "say", "text": " Hi! ", "to": "jonas"}',
            {"action": "say", "text": "Hi!", "to": "Jonas"},
        ),
        ('{"action": "say", "text": "Hi all"}', {"action": "say", "text": "Hi all", "to": None}),
        ('{"action": "wait"}', {"action": "wait"}),
    ],
)
def test_valid_actions(answer: str, action: dict[str, Any]) -> None:
    assert parse_action(answer, new_world(), "Hilde") == (action, None)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "no answer"),
        ("I will go fishing.", "the answer is not JSON"),
        ('{"action": "dance"}', "not a valid action"),
        ('{"action": "move"}', "not a valid action"),
        ('{"action": "move", "place": "harbour"}', "unknown place 'harbour'"),
        ('{"action": "move", "place": "town hall"}', "already at the town hall"),
        ('{"action": "say", "text": "   "}', "nothing to say"),
        ('{"action": "say", "text": "Hi", "to": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "say", "text": "Hi", "to": "Hilde"}', "unknown villager 'Hilde'"),
    ],
)
def test_invalid_answers_become_wait(answer: str | None, reason: str) -> None:
    action, why = parse_action(answer, new_world(), "Hilde")
    assert action == {"action": "wait"}
    assert why is not None and why.startswith(reason)


@pytest.mark.parametrize("name", list(VILLAGERS))
def test_villager_agents_are_valid_block_agents(name: str) -> None:
    body = villager_agent(name)
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    decide, check = config.blocks
    assert decide.kind == "model" and VILLAGERS[name].persona in decide.system
    assert '{"action": "wait"}' in decide.system
    assert check.kind == "check" and check.rule == "valid_json"
    assert body["name"] == VILLAGERS[name].title
    assert json.loads('{"action": "wait"}')  # the example in the rules is valid JSON
