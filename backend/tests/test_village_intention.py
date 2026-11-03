"""Intentions and their steps (FR-001 to FR-003)."""

from typing import Any

from agent_lab.village.evals.fixtures import build_world
from agent_lab.village.intention import (
    KINDS,
    described,
    ended_text,
    intention_text,
    next_step,
    start,
    started_text,
)
from agent_lab.village.world import door, place_cells


def world_of(**villagers: Any) -> dict[str, Any]:
    return build_world({"day": 20, "time": "09:30", "villagers": villagers})


def building(site: dict[str, int] | None = None, **villagers: Any) -> dict[str, Any]:
    fixture = {
        "day": 20,
        "time": "09:30",
        "project": {"key": "trees_square", "site": site or {}},
        "villagers": villagers,
    }
    return build_world(fixture)


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def set_on(world: dict[str, Any], name: str, action: dict[str, Any]) -> dict[str, Any]:
    v = villager(world, name)
    v["intention"] = start(world, name, action)
    return v


def test_the_kinds() -> None:
    assert KINDS == ("go", "work", "build", "bring", "see", "lead", "row")


def test_start_turns_each_answer_into_an_intention() -> None:
    world = building(Greta={"at": "fields"})
    world["tick"] += 1
    work = start(
        world, "Greta", {"action": "work", "place": None, "until": 720, "purpose": " weed "}
    )
    assert work == {
        "kind": "work",
        "place": "fields",
        "villager": None,
        "until": 720,
        "purpose": "weed",
        "since": world["tick"],
        "say": None,
    }
    assert start(world, "Greta", {"action": "move", "place": "pier"})["kind"] == "go"
    assert start(world, "Greta", {"action": "build"})["place"] == "site"
    assert start(world, "Greta", {"action": "bring"})["kind"] == "bring"
    see = start(world, "Greta", {"action": "find", "villager": "Jonas", "say": "Fish?"})
    assert (see["kind"], see["villager"], see["say"], see["place"]) == (
        "see",
        "Jonas",
        "Fish?",
        None,
    )
    assert start(world, "Greta", {"action": "work", "purpose": "x" * 300})["purpose"] == "x" * 120


def test_go_walks_and_is_done_on_arrival() -> None:
    world = world_of(Greta={"at": "fields"})
    v = set_on(world, "Greta", {"action": "move", "place": "market"})
    assert next_step(world, v) == {"kind": "walk", "goal": {"kind": "place", "place": "market"}}
    v["x"], v["y"] = place_cells("market")[0]
    assert next_step(world, v) == {"kind": "done", "why": "you arrived at the market"}
    home = set_on(world, "Greta", {"action": "move", "place": "home"})
    assert next_step(world, home)["goal"] == {"kind": "home"}


def test_work_walks_there_starts_and_keeps_at_it_until_the_time() -> None:
    world = world_of(Greta={"at": "market"})
    v = set_on(world, "Greta", {"action": "work", "place": "fields", "until": 12 * 60})
    assert next_step(world, v)["kind"] == "walk"
    v["x"], v["y"] = place_cells("fields")[0]
    assert next_step(world, v) == {"kind": "start_work", "place": "fields"}
    v["working"] = {"place": "fields", "steps": 0}
    assert next_step(world, v) == {"kind": "none"}
    world["tick"] += (12 * 60 - (9 * 60 + 30)) // 10  # noon
    assert next_step(world, v) == {"kind": "done", "why": "it is 12:00"}


def test_work_where_nobody_may_work_is_given_up() -> None:
    world = world_of(Greta={"at": "pier"})
    v = set_on(world, "Greta", {"action": "work", "place": "pier"})
    step = next_step(world, v)
    assert step["kind"] == "given_up" and "only Jonas fishes here" in step["why"]


def test_build_walks_to_the_site_sets_down_a_needed_load_then_builds() -> None:
    world = building({"saplings": 1}, Greta={"at": "fields", "carrying": "saplings"})
    v = set_on(world, "Greta", {"action": "build", "until": 15 * 60})
    assert next_step(world, v) == {"kind": "walk", "goal": {"kind": "place", "place": "site"}}
    v["x"], v["y"] = 18, 10  # on the site
    assert next_step(world, v) == {"kind": "set_down", "goods": "saplings"}
    v["basket"] = None
    world["project"]["site"]["saplings"] += 1
    assert next_step(world, v) == {"kind": "start_work", "place": "site"}
    v["working"] = {"place": "site", "steps": 0}
    assert next_step(world, v) == {"kind": "none"}


def test_build_ends_when_nothing_is_left_to_build_with_or_the_project_is_gone() -> None:
    world = building({}, Greta={"at": "site", "working": "site"})
    v = set_on(world, "Greta", {"action": "build"})
    assert next_step(world, v) == {
        "kind": "given_up",
        "why": "the building site holds nothing to build with",
    }
    world["project"] = None
    assert next_step(world, v) == {"kind": "given_up", "why": "nothing is being built any more"}


