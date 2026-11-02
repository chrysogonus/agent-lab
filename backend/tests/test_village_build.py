"""The building catalogue, the sites and building work (FR-010 to FR-013, SC-002)."""

import json
from typing import Any

import pytest

from agent_lab.village.build import (
    CATALOGUE,
    build_step,
    buildable,
    built_text,
    entry,
    needs_left,
    new_project,
    project_named,
    project_text,
    site_at,
    site_cells,
    site_refusal,
)
from agent_lab.village.world import ROWS, new_world, walkable

LONGEST_DAY_HOURS = 16  # Jonas 05:00-21:00, Greta 05:30-21:30


def test_the_catalogue() -> None:
    keys = [e.key for e in CATALOGUE]
    assert len(keys) == len(set(keys)) == 10
    kinds = {e.kind for e in CATALOGUE}
    assert kinds == {"paint", "trees", "stand", "building", "boat"}
    for e in CATALOGUE:
        assert e.site and all(walkable(x, y) for x, y in e.site), e.key
        assert e.at and e.needs and all(n > 0 for n in e.needs.values()), e.key
        assert set(e.needs) <= {"wood", "paint", "saplings"}
        assert e.done_text.endswith(".")
    assert entry("bakehouse").needs == {"wood": 14, "paint": 3}
    assert entry("barn").needs == {"wood": 16, "paint": 3}


def test_a_building_takes_more_than_a_waking_day_of_one_villagers_work() -> None:
    for e in CATALOGUE:
        if e.kind == "building":
            assert sum(e.needs.values()) > LONGEST_DAY_HOURS, e.key  # one load is one hour


def test_buildings_stand_on_their_plots() -> None:
    assert {ROWS[y][x] for x, y in entry("bakehouse").at} == {"b"}
    assert {ROWS[y][x] for x, y in entry("barn").at} == {"r"}


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("A market stand", "market_stand"),
        ("market stand", "market_stand"),
        ("the Market Stand", "market_stand"),
        ("Paint the town hall", "paint_town_hall"),
        ("paint_lina", "paint_lina"),
        ("  A rowing boat ", "boat"),
        ("a castle", None),
        ("", None),
    ],
)
def test_project_named(text: str, key: str | None) -> None:
    assert project_named(text) == key


def test_buildable_skips_what_is_built_and_what_is_being_built() -> None:
    world = new_world()
    assert [e.key for e in buildable(world)] == [e.key for e in CATALOGUE]
    world["built"] = [{"key": "paint_town_hall", "day": 3}]
    world["project"] = new_project("boat", 6)
    keys = [e.key for e in buildable(world)]
    assert "paint_town_hall" not in keys and "boat" not in keys and len(keys) == 8


def test_new_project() -> None:
    assert new_project("market_stand", 9) == {
        "key": "market_stand",
        "site": {"wood": 0, "paint": 0, "saplings": 0},
        "used": {"wood": 0, "paint": 0, "saplings": 0},
        "work": 0,
        "tasks": [],
        "day": 9,
    }


def test_built_text() -> None:
    world = new_world()
    assert built_text(world) is None
    world["built"] = [{"key": "paint_town_hall", "day": 3}, {"key": "boat", "day": 9}]
    assert built_text(world) == (
        "Built so far: The town hall has been painted. A rowing boat lies at the pier."
    )


def building(world: dict[str, Any], key: str, **changes: Any) -> dict[str, Any]:
    world["project"] = new_project(key, 3) | changes
    return world["project"]


def test_needs_left_counts_what_lies_on_the_site_and_what_was_used() -> None:
    world = new_world()
    building(world, "market_stand")  # 3 wood, 1 paint
    assert needs_left(world) == {"wood": 3, "paint": 1}
    world["project"]["site"]["paint"] = 1
    world["project"]["used"]["wood"] = 2
    assert needs_left(world) == {"wood": 1}
    world["project"] = None
    assert needs_left(world) == {}


def test_project_text() -> None:
    world = new_world()
    assert project_text(world, "Greta") == []
    tasks = [
        {"task": "buy", "goods": "paint", "villagers": ["Greta", "Lina"]},
        {"task": "build", "goods": None, "villagers": ["Greta"]},
    ]
    building(world, "paint_lina", tasks=tasks)
    world["project"]["site"]["paint"] = 1
    world["built"] = [{"key": "boat", "day": 2}]
    assert project_text(world, "Greta") == [
        "The village is building: Paint Lina's house (the building site is in front of Lina's "
        "house). It still needs 1 paint; the site holds 1 paint; 0 of 2 loads worked in.",
        "Hilde asked you to: buy paint from the trader; build at the building site.",
        "The building site (in front of Lina's house) holds 1 paint waiting to be built with: go "
        'and build ({"action": "move", "place": "building site"}, then {"action": "work"}).',
        "Built so far: A rowing boat lies at the pier.",
    ]
    assert project_text(world, "Jonas")[1] == "Nothing is asked of you; you may still help."
    world["project"]["tasks"] = []
    assert project_text(world, "Jonas")[1] == "Hilde has not handed out the work yet."
    world["project"]["tasks"] = [{"task": "build", "goods": None, "villagers": ["Hilde"]}]
    assert project_text(world, "Hilde")[1] == "You took on: build at the building site."


def test_every_project_says_where_its_site_is() -> None:
    assert all(p.where.startswith(("at ", "in front of ", "by ", "on ")) for p in CATALOGUE)


def site_world(key: str = "market_stand", **site: int) -> dict[str, Any]:
    world = new_world()
    world["tick"] = 30
    for v in world["villagers"]:
        v["asleep"] = False
    project = building(world, key)
    project["site"] |= site
    return world


