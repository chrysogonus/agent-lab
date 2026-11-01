"""The village map, homes, paths, nearness, clock and routines (FR-001 to FR-004, FR-014)."""

import pytest

from agent_lab.village.world import (
    HEIGHT,
    HOMES,
    PLACES,
    ROWS,
    VILLAGERS,
    WIDTH,
    adjacent,
    awake_at,
    clock,
    door,
    label_cell,
    new_world,
    place_at,
    place_cells,
    sees,
    step_towards,
    steps_to,
    usual_place,
    walkable,
)


def test_map_size_and_characters() -> None:
    assert (WIDTH, HEIGHT) == (32, 22)
    assert all(len(row) == WIDTH for row in ROWS)
    assert set("".join(ROWS)) <= set(".=~TSMPFGBhjglti")
    for char in "~Bhjglti":
        x, y = next((x, y) for y, r in enumerate(ROWS) for x, c in enumerate(r) if c == char)
        assert not walkable(x, y), char
    assert walkable(0, 1) and not walkable(-1, 0) and not walkable(0, HEIGHT)


def test_every_place_and_door_is_reachable_from_every_other() -> None:
    starts = [label_cell(p) for p in PLACES] + [door(n) for n in VILLAGERS]
    goals = [place_cells(p) for p in PLACES] + [[door(n)] for n in VILLAGERS]
    for x, y in starts:
        for goal in goals:
            assert steps_to(x, y, goal) >= 0  # KeyError if unreachable


def test_each_home_is_a_house_with_a_walkable_door_near_its_owners_work() -> None:
    for name, letter in HOMES.items():
        cells = [(x, y) for y, r in enumerate(ROWS) for x, c in enumerate(r) if c == letter]
        assert len(cells) == 6  # 3 x 2
        x, y = door(name)
        assert walkable(x, y) and (x, y - 1) in cells
        assert steps_to(x, y, place_cells(VILLAGERS[name].work)) <= 8, name


def test_pier_lies_at_the_water() -> None:
    assert any(
        0 <= y + dy < HEIGHT and ROWS[y + dy][x + dx] == "~"
        for x, y in place_cells("pier")
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    )


def test_step_towards_takes_one_walkable_step_and_arrives() -> None:
    x, y = door("Hilde")
    pier = place_cells("pier")
    for _ in range(steps_to(x, y, pier)):
        nx, ny = step_towards(x, y, pier)
        assert walkable(nx, ny) and abs(nx - x) + abs(ny - y) == 1
        x, y = nx, ny
    assert place_at(x, y) == "pier"
    assert step_towards(x, y, pier) == (x, y)  # already there
    assert step_towards(*door("Lina"), [door("Lina")]) == door("Lina")


def test_adjacent_and_sight() -> None:
    assert adjacent((3, 3), (3, 3)) and adjacent((3, 3), (4, 4)) and adjacent((3, 3), (2, 3))
    assert not adjacent((3, 3), (5, 3))
    assert sees((0, 0), (6, 3)) and not sees((0, 0), (7, 0))


@pytest.mark.parametrize(
    ("tick", "expected"),
    [
        (0, (1, "04:30", "night")),
        (3, (1, "05:00", "morning")),
        (117, (2, "00:00", "night")),
        (147, (2, "05:00", "morning")),
        (87, (1, "19:00", "evening")),
    ],
)
def test_clock(tick: int, expected: tuple[int, str, str]) -> None:
    assert clock(tick) == expected


def test_sleeping_hours_and_routines() -> None:
    hours = {n: (c.wake, c.bed) for n, c in VILLAGERS.items()}
    assert hours == {
        "Jonas": (300, 1260),
        "Greta": (330, 1290),
        "Lina": (390, 1320),
        "Hilde": (450, 1380),
    }
    assert awake_at("Jonas", 300) and not awake_at("Jonas", 299) and not awake_at("Jonas", 1260)
    assert usual_place("Jonas", 6 * 60) == "pier"
    assert usual_place("Jonas", 12 * 60) == "market"
    assert usual_place("Hilde", 6 * 60) == "home"  # still asleep
    assert usual_place("Lina", 23 * 60) == "home"


def test_new_world_has_everyone_asleep_at_home() -> None:
    world = new_world()
    assert (world["version"], world["tick"], world["running"]) == (4, 0, False)
    assert world["interval"] == 5
    assert world["conversations"] == world["talked_out"] == world["log"] == []
    names = [v["name"] for v in world["villagers"]]
    assert names == ["Hilde", "Jonas", "Greta", "Lina"]
    for v in world["villagers"]:
        assert v["asleep"] and (v["x"], v["y"]) == door(v["name"])
        assert v["goal"] is None and v["beliefs"] == {} and v["events"] == []
        assert v["memories"] == v["learnings"] == [] and v["views"] == {}
