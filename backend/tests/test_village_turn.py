"""Observations, actions, beliefs and the villager agents (FR-009, FR-010, FR-014 to FR-016)."""

import json
from typing import Any

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.turn import (
    belief_text,
    heard_places,
    observation,
    parse_action,
    villager_agent,
)
from agent_lab.village.world import VILLAGERS, door, label_cell, new_world, place_cells, steps_to

MARKET = label_cell("market")


def world_with(tick: int = 30, **changes: Any) -> dict[str, Any]:
    """Everyone awake at its door unless changed; tick 30 is 09:30."""
    world = new_world()
    world["tick"] = tick
    for v in world["villagers"]:
        v["asleep"] = False
        v.update(changes.get(v["name"], {}))
    return world


def at(x: int, y: int) -> dict[str, int]:
    return {"x": x, "y": y}


def test_observation() -> None:
    mx, my = MARKET
    world = world_with(
        Hilde=at(mx, my),
        Jonas={
            **at(mx + 1, my),
            "inbox": [
                {"from": "Hilde", "to": "Jonas", "text": "Fish for the festival?", "tick": 29},
                {"from": "Hilde", "to": None, "text": "Hello all!", "tick": 29},
            ],
            "events": [{"tick": 28, "kind": "arrived", "text": "You arrived at the market."}],
            "beliefs": {
                "Greta": {"where": "fields", "cell": [2, 15], "tick": 25, "source": "seen"},
                "Lina": {
                    "where": "square",
                    "cell": [12, 7],
                    "tick": 27,
                    "source": "heard",
                    "from": "Hilde",
                },
            },
        },
        Lina=at(mx + 4, my + 1),
        Greta={"asleep": True},
    )
    world["conversations"] = [{"a": "Hilde", "b": "Jonas", "lines": 2, "last_tick": 29}]
    text = observation(world, "Jonas")
    assert text.startswith("Day 1, 09:30, morning. You are at the market.")
    assert "You get up at 05:00 and go to bed at 21:00." in text
    assert "Next to you: Mayor Hilde." in text
    assert "In sight: Lina the flower girl (3 steps away)." in text
    assert "You are talking with Hilde (2 lines so far)." in text
    assert '- Hilde to you: "Fish for the festival?"' in text and '- Hilde: "Hello all!"' in text
    assert "- Greta: at the fields (seen 08:40)" in text
    assert "- Lina: at the square (heard from Hilde at 09:00)" in text
    assert "- Hilde: usually at the town hall around now (their routine)" in text
    places = text.split("Places: ")[1].split("\n")[0]
    assert f"town hall {steps_to(mx + 1, my, place_cells('town_hall'))} steps" in places
    assert "market" not in places and "your home" in places
    assert "- 09:10 You arrived at the market." in text
    assert text.endswith("What do you do? Answer with one JSON object.")


def test_observation_when_alone_and_walking() -> None:
    world = world_with(Hilde={"goal": {"kind": "find", "villager": "Lina", "target": [[1, 1]]}})
    text = observation(world, "Hilde")
    assert "You are at your home's door." in text and "You are looking for Lina." in text
    assert "Next to you: nobody." in text and "You are not talking with anyone." in text


def test_belief_from_routine_outside_waking_hours() -> None:
    world = world_with(tick=0)
    assert belief_text(world, "Jonas", "Hilde") == "at home asleep at this hour (their routine)"


@pytest.mark.parametrize(
    ("answer", "action"),
    [
        ('{"action": "move", "place": "market"}', {"action": "move", "place": "market"}),
        (
            '{"action": "move", "place": "the Flower Garden"}',
            {"action": "move", "place": "flower_garden"},
        ),
        ('{"action": "move", "place": "town hall"}', {"action": "move", "place": "town_hall"}),
        ('{"action": "find", "villager": "lina"}', {"action": "find", "villager": "Lina"}),
        (
            '{"action": "say", "text": " Hi! ", "to": "jonas"}',
            {"action": "say", "text": "Hi!", "to": "Jonas"},
        ),
        ('{"action": "say", "text": "Hi all"}', {"action": "say", "text": "Hi all", "to": None}),
        ('{"action": "goodbye", "text": "Bye!"}', {"action": "goodbye", "text": "Bye!"}),
        ('{"action": "goodbye"}', {"action": "goodbye", "text": None}),
        ('{"action": "wait"}', {"action": "wait"}),
    ],
)
def test_valid_actions(answer: str, action: dict[str, Any]) -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))  # next to Hilde
    assert parse_action(answer, world, "Hilde") == (action, None)