def work_at_site(world: dict[str, Any], *names: str) -> None:
    cells = entry(world["project"]["key"]).site
    for i, v in enumerate(v for v in world["villagers"] if v["name"] in names):
        v |= {"x": cells[i % len(cells)][0], "y": cells[i % len(cells)][1]}
        v["working"] = {"place": "site", "steps": 0}


def test_the_site_of_the_current_project() -> None:
    world = new_world()
    assert site_cells(world) == [] and not site_at(world, (14, 12))
    building(world, "bakehouse")
    assert site_cells(world) == [(14, 12), (15, 12), (16, 12)]
    assert site_at(world, (15, 12)) and not site_at(world, (15, 11))


def test_site_refusals() -> None:
    world = site_world(wood=3)  # the stand: 3 wood, 1 paint
    assert site_refusal(world, "saplings") == "the building site does not need saplings"
    assert site_refusal(world, "wood") == "the building site has all the wood it needs"
    assert site_refusal(world, "paint") is None


def test_two_workers_work_in_a_load_in_three_steps() -> None:
    world = site_world(wood=2)
    work_at_site(world, "Greta", "Lina")
    assert [build_step(world) for _ in range(3)] == [None, None, None]
    project = world["project"]
    assert project["site"]["wood"] == 1 and project["used"]["wood"] == 1 and project["work"] == 0


def test_no_loads_no_progress() -> None:
    world = site_world()
    work_at_site(world, "Greta")
    for _ in range(10):
        assert build_step(world) is None
    assert world["project"]["work"] == 0 and world["project"]["used"]["wood"] == 0


def test_loads_in_any_order_and_across_a_reload() -> None:
    world = site_world(paint=1)  # paint first
    work_at_site(world, "Greta")
    for _ in range(6):
        build_step(world)
    assert world["project"]["used"] == {"wood": 0, "paint": 1, "saplings": 0}
    assert needs_left(world) == {"wood": 3}
    world = json.loads(json.dumps(world))  # saved and loaded again
    assert needs_left(world) == {"wood": 3}
    assert site_refusal(world, "paint") == "the building site has all the paint it needs"


def test_a_fully_stocked_bakehouse_takes_one_worker_more_than_a_day() -> None:
    world = site_world("bakehouse", wood=14, paint=3)
    work_at_site(world, "Jonas")
    day = 16 * 6  # Jonas's waking day in steps
    assert [build_step(world) for _ in range(day)].count("bakehouse") == 0
    finished = [build_step(world) for _ in range(6)]
    assert finished == [None] * 5 + ["bakehouse"]
    assert world["project"]["used"] == {"wood": 14, "paint": 3, "saplings": 0}


def test_sleepers_and_others_do_not_build() -> None:
    world = site_world(wood=1)
    work_at_site(world, "Greta")
    next(v for v in world["villagers"] if v["name"] == "Greta")["asleep"] = True
    for _ in range(6):
        build_step(world)
    assert world["project"]["used"]["wood"] == 0


def test_a_carried_load_is_meant_for_the_building_site() -> None:
    world = site_world()  # the market stand, its site the market
    jonas = next(v for v in world["villagers"] if v["name"] == "Jonas")
    jonas["basket"] = "wood"
    lines = project_text(world, "Jonas")
    assert (
        "Take your load of wood to the building site (at the market) and set it down there: "
        '{"action": "move", "place": "building site"}, then {"action": "give"}.'
    ) in lines
    jonas |= {"x": entry("market_stand").site[0][0], "y": entry("market_stand").site[0][1]}
    assert (
        'You are at the building site: set down your load of wood now with {"action": "give"}.'
        in project_text(world, "Jonas")
    )
    jonas["basket"] = "saplings"  # not needed: no hint
    assert not any("saplings" in line for line in project_text(world, "Jonas"))


def test_loads_at_the_site_ask_whoever_stands_there_to_build() -> None:
    world = site_world(wood=2)
    greta = next(v for v in world["villagers"] if v["name"] == "Greta")
    greta |= {"x": entry("market_stand").site[0][0], "y": entry("market_stand").site[0][1]}
    assert 'The building site holds 2 wood: build here with {"action": "work"}.' in project_text(
        world, "Greta"
    )
    greta["working"] = {"place": "site", "steps": 0}
    assert not any("build here" in line for line in project_text(world, "Greta"))


def test_with_nothing_to_build_with_a_basket_is_pointed_to_the_trader() -> None:
    world = site_world("trees_square")  # needs 3 saplings, the site holds nothing
    greta = next(v for v in world["villagers"] if v["name"] == "Greta")
    greta["basket"] = "flowers"
    hint = (
        "Nothing can be built until someone buys saplings: trade your basket for a load at the "
        'market while the trader is there ({"action": "buy", "goods": "saplings"}).'
    )
    assert hint in project_text(world, "Greta")
    greta["basket"] = None
    assert hint not in project_text(world, "Greta")
    greta["basket"] = "flowers"
    world["project"]["site"]["saplings"] = 1  # something to build with
    assert hint not in project_text(world, "Greta")


def test_loads_waiting_at_the_site_call_the_others_to_build() -> None:
    world = site_world("trees_square", saplings=2)
    hint = (
        "The building site (by the square, east of it) holds 2 saplings waiting to be built "
        'with: go and build ({"action": "move", "place": "building site"}, then '
        '{"action": "work"}).'
    )
    assert hint in project_text(world, "Jonas")  # at his door, far from the site
    jonas = next(v for v in world["villagers"] if v["name"] == "Jonas")
    jonas |= {"x": 18, "y": 10}  # at the site: told to build here instead
    assert hint not in project_text(world, "Jonas")
    assert any("build here" in line for line in project_text(world, "Jonas"))