def test_bring_walks_to_the_site_and_sets_the_load_down_then_is_done() -> None:
    world = building({}, Jonas={"at": "market", "carrying": "saplings"})
    v = set_on(world, "Jonas", {"action": "bring"})
    assert next_step(world, v)["kind"] == "walk"
    v["x"], v["y"] = 20, 10
    assert next_step(world, v) == {
        "kind": "set_down",
        "goods": "saplings",
        "done": "you set down the saplings",
    }
    v["basket"] = None
    assert next_step(world, v) == {"kind": "given_up", "why": "your hands are empty"}
    v["basket"] = "wood"
    assert next_step(world, v) == {"kind": "given_up", "why": "the site needs no more wood"}


def test_see_follows_says_the_line_and_ends() -> None:
    world = world_of(Greta={"at": "market"}, Jonas={"at": [26, 10]})
    v = set_on(world, "Greta", {"action": "find", "villager": "Jonas", "say": "Any fish?"})
    assert next_step(world, v) == {
        "kind": "walk",
        "goal": {"kind": "find", "villager": "Jonas"},
        "seen": True,
    }
    v["x"], v["y"] = 25, 10
    assert next_step(world, v) == {
        "kind": "say",
        "to": "Jonas",
        "text": "Any fish?",
        "done": "you found Jonas",
    }
    v["intention"]["say"] = None
    assert next_step(world, v) == {"kind": "done", "why": "you found Jonas"}


def test_see_of_someone_out_of_sight_walks_and_gives_up_on_losing_sight() -> None:
    world = world_of(Greta={"at": "fields"}, Jonas={"at": "pier"})
    v = set_on(world, "Greta", {"action": "find", "villager": "Jonas"})
    assert next_step(world, v) == {"kind": "walk", "goal": {"kind": "find", "villager": "Jonas"}}
    v["intention"]["seen"] = True
    v["beliefs"]["Jonas"] = {"where": "market", "cell": [22, 8], "tick": 0, "source": "seen"}
    assert next_step(world, v) == {
        "kind": "given_up",
        "why": "you lost sight of Jonas at the market",
    }


def test_see_of_someone_asleep_is_given_up() -> None:
    world = world_of(Greta={"at": "fields"}, Jonas={"asleep": True})
    v = set_on(world, "Greta", {"action": "find", "villager": "Jonas"})
    assert next_step(world, v) == {"kind": "given_up", "why": "Jonas is asleep"}


def test_until_before_and_after() -> None:
    world = world_of(Greta={"at": "fields", "working": "fields"})
    v = set_on(world, "Greta", {"action": "work", "until": 9 * 60 + 40})
    assert next_step(world, v) == {"kind": "none"}
    world["tick"] += 1
    assert next_step(world, v) == {"kind": "done", "why": "it is 09:40"}


def test_the_texts() -> None:
    world = building({"saplings": 2}, Greta={"at": "fields"})
    v = set_on(
        world, "Greta", {"action": "build", "until": 15 * 60, "purpose": "to plant the trees"}
    )
    assert intention_text(world, v) == (
        "You are set on: build at the building site until 15:00 (to plant the trees). "
        "Next: walk there."
    )
    assert intention_text(world, villager(world, "Jonas")) == "You are not set on anything."
    assert started_text("Greta", v["intention"]) == (
        "Greta set out to build at the building site until 15:00 (to plant the trees)."
    )
    assert ended_text("Greta", v["intention"], "it is 15:00") == (
        "Greta is done with: build at the building site until 15:00 (to plant the trees): "
        "it is 15:00."
    )
    bring = start(world, "Greta", {"action": "bring"})
    assert described(bring, "saplings") == "take the load of saplings to the building site"
    see = start(world, "Greta", {"action": "find", "villager": "Lina", "say": "Hi"})
    assert described(see) == 'see Lina and say "Hi"'


def test_lead_walks_to_the_owners_door_and_is_done_when_the_animal_is_home() -> None:
    world = world_of(Jonas={"at": "market"}, Greta={"at": "fields"})
    goat = {"kind": "animal", "state": "here", "leader": "Jonas", "concerns": "Greta"}
    goat |= {"details": {"text": "Greta's goat"}, "cell": [0, 0]}
    world["happenings"] = [goat]
    v = set_on(world, "Jonas", {"action": "lead"})
    assert (v["intention"]["kind"], v["intention"]["villager"]) == ("lead", "Greta")
    step = next_step(world, v)
    assert step["kind"] == "walk" and step["goal"]["kind"] == "door"
    assert step["goal"]["target"] == [list(door("Greta"))]
    goat["state"] = "dealt"
    assert next_step(world, v) == {"kind": "done", "why": "Greta's goat is home"}
    goat |= {"state": "passed", "leader": None}
    assert next_step(world, v)["kind"] == "given_up"
    assert described(v["intention"]) == "take the lost animal home to Greta"


def test_row_lasts_until_the_trip_is_over() -> None:
    from agent_lab.village.boat import start_trip

    world = build_world(
        {"day": 66, "time": "14:00", "built": ["boat"], "villagers": {"Jonas": {"at": "pier"}}}
    )
    start_trip(world, "Jonas", None, None)
    v = set_on(world, "Jonas", {"action": "row"})
    assert v["intention"]["kind"] == "row" and next_step(world, v) == {"kind": "none"}
    world["boat"] = None
    assert next_step(world, v) == {"kind": "done", "why": "the boat trip is over"}
    assert described(v["intention"]) == "row the boat on the lake"
