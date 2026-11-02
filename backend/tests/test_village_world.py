"""The village map, homes, paths, nearness, clock and routines (FR-001 to FR-004, FR-014)."""

from typing import Any

import pytest

from agent_lab.village.world import (
    HEIGHT,
    HOMES,
    PLACES,
    PLOT_EXITS,
    ROWS,
    VERSION,
    VILLAGERS,
    WIDTH,
    adjacent,
    awake_at,
    clock,
    door,
    label_cell,
    letter_cells,
    new_world,
    place_at,
    place_cells,
    sees,
    step_towards,
    steps_to,
    upgrade,
    usual_place,
    walkable,
)


def test_map_size_and_characters() -> None:
    assert (WIDTH, HEIGHT) == (32, 22)
    assert all(len(row) == WIDTH for row in ROWS)
    assert set("".join(ROWS)) <= set(".=~TSMPFGBhjgltibr")
    for char in "~Bhjgltibr":
        x, y = next((x, y) for y, r in enumerate(ROWS) for x, c in enumerate(r) if c == char)
        assert not walkable(x, y), char
    assert walkable(0, 1) and not walkable(-1, 0) and not walkable(0, HEIGHT)


def test_every_place_and_door_is_reachable_from_every_other() -> None:
    starts = [label_cell(p) for p in PLACES] + [door(n) for n in VILLAGERS]
    goals = [place_cells(p) for p in PLACES] + [[door(n)] for n in VILLAGERS]
    for x, y in starts:
        for goal in goals:
            assert steps_to(x, y, goal) >= 0  # KeyError if unreachable


def test_every_walkable_cell_reaches_every_other_with_the_plots_blocked() -> None:
    cells = [(x, y) for y in range(HEIGHT) for x in range(WIDTH) if walkable(x, y)]
    reached = steps_to(*cells[0], [cells[-1]])  # KeyError if the plots cut the map apart
    assert reached >= 0
    assert all(steps_to(x, y, [cells[0]]) >= 0 for x, y in cells)


def test_the_building_plots() -> None:
    plots = {c: letter_cells(c) for c in "br"}
    assert plots["b"] == [(x, y) for y in (13, 14) for x in range(14, 18)]
    assert plots["r"] == [(x, y) for y in (17, 18) for x in range(9, 13)]
    for letter, exit_cell in PLOT_EXITS.items():
        assert walkable(*exit_cell) and any(adjacent(exit_cell, c) for c in plots[letter])


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
    assert usual_place("Jonas", (6 * 60 - 270) // 10) == "pier"
    assert usual_place("Jonas", (12 * 60 - 270) // 10) == "market"
    assert usual_place("Hilde", (6 * 60 - 270) // 10) == "home"  # still asleep
    assert usual_place("Lina", (23 * 60 - 270) // 10) == "home"


def test_new_world_has_everyone_asleep_at_home() -> None:
    world = new_world()
    assert (world["version"], world["tick"], world["running"]) == (VERSION, 0, False)
    assert VERSION == 7
    assert world["interval"] == 5
    assert world["conversations"] == world["talked_out"] == world["log"] == []
    names = [v["name"] for v in world["villagers"]]
    assert names == ["Hilde", "Jonas", "Greta", "Lina"]
    for v in world["villagers"]:
        assert v["asleep"] and (v["x"], v["y"]) == door(v["name"])
        assert v["goal"] is None and v["beliefs"] == {} and v["events"] == []
        assert v["memories"] == v["learnings"] == [] and v["views"] == {}
        assert v["plan"] is v["basket"] is v["working"] is None and v["said"] == []
        assert v["intention"] is None and v["requests"] == []
    assert world["stalls"] == {"fish": 0, "vegetables": 0, "flowers": 0}
    assert world["harvest"] == {"pier": 0, "fields": 0, "flower_garden": 0}
    assert world["planner_agent_id"] is None
    assert world["trader"] is world["meeting"] is world["project"] is None
    assert world["built"] == [] and world["meeting_agent_id"] is None


def test_a_version_4_world_gets_plans_baskets_and_stalls() -> None:
    world = new_world()
    for v in world["villagers"]:
        for key in ("plan", "basket", "working", "said"):
            del v[key]
    for key in ("stalls", "harvest", "planner_agent_id"):
        del world[key]
    world |= {"version": 4, "tick": 40, "chronicle": [{"day": 1}]}
    upgraded = upgrade(world)
    assert (upgraded["version"], upgraded["tick"], upgraded["chronicle"]) == (
        VERSION,
        40,
        [{"day": 1}],
    )
    for v in upgraded["villagers"]:
        assert v["plan"] is v["basket"] is v["working"] is None and v["said"] == []
    assert upgraded["stalls"] == {"fish": 0, "vegetables": 0, "flowers": 0}
    assert upgraded["harvest"] == {"pier": 0, "fields": 0, "flower_garden": 0}
    assert upgraded["planner_agent_id"] is None


def version_5_world() -> dict[str, Any]:
    world = new_world()
    for key in ("trader", "meeting", "project", "built", "meeting_agent_id"):
        del world[key]
    return world | {"version": 5}


def test_a_version_5_world_gets_trader_meeting_and_projects() -> None:
    world = version_5_world()
    world["villagers"][1] |= {"basket": "fish", "said": ["Hello"]}
    world["stalls"]["fish"] = 2
    upgraded = upgrade(world)
    assert upgraded["version"] == VERSION
    assert upgraded["trader"] is upgraded["meeting"] is upgraded["project"] is None
    assert upgraded["built"] == [] and upgraded["meeting_agent_id"] is None
    jonas = upgraded["villagers"][1]
    assert jonas["basket"] == "fish" and jonas["said"] == ["Hello"]  # M11 state is kept
    assert upgraded["stalls"]["fish"] == 2


def test_upgrading_moves_a_villager_off_a_new_plot() -> None:
    world = version_5_world()
    world["villagers"][2] |= {"x": 15, "y": 13, "asleep": False}  # on the bakehouse plot
    world["villagers"][3] |= {"x": 10, "y": 18, "asleep": False}  # on the barn plot
    upgraded = upgrade(world)
    assert (upgraded["villagers"][2]["x"], upgraded["villagers"][2]["y"]) == PLOT_EXITS["b"]
    assert (upgraded["villagers"][3]["x"], upgraded["villagers"][3]["y"]) == PLOT_EXITS["r"]


def test_a_version_6_world_gets_intentions_and_requests() -> None:
    world = new_world()
    for v in world["villagers"]:
        del v["intention"], v["requests"]
    world |= {"version": 6, "tick": 144 * 60, "project": {"key": "boat"}}
    world["villagers"][1] |= {"basket": "wood", "asleep": False}
    upgraded = upgrade(world)
    assert upgraded["version"] == VERSION
    for v in upgraded["villagers"]:
        assert v["intention"] is None and v["requests"] == []
    assert upgraded["project"] == {"key": "boat"}  # M12 state is kept
    assert upgraded["villagers"][1]["basket"] == "wood"