def test_move_home() -> None:
    world = world_with(Hilde=at(*MARKET))
    assert parse_action('{"action": "move", "place": "home"}', world, "Hilde") == (
        {"action": "move", "place": "home"},
        None,
    )


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "no answer"),
        ("I will go fishing.", "the answer is not JSON"),
        ('{"action": "dance"}', "not a valid action"),
        ('{"action": "move"}', "not a valid action"),
        ('{"action": "move", "place": "harbour"}', "unknown place 'harbour'"),
        ('{"action": "move", "place": "home"}', "already at your home"),
        ('{"action": "find", "villager": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "find", "villager": "Jonas"}', "Jonas is already next to you"),
        ('{"action": "say", "text": "   "}', "nothing to say"),
        ('{"action": "say", "text": "Hi", "to": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "say", "text": "Hi", "to": "Hilde"}', "unknown villager 'Hilde'"),
        ('{"action": "say", "text": "Hi", "to": "Lina"}', "Lina is not next to you"),
    ],
)
def test_invalid_answers_become_wait(answer: str | None, reason: str) -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))
    action, why = parse_action(answer, world, "Hilde")
    assert action == {"action": "wait"}
    assert why is not None and why.startswith(reason)


def test_speech_needs_an_awake_neighbour() -> None:
    hx, hy = door("Hilde")
    say = '{"action": "say", "text": "Hi"}'
    assert parse_action(say, world_with(), "Hilde") == ({"action": "wait"}, "nobody is next to you")
    asleep = world_with(Jonas={**at(hx + 1, hy), "asleep": True})
    assert parse_action(say, asleep, "Hilde")[1] == "nobody is next to you"
    tired = world_with(Jonas=at(hx + 1, hy))
    tired["talked_out"] = [["Hilde", "Jonas"]]
    assert parse_action(say, tired, "Hilde")[1] == (
        "you have talked a long time with Jonas; say goodbye or go on"
    )


def test_heard_places() -> None:
    assert heard_places("Lina is at the square. See you!", "Hilde", "Jonas") == {"Lina": "square"}
    assert heard_places("Greta went home.", "Hilde", "Jonas") == {"Greta": "home"}
    assert heard_places("Lina and Greta are at the market.", "Hilde", "Jonas") == {}
    assert heard_places("Jonas, meet me at the pier.", "Hilde", "Jonas") == {}  # the hearer


@pytest.mark.parametrize("name", list(VILLAGERS))
def test_villager_agents_are_valid_block_agents(name: str) -> None:
    body = villager_agent(name)
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    decide, check = config.blocks
    assert decide.kind == "model" and decide.system.startswith(VILLAGERS[name].persona)
    assert VILLAGERS[name].home in decide.system and "go to bed at" in decide.system
    for example in ('{"action": "wait"}', '{"action": "find", "villager": "Lina"}'):
        assert example in decide.system and json.loads(example)
    assert "right next to you" in decide.system
    assert check.kind == "check" and check.rule == "valid_json"
    assert body["name"] == VILLAGERS[name].title


def test_each_agent_has_only_its_own_persona() -> None:
    systems = {n: villager_agent(n)["config"]["blocks"][0]["system"] for n in VILLAGERS}
    for name, system in systems.items():
        assert all(VILLAGERS[other].persona not in system for other in VILLAGERS if other != name)


def test_observation_lists_only_the_last_ten_events() -> None:
    events = [{"tick": t, "kind": "waited", "text": f"Event {t}."} for t in range(10)]
    text = observation(world_with(Lina={"events": events}), "Lina")
    assert text.count("Event ") == 10 and "Event 0." in text
