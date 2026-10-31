"""The village map, paths, nearness and clock (FR-001, FR-003, FR-009)."""

import pytest

from agent_lab.village.world import (
    HEIGHT,
    PLACES,
    ROWS,
    VILLAGERS,
    WIDTH,
    clock,
    label_cell,
    nearby,
    new_world,
    place_at,
    place_cells,
    step_towards,
    steps_between,
    walkable,
)


def test_map_size_and_characters() -> None:
    assert (WIDTH, HEIGHT) == (20, 15)
    assert all(len(row) == WIDTH for row in ROWS)
    assert set("".join(ROWS)) <= set(".=~TSMPFG")
    assert not walkable(15, 11) and walkable(0, 0) and not walkable(-1, 0)


def test_every_place_is_reachable_from_every_other() -> None:
    for start in PLACES:
        x, y = label_cell(start)
        for goal in PLACES:
            assert steps_between(x, y, goal) >= 0  # KeyError if unreachable


def test_pier_lies_at_the_water() -> None:
    assert any(
        not walkable(x + dx, y + dy) and 0 <= y + dy < HEIGHT
        for x, y in place_cells("pier")
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    )


def test_step_towards_takes_one_walkable_step_and_arrives() -> None:
    x, y = label_cell("town_hall")
    steps = steps_between(x, y, "pier")
    for _ in range(steps):
        nx, ny = step_towards(x, y, "pier")
        assert walkable(nx, ny) and abs(nx - x) + abs(ny - y) == 1
        x, y = nx, ny
    assert place_at(x, y) == "pier"
    assert step_towards(x, y, "pier") == (x, y)  # already there


def test_nearby() -> None:
    assert nearby((1, 1), (3, 2))  # both in the town hall
    assert not nearby((1, 1), (4, 1))  # town hall and the grass next to it
    assert nearby((5, 10), (8, 12))  # outside places, 3 cells apart
    assert not nearby((4, 13), (8, 13))  # outside places, 4 cells apart


@pytest.mark.parametrize(
    ("tick", "expected"),
    [
        (0, (1, "06:00", "morning")),
        (30, (1, "11:00", "midday")),
        (144, (2, "06:00", "morning")),
        (78, (1, "19:00", "evening")),
        (114, (2, "01:00", "night")),
    ],
)
def test_clock(tick: int, expected: tuple[int, str, str]) -> None:
    assert clock(tick) == expected


def test_new_world_has_four_villagers_at_home() -> None:
    world = new_world()
    assert (world["tick"], world["running"], world["interval"]) == (0, False, 5)
    names = [v["name"] for v in world["villagers"]]
    assert names == ["Hilde", "Jonas", "Greta", "Lina"]
    assert [VILLAGERS[n].initial for n in names] == ["H", "J", "G", "L"]
    for v in world["villagers"]:
        home = VILLAGERS[v["name"]].home
        assert place_at(v["x"], v["y"]) == home
        assert (v["x"], v["y"]) != label_cell(home)  # the figure leaves the place label readable
