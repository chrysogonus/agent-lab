"""The building catalogue, the sites and building work (FR-010 to FR-013, SC-002)."""

import pytest

from agent_lab.village.build import (
    CATALOGUE,
    buildable,
    built_text,
    entry,
    new_project,
    project_named,
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
