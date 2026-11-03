"""What a villager can do where it stands (FR-004, FR-008)."""

import json
from typing import Any

from agent_lab.village.affordances import MOST, can_do, can_do_lines
from agent_lab.village.evals.fixtures import build_world
from agent_lab.village.turn import parse_action


def world_of(**fixture: Any) -> dict[str, Any]:
    return build_world({"day": 20, "time": "10:00"} | fixture)


def actions(world: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [action for action, _ in can_do(world, name)]


def test_work_where_there_is_work_and_nowhere_else() -> None:
    world = world_of(
        growth={"fields": "growing"},
        villagers={"Greta": {"at": "fields"}, "Lina": {"at": "market"}},
    )
    assert can_do(world, "Greta")[0] == (
        {"action": "work"},
        "you can work the fields here; an hour of work tends them",
    )
    assert actions(world, "Lina") == []


def test_work_says_what_an_hour_fills() -> None:
    world = world_of(villagers={"Jonas": {"at": "pier"}})
    assert can_do(world, "Jonas") == [
        ({"action": "work"}, "you can work the pier here; an hour of work fills a basket of fish")
    ]


def test_build_at_or_away_from_a_site_holding_loads() -> None:
    world = world_of(
        project={"key": "trees_square", "site": {"saplings": 2}},
        villagers={"Greta": {"at": "fields"}, "Lina": {"at": "site"}},
    )
    assert can_do(world, "Lina") == [({"action": "build"}, "the building site holds 2 saplings")]
    assert ({"action": "build"}, "the building site holds 2 saplings") in can_do(world, "Greta")


def test_bring_a_needed_load_and_set_it_down_at_the_site() -> None:
    world = world_of(
        project={"key": "trees_square"},
        villagers={"Jonas": {"at": "market", "carrying": "saplings"}},
    )
    assert can_do(world, "Jonas") == [
        ({"action": "bring"}, "the building site still needs the saplings you carry")
    ]
    world["villagers"][1] |= {"x": 18, "y": 10}  # on the site
    assert can_do(world, "Jonas") == [
        ({"action": "build"}, "you can set down your saplings and build with them"),
        ({"action": "bring"}, "the building site still needs the saplings you carry"),
        ({"action": "give"}, "set down your load of saplings at the building site"),
    ]


def test_buy_what_the_trader_has_and_the_project_needs() -> None:
    world = world_of(
        project={"key": "market_stand"},  # needs wood and paint
        trader={"wood": 2, "paint": 0, "saplings": 1},
        villagers={"Greta": {"at": "market", "carrying": "vegetables"}},
    )
    assert can_do(world, "Greta") == [
        ({"action": "buy", "goods": "wood"}, "trade your basket for a load; the trader has 2 left"),
    ]
    world["project"] = None  # nothing to build: no reason to buy
    assert can_do(world, "Greta") == []


def test_give_onto_the_stalls_on_the_square() -> None:
    world = world_of(villagers={"Jonas": {"at": "square", "carrying": "fish"}})
    assert can_do(world, "Jonas") == [
        ({"action": "give"}, "the festival stalls still lack fish: set yours out now")
    ]
    world["stalls"]["fish"] = 1
    assert can_do(world, "Jonas") == [
        ({"action": "give"}, "set out your fish on the festival stalls")
    ]


def test_say_to_each_awake_villager_next_to_you() -> None:
    world = world_of(
        villagers={"Lina": {"at": [22, 7]}, "Hilde": {"at": [23, 7]}, "Jonas": {"at": [21, 7]}},
        conversations=[],
    )
    assert can_do(world, "Lina") == [
        ({"action": "say", "to": "Hilde", "text": "…"}, "Hilde is next to you"),
        ({"action": "say", "to": "Jonas", "text": "…"}, "Jonas is next to you"),
    ]
    world["talked_out"] = [["Hilde", "Lina"]]
    assert actions(world, "Lina") == [{"action": "say", "to": "Jonas", "text": "…"}]


def test_six_entries_in_order() -> None:
    world = world_of(
        project={"key": "market_stand", "site": {"wood": 1}},  # its site is the market
        trader={"wood": 2, "paint": 2, "saplings": 2},
        villagers={
            "Greta": {"at": [23, 8], "carrying": "vegetables"},
            "Hilde": {"at": [24, 8]},
            "Jonas": {"at": [23, 9]},
            "Lina": {"at": [22, 8]},
        },
    )
    kinds = [(a["action"], a.get("goods") or a.get("to")) for a in actions(world, "Greta")]
    assert len(kinds) == MOST == 6
    assert kinds == [
        ("build", None),
        ("buy", "wood"),
        ("buy", "paint"),
        ("say", "Hilde"),
        ("say", "Jonas"),
        ("say", "Lina"),
    ]


def test_every_listed_answer_is_accepted() -> None:
    worlds = [
        (world_of(villagers={"Greta": {"at": "fields"}}), "Greta"),
        (world_of(villagers={"Jonas": {"at": "pier"}}), "Jonas"),
        (world_of(villagers={"Jonas": {"at": "square", "carrying": "fish"}}), "Jonas"),
        (
            world_of(
                project={"key": "trees_square", "site": {"saplings": 1}},
                villagers={"Jonas": {"at": "site", "carrying": "saplings"}},
            ),
            "Jonas",
        ),
        (
            world_of(
                project={"key": "trees_square"},
                villagers={"Jonas": {"at": "market", "carrying": "saplings"}},
            ),
            "Jonas",
        ),
        (
            world_of(
                project={"key": "boat"},
                trader=True,
                villagers={
                    "Greta": {"at": "market", "carrying": "vegetables"},
                    "Lina": {"at": [23, 8]},
                },
            ),
            "Greta",
        ),
    ]
    for world, name in worlds:
        listed = actions(world, name)
        assert listed
        for action in listed:
            answer = action | (
                {"text": "Hello there"} if action["action"] in ("say", "goodbye") else {}
            )
            assert parse_action(json.dumps(answer), world, name)[1] is None, action


def test_the_lines() -> None:
    world = world_of(villagers={"Jonas": {"at": "pier"}})
    assert can_do_lines(world, "Jonas") == [
        "What you can do here:",
        '- {"action": "work"}: you can work the pier here; an hour of work fills a basket of fish',
    ]
    lina = world_of(villagers={"Lina": {"at": "market"}})
    assert can_do_lines(lina, "Lina") == [
        "What you can do here:",
        "- nothing here; walk somewhere with move, or find someone",
    ]


def test_a_talker_due_elsewhere_by_its_plan_is_offered_to_leave() -> None:
    plan = [
        {"time": "10:00", "place": "market", "purpose": "sell flowers"},
        {"time": "11:00", "place": "flower garden", "purpose": "water the beds"},
    ]
    world = world_of(
        time="10:40",
        villagers={"Lina": {"at": [23, 7], "plan": plan}, "Jonas": {"at": [22, 7]}},
        conversations=[["Jonas", "Lina", 4]],
    )
    leave = (
        {"action": "goodbye", "place": "flower garden"},
        "your plan has you at the flower garden at 11:00",
    )
    assert leave in can_do(world, "Lina")
    world["tick"] -= 2  # 10:20: not yet due
    assert leave not in can_do(world, "Lina")
    world["tick"] += 2
    world["conversations"] = []  # not talking: it simply goes
    assert leave not in can_do(world, "Lina")


def test_a_plan_to_see_someone_offers_to_find_them() -> None:
    plan = [
        {"time": "07:00", "place": "flower garden", "purpose": "water"},
        {"time": "11:00", "villager": "Greta", "purpose": "ask for seeds"},
    ]
    world = world_of(
        time="11:00",
        villagers={"Lina": {"at": "flower garden", "plan": plan}, "Greta": {"at": "fields"}},
    )
    see = ({"action": "find", "villager": "Greta"}, "your plan has you see Greta at 11:00")
    assert see in can_do(world, "Lina")
    world["villagers"][2] |= {"x": world["villagers"][3]["x"] + 1, "y": world["villagers"][3]["y"]}
    assert see not in can_do(world, "Lina")  # next to her: say it
    world["villagers"][2] |= {"x": 1, "y": 14}
    world["conversations"] = [{"a": "Lina", "b": "Jonas", "lines": 2, "last_tick": 0}]
    assert (
        {"action": "goodbye", "villager": "Greta"},
        "your plan has you see Greta at 11:00",
    ) in can_do(world, "Lina")


# --- M15: happenings (FR-003) ---


def test_lead_mend_and_the_peddlers_curiosity() -> None:
    world = world_of(
        villagers={"Jonas": {"at": "pier"}, "Lina": {"at": "square", "carrying": "flowers"}}
    )
    jonas, lina = world["villagers"][1], world["villagers"][3]
    world["happenings"] = [
        {
            "kind": "repair",
            "place": "pier",
            "state": "here",
            "details": {"text": "the boards of the pier"},
            "work": 0,
            "cell": [jonas["x"], jonas["y"]],
            "concerns": None,
            "leader": None,
        },
        {
            "kind": "animal",
            "place": "pier",
            "state": "here",
            "details": {"text": "Greta's goat"},
            "cell": [jonas["x"] + 1, jonas["y"]],
            "concerns": "Greta",
            "leader": None,
        },
        {
            "kind": "peddler",
            "place": "square",
            "state": "here",
            "details": {"text": "a peddler with a kite", "goods": "a kite"},
            "cell": [lina["x"] + 1, lina["y"]],
            "concerns": None,
            "leader": None,
        },
    ]
    assert can_do(world, "Jonas")[:2] == [
        ({"action": "work"}, "mend the boards of the pier: an hour of work there"),
        ({"action": "lead"}, "Greta's goat is next to you; take it home to Greta"),
    ]
    assert (
        {"action": "buy", "goods": "a kite"},
        "the peddler trades a kite for your basket",
    ) in can_do(world, "Lina")
    for name in ("Jonas", "Lina"):
        for action in actions(world, name):
            answer = action | (
                {"text": "Hello there"} if action["action"] in ("say", "goodbye") else {}
            )
            assert parse_action(json.dumps(answer), world, name)[1] is None, action


def test_row_at_the_pier_once_there_is_a_boat() -> None:
    world = world_of(built=["boat"], villagers={"Jonas": {"at": "pier"}, "Greta": {"at": [21, 17]}})
    assert (
        {"action": "row", "with": "Greta"},
        "take the boat out on the lake with Greta",
    ) in can_do(world, "Jonas")
    assert ({"action": "row"}, "take the boat out on the lake") in can_do(world, "Jonas")
    no_boat = world_of(villagers={"Jonas": {"at": "pier"}})
    assert all(a["action"] != "row" for a in actions(no_boat, "Jonas"))
