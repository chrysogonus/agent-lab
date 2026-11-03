"""Boat trips (FR-006 to FR-008)."""

from typing import Any

from agent_lab.village.boat import (
    LOOP,
    PIER_BOAT,
    TRIP_STEPS,
    boat_cell,
    boat_step,
    boat_text,
    in_boat,
    row_refusal,
    start_trip,
)
from agent_lab.village.evals.fixtures import build_world
from agent_lab.village.world import ROWS, place_cells


def world_with_boat(time: str = "14:00", **villagers: Any) -> dict[str, Any]:
    fixture = {"day": 66, "time": time, "built": ["boat"], "villagers": villagers}
    return build_world(fixture)


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def test_the_loop_is_on_the_lake() -> None:
    assert len(LOOP) == TRIP_STEPS == 6
    assert all(ROWS[y][x] == "~" for x, y in [*LOOP, PIER_BOAT])


def test_row_refusals() -> None:
    world = world_with_boat(Jonas={"at": "pier"}, Greta={"at": "pier"}, Lina={"at": "market"})
    assert row_refusal(world, "Jonas", None) is None
    assert row_refusal(world, "Lina", None) == "the boat lies at the pier"
    assert row_refusal(world, "Jonas", "Lina") == "Lina is not next to you"
    jonas, greta = villager(world, "Jonas"), villager(world, "Greta")
    greta["x"], greta["y"] = jonas["x"], jonas["y"] + 1
    assert row_refusal(world, "Jonas", "Greta") is None
    start_trip(world, "Jonas", None, None)
    assert row_refusal(world, "Greta", None) == "Jonas is taking the boat out"
    world["boat"]["state"] = "out"
    assert row_refusal(world, "Greta", None) == "the boat is out with Jonas"
    nothing = build_world({"day": 66, "time": "14:00", "villagers": {"Jonas": {"at": "pier"}}})
    assert row_refusal(nothing, "Jonas", None) == "the village has no boat"


def test_no_trips_in_a_storm() -> None:
    from agent_lab.village.seasons import weather

    day = next(d for d in range(1, 200) if weather(d) == "storm")
    world = build_world(
        {"day": day, "time": "12:00", "built": ["boat"], "villagers": {"Jonas": {"at": "pier"}}}
    )
    assert row_refusal(world, "Jonas", None) == "no boat trips in a storm"


def test_an_invited_villager_may_join_while_boarding() -> None:
    world = world_with_boat(Jonas={"at": "pier"}, Greta={"at": "pier"})
    start_trip(world, "Jonas", "Greta", None)
    assert world["boat"]["invited"] == "Greta"
    assert row_refusal(world, "Greta", None) is None  # she joins


def test_a_trip_boards_goes_round_the_lake_and_comes_back() -> None:
    world = world_with_boat(Jonas={"at": "pier"})
    start_trip(world, "Jonas", None, None)
    assert boat_step(world) == []  # boarding: waits for nobody
    world["tick"] += 1
    assert boat_step(world) == [{"change": "out", "rowers": ["Jonas"]}]
    jonas = villager(world, "Jonas")
    assert in_boat(world, "Jonas") and [jonas["x"], jonas["y"]] == list(LOOP[0])
    changes: list[dict[str, Any]] = []
    for _ in range(TRIP_STEPS):
        world["tick"] += 1
        changes += boat_step(world)
    assert changes == [{"change": "back", "rowers": ["Jonas"]}]
    assert world["boat"] is None and not in_boat(world, "Jonas")
    assert (jonas["x"], jonas["y"]) in place_cells("pier")


def test_a_trip_until_a_time_and_bedtime() -> None:
    world = world_with_boat("20:00", Jonas={"at": "pier"})
    start_trip(world, "Jonas", None, 21 * 60 + 30)  # past his bedtime (21:00)
    world["tick"] += 2
    boat_step(world)
    world["tick"] += 5  # 21:10
    assert boat_step(world) == [{"change": "back", "rowers": ["Jonas"]}]


def test_the_boat_text_and_cell() -> None:
    world = world_with_boat(Jonas={"at": "pier"}, Lina={"at": "market"})
    assert boat_text(world, "Lina") == "The boat lies at the pier."
    assert boat_cell(world) == list(PIER_BOAT)
    start_trip(world, "Jonas", None, 15 * 60)
    world["boat"]["state"] = "out"
    assert boat_text(world, "Lina") == "The boat is out on the lake with Jonas until 15:00."
    assert boat_text(world, "Jonas") == "You are out on the lake in the boat until 15:00."
    nothing = build_world({"day": 66, "time": "14:00", "villagers": {"Jonas": {"at": "pier"}}})
    assert boat_text(nothing, "Jonas") is None
