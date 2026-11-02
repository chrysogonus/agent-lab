"""A village from a few lines of JSON, for turn checks and scenarios
(specs/013-measuring-the-village/research.md §4, data-model.md "Fixture")."""

import re
import time
from typing import Any

from agent_lab.village.build import CATALOGUE, entry, new_project
from agent_lab.village.memory import remember
from agent_lab.village.seasons import date, new_growth
from agent_lab.village.trade import BASKET_GOODS, BUILDING_GOODS, trader_stock
from agent_lab.village.world import (
    PLACES,
    VILLAGERS,
    adjacent,
    door,
    new_world,
    place_cells,
    place_named,
    walkable,
)

KEYS = {
    *("day", "time", "villagers", "conversations", "trader", "project", "built", "meeting"),
    *("stalls", "growth"),
}
VILLAGER_KEYS = {
    *("at", "asleep", "carrying", "working", "goal", "memories", "learnings", "inbox"),
    *("said", "events", "plan", "triggers"),
}
FIRST_MINUTE = 270  # 04:30 of day 1, tick 0

Fixture = dict[str, Any]


class FixtureError(ValueError):
    """The fixture names something the village does not have."""


def _unknown(keys: set[str], allowed: set[str], whose: str = "") -> None:
    for key in sorted(keys - allowed):
        raise FixtureError(f"unknown key {key!r}{f' for {whose}' if whose else ''}")


def _minute(text: str) -> int:
    found = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not found or int(found[1]) > 23 or int(found[2]) > 59:
        raise FixtureError(f"bad time {text!r}")
    return int(found[1]) * 60 + int(found[2])


def _place(text: str) -> str:
    if text in PLACES or text in ("home", "site"):
        return text
    found = place_named(text)
    if found is None:
        raise FixtureError(f"unknown place {text!r}")
    return found


def _goods(text: str) -> str:
    if text not in (*BASKET_GOODS, *BUILDING_GOODS):
        raise FixtureError(f"unknown goods {text!r}")
    return text


def _cell(world: dict[str, Any], name: str, at: Any) -> tuple[int, int]:
    if isinstance(at, list):
        cell: list[Any] = at  # pyright: ignore[reportUnknownVariableType]
        x, y = int(cell[0]), int(cell[1])
        if not walkable(x, y):
            raise FixtureError(f"{[x, y]} is not a walkable cell")
        return x, y
    place = _place(str(at))
    if place == "home":
        return door(name)
    if place == "site":
        if world["project"] is None:
            raise FixtureError("no project, so no building site")
        return entry(world["project"]["key"]).site[0]
    return place_cells(place)[0]


def _project(spec: dict[str, Any], day: int) -> dict[str, Any]:
    _unknown(set(spec), {"key", "site", "used", "tasks"}, "the project")
    if spec["key"] not in {p.key for p in CATALOGUE}:
        raise FixtureError(f"unknown project {spec['key']!r}")
    project = new_project(spec["key"], day)
    for part in ("site", "used"):
        for goods, n in spec.get(part, {}).items():
            project[part][_goods(goods)] = n
    project["tasks"] = list(spec.get("tasks", []))
    return project


def _villager(world: dict[str, Any], name: str, spec: dict[str, Any], day: int) -> None:
    _unknown(set(spec), VILLAGER_KEYS, name)
    tick = world["tick"]
    v = next(x for x in world["villagers"] if x["name"] == name)
    x, y = _cell(world, name, spec.get("at", "home"))
    v |= {"x": x, "y": y, "asleep": bool(spec.get("asleep", False))}
    if "carrying" in spec:
        v["basket"] = _goods(spec["carrying"])
    if "working" in spec:
        v["working"] = {"place": _place(spec["working"]), "steps": 0}
    if "goal" in spec:
        goal = _place(spec["goal"])
        v["goal"] = {"kind": "home"} if goal == "home" else {"kind": "place", "place": goal}
    for text in spec.get("memories", []):
        remember(v, tick - 1, "conversation", text, [], None)
    v["learnings"] = [{"tick": tick - 1, "text": t} for t in spec.get("learnings", [])]
    v["inbox"] = [
        {"from": i["from"], "to": name, "text": i["text"], "tick": tick}
        for i in spec.get("inbox", [])
    ]
    v["said"] = list(spec.get("said", []))
    v["triggers"] = list(spec.get("triggers", []))  # a reason to decide on the first step
    v["events"] = [{"tick": tick - 1, "kind": "event", "text": t} for t in spec.get("events", [])]
    if "plan" in spec:
        entries = [
            {
                "minute": _minute(e["time"]),
                "place": _place(e["place"]) if "place" in e else None,
                "villager": e.get("villager"),
                "purpose": e["purpose"],
            }
            for e in spec["plan"]
        ]
        v["plan"] = {"day": day, "entries": entries, "revisions": 0}


def build_world(fixture: Fixture) -> dict[str, Any]:
    """`new_world()` at the fixture's day and time, with what it sets; the villagers it does not
    name are asleep at home."""
    _unknown(set(fixture), KEYS)
    day = int(fixture["day"])
    absolute = (day - 1) * 1440 + _minute(fixture["time"])
    if absolute < FIRST_MINUTE:
        raise FixtureError("the time is before the village's first morning (day 1, 04:30)")
    world = new_world()
    tick = (absolute - FIRST_MINUTE) // 10
    world |= {"tick": tick, "growth": new_growth(date(day)[1]), "born": time.time()}
    if "growth" in fixture:
        for place, stage in fixture["growth"].items():
            world["growth"][place]["stage"] = stage
    if "project" in fixture:
        world["project"] = _project(fixture["project"], day)
    world["built"] = [{"key": key, "day": day - 1} for key in fixture.get("built", [])]
    for key in fixture.get("built", []):
        if key not in {p.key for p in CATALOGUE}:
            raise FixtureError(f"unknown project {key!r}")
    named: dict[str, Any] = fixture.get("villagers", {})
    for name in named:
        if name not in VILLAGERS:
            raise FixtureError(f"unknown villager {name!r}")
    for v in world["villagers"]:
        v["last_decided"] = tick
        if v["name"] in named:
            _villager(world, v["name"], named[v["name"]], day)
    awake = [v for v in world["villagers"] if not v["asleep"]]
    for v in awake:  # already next to each other: no "met" on the first step
        v["neighbours"] = sorted(
            o["name"] for o in awake if o is not v and adjacent((v["x"], v["y"]), (o["x"], o["y"]))
        )
    world["conversations"] = [
        {"a": a, "b": b, "lines": lines, "last_tick": tick, "transcript": []}
        for a, b, lines in fixture.get("conversations", [])
    ]
    trader = fixture.get("trader")
    if trader:
        stock = trader_stock(day) if trader is True else {g: 0 for g in BUILDING_GOODS} | trader
        world["trader"] = {"day": day, "stock": stock}
    if "meeting" in fixture:
        m = fixture["meeting"]
        _unknown(set(m), {"kind", "proposals", "votes", "present"}, "the meeting")
        world["meeting"] = {
            "day": day,
            "kind": m.get("kind", "vote"),
            "proposals": [{**p, "run_id": None} for p in m.get("proposals", [])],
            "votes": {n: {**vote, "run_id": None} for n, vote in m.get("votes", {}).items()},
            "present": list(m.get("present", [])),
            "decision": None,
            "outcome": None,
        }
    for goods, n in fixture.get("stalls", {}).items():
        world["stalls"][_goods(goods)] = n
    if awake:
        world["day_record"] = {"day": day, "items": []}  # notes are kept from the start
    return world
