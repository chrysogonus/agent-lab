"""Boat trips on the lake, once the village built its rowing boat
(specs/015-daily-happenings/research.md §5).

Pure: the runner applies the changes `boat_step` returns. The boat goes round a fixed loop of
lake cells for about an hour, with whoever is in it, and is back by the first rower's bedtime.
"""

from typing import Any

from agent_lab.village.seasons import weather
from agent_lab.village.world import (
    VILLAGERS,
    adjacent,
    clock,
    hhmm,
    listed,
    minute_of_day,
    place_at,
    place_cells,
    villager_named,
)

PIER_BOAT = (20, 17)  # where the built boat lies (the catalogue's boat)
LOOP: tuple[tuple[int, int], ...] = ((20, 18), (21, 19), (23, 20), (25, 20), (25, 19), (23, 18))
TRIP_STEPS = len(LOOP)  # an hour on the lake without "until"
BOARDING = 2  # steps the boat waits at the pier for the one invited

Boat = dict[str, Any]


def _villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def built(world: dict[str, Any]) -> bool:
    return any(b["key"] == "boat" for b in world["built"])


def in_boat(world: dict[str, Any], name: str) -> bool:
    boat: Boat | None = world["boat"]
    return bool(boat) and boat["state"] == "out" and name in boat["rowers"]


def row_refusal(world: dict[str, Any], name: str, with_: str | None) -> str | None:
    """Why a villager cannot take (or join) the boat now, or None."""
    boat: Boat | None = world["boat"]
    if not built(world):
        return "the village has no boat"
    if boat and boat["state"] == "boarding" and boat["invited"] == name:
        return None  # it joins
    if boat and name in boat["rowers"]:
        return "you are already in the boat"
    if boat and boat["state"] == "boarding":
        return f"{boat['rowers'][0]} is taking the boat out"
    if boat:
        return f"the boat is out with {listed(boat['rowers'])}"
    if weather(clock(world["tick"])[0]) == "storm":
        return "no boat trips in a storm"
    me = _villager(world, name)
    if place_at(me["x"], me["y"]) != "pier":
        return "the boat lies at the pier"
    if with_ is not None:
        other = villager_named(with_)
        them = other and other != name and _villager(world, other)
        if not them or them["asleep"] or not adjacent((me["x"], me["y"]), (them["x"], them["y"])):
            return f"{other or with_} is not next to you"
    return None


def start_trip(world: dict[str, Any], name: str, with_: str | None, until: int | None) -> Boat:
    boat: Boat = {
        "state": "boarding",
        "rowers": [name],
        "invited": with_,
        "since": world["tick"],
        "until": until,
        "out": None,
        "at": 0,
    }
    world["boat"] = boat
    return boat


def _done(world: dict[str, Any], boat: Boat) -> bool:
    minute = minute_of_day(world["tick"])
    if any(minute >= VILLAGERS[name].bed for name in boat["rowers"]):
        return True
    if boat["until"] is not None:
        return minute >= boat["until"]
    return world["tick"] >= boat["out"] + TRIP_STEPS


def boat_step(world: dict[str, Any]) -> list[dict[str, Any]]:
    """One step of the boat: leaving the pier, rowing round the lake, coming back."""
    boat: Boat | None = world["boat"]
    if boat is None:
        return []
    tick = world["tick"]
    if boat["state"] == "boarding":
        waited = tick - boat["since"]
        if waited < 1 or (boat["invited"] and waited < BOARDING):
            return []
        boat |= {"state": "out", "out": tick, "at": 0, "invited": None}
        _place(world, boat)
        return [{"change": "out", "rowers": list(boat["rowers"])}]
    if _done(world, boat):
        return [come_back(world)]
    boat["at"] += 1
    _place(world, boat)
    return []


def come_back(world: dict[str, Any]) -> dict[str, Any]:
    """The boat back at the pier: its rowers step onto the pier, and it lies there again."""
    boat: Boat = world["boat"]
    pier = place_cells("pier")
    for i, name in enumerate(boat["rowers"]):
        v = _villager(world, name)
        v["x"], v["y"] = pier[i % len(pier)]
    world["boat"] = None
    return {"change": "back", "rowers": list(boat["rowers"])}


def _place(world: dict[str, Any], boat: Boat) -> None:
    x, y = LOOP[int(boat["at"]) % len(LOOP)]
    for name in boat["rowers"]:
        v = _villager(world, name)
        v["x"], v["y"] = x, y


def boat_cell(world: dict[str, Any]) -> list[int]:
    boat: Boat | None = world["boat"]
    if boat and boat["state"] == "out":
        return list(LOOP[int(boat["at"]) % len(LOOP)])
    return list(PIER_BOAT)


def boat_text(world: dict[str, Any], name: str) -> str | None:
    """What a villager knows of the boat, once there is one."""
    if not built(world):
        return None
    boat: Boat | None = world["boat"]
    if boat is None:
        return "The boat lies at the pier."
    until = f"until {hhmm(boat['until'])}" if boat["until"] is not None else "for about an hour"
    if name in boat["rowers"] and boat["state"] == "out":
        return f"You are out on the lake in the boat {until}."
    if boat["state"] == "boarding":
        return f"{boat['rowers'][0]} is taking the boat out from the pier."
    return f"The boat is out on the lake with {listed(boat['rowers'])} {until}."
