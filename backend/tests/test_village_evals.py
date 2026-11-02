"""Fixtures, turn checks, scenarios and their results (FR-004 to FR-014, SC-005)."""

from typing import Any

import pytest

from agent_lab.village.build import entry
from agent_lab.village.evals.fixtures import FixtureError, build_world
from agent_lab.village.trade import trader_stock
from agent_lab.village.turn import observation
from agent_lab.village.world import clock, door, place_at, place_cells


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


# --- fixtures ---


def test_a_fixture_sets_the_clock_and_wakes_who_it_names() -> None:
    world = build_world({"day": 66, "time": "10:30", "villagers": {"Lina": {"at": "market"}}})
    assert clock(world["tick"])[:2] == (66, "10:30")
    lina = villager(world, "Lina")
    assert not lina["asleep"] and place_at(lina["x"], lina["y"]) == "market"
    assert lina["last_decided"] == world["tick"]
    jonas = villager(world, "Jonas")
    assert jonas["asleep"] and (jonas["x"], jonas["y"]) == door("Jonas")
    assert world["day_record"] == {"day": 66, "items": []}  # notes are kept from the start
    assert world["growth"]["flower_garden"]["stage"] == "blooming"  # summer
    assert world["born"] > 0


def test_a_fixture_with_everything() -> None:
    world = build_world(
        {
            "day": 67,
            "time": "10:00",
            "villagers": {
                "Lina": {
                    "at": "site",
                    "carrying": "saplings",
                    "working": "site",
                    "goal": "town_hall",
                    "memories": ["Hilde asked me for saplings."],
                    "learnings": ["The trader comes at nine."],
                    "inbox": [{"from": "Greta", "text": "Need help?"}],
                    "said": ["Morning!"],
                    "events": ["You arrived at the building site."],
                    "plan": [
                        {"time": "11:00", "villager": "Greta", "purpose": "Talk"},
                        {"time": "14:00", "place": "market", "purpose": "Sell"},
                    ],
                },
                "Greta": {"at": [18, 11]},
                "Hilde": {"at": "home", "asleep": True},
            },
            "conversations": [["Lina", "Greta", 2]],
            "trader": True,
            "project": {
                "key": "trees_square",
                "site": {"saplings": 1},
                "used": {"saplings": 1},
                "tasks": [{"task": "build", "goods": None, "villagers": ["Lina"]}],
            },
            "built": ["boat"],
            "meeting": {
                "kind": "vote",
                "proposals": [{"key": "barn", "reason": "Room."}],
                "votes": {"Greta": {"key": "barn", "reason": "Yes."}},
                "present": ["Greta"],
            },
            "stalls": {"fish": 1},
        }
    )
    lina = villager(world, "Lina")
    assert (lina["x"], lina["y"]) == entry("trees_square").site[0]
    assert lina["basket"] == "saplings" and lina["working"] == {"place": "site", "steps": 0}
    assert lina["goal"] == {"kind": "place", "place": "town_hall"}
    assert lina["memories"][0]["text"] == "Hilde asked me for saplings."
    assert lina["learnings"][0]["text"] == "The trader comes at nine."
    assert lina["inbox"][0] | {"tick": 0} == {
        "from": "Greta",
        "to": "Lina",
        "text": "Need help?",
        "tick": 0,
    }
    assert lina["said"] == ["Morning!"] and lina["events"][0]["text"].startswith("You arrived")
    assert [e["minute"] for e in lina["plan"]["entries"]] == [660, 840]
    assert lina["plan"]["entries"][0]["villager"] == "Greta"
    assert lina["neighbours"] == ["Greta"]  # already next to each other: no "met" on step one
    assert world["conversations"][0] | {"last_tick": 0, "transcript": []} == {
        "a": "Lina",
        "b": "Greta",
        "lines": 2,
        "last_tick": 0,
        "transcript": [],
    }
    assert world["trader"] == {"day": 67, "stock": trader_stock(67)}
    assert world["project"]["site"]["saplings"] == 1 and world["project"]["used"]["saplings"] == 1
    assert world["built"] == [{"key": "boat", "day": 66}]
    assert world["meeting"]["proposals"] == [{"key": "barn", "reason": "Room.", "run_id": None}]
    assert world["meeting"]["votes"]["Greta"]["run_id"] is None
    assert world["stalls"] == {"fish": 1, "vegetables": 0, "flowers": 0}
    facts = observation(world, "Lina")
    assert "You carry a load of saplings." in facts and "A trader is at the market" in facts
    assert "The village is building: Plant trees by the square" in facts


@pytest.mark.parametrize(
    ("fixture", "error"),
    [
        ({"day": 3, "time": "10:00", "weather": "sun"}, "unknown key 'weather'"),
        ({"day": 3, "time": "25:00"}, "bad time '25:00'"),
        ({"day": 1, "time": "03:00"}, "before the village's first morning"),
        ({"day": 3, "time": "10:00", "villagers": {"Tom": {}}}, "unknown villager 'Tom'"),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"at": "harbour"}}},
            "unknown place 'harbour'",
        ),
        ({"day": 3, "time": "10:00", "villagers": {"Lina": {"at": [0, 0]}}}, "not a walkable cell"),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"carrying": "gold"}}},
            "unknown goods 'gold'",
        ),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"at": "site"}}},
            "no project, so no building site",
        ),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"mood": "happy"}}},
            "unknown key 'mood' for Lina",
        ),
        ({"day": 3, "time": "10:00", "project": {"key": "castle"}}, "unknown project 'castle'"),
    ],
)
def test_bad_fixtures_say_what_is_wrong(fixture: dict[str, Any], error: str) -> None:
    with pytest.raises(FixtureError, match=error):
        build_world(fixture)


def test_a_cell_fixture_and_a_place_fixture_agree() -> None:
    cell = place_cells("pier")[0]
    world = build_world({"day": 2, "time": "06:00", "villagers": {"Jonas": {"at": list(cell)}}})
    assert place_at(villager(world, "Jonas")["x"], villager(world, "Jonas")["y"]) == "pier"
