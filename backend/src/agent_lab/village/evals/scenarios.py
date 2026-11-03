"""Scenarios: short slices of village life from a fixed start, run several times on fresh
copies with a condition to hold (specs/013-measuring-the-village/research.md §6)."""

import json
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_lab.bus import Bus
from agent_lab.llm.models import Models
from agent_lab.store import Store
from agent_lab.village.evals.checks import agent_models, read_owner
from agent_lab.village.evals.fixtures import FixtureError, build_world
from agent_lab.village.evals.results import Results, wilson
from agent_lab.village.health import TALK
from agent_lab.village.health_view import days_health
from agent_lab.village.runner import FAILED_TICKS_PAUSE, Village
from agent_lab.village.world import clock, listed

TICKS_PER_HOUR = 6
SHARED_AGENTS = (
    *("reflection_agent_id", "chronicler_agent_id"),
    *("planner_agent_id", "meeting_agent_id"),
)

Scenario = dict[str, Any]
World = dict[str, Any]
Condition = Callable[[Store, World, int, dict[str, Any]], tuple[bool, str]]


def _tick_at(day: int, text: str) -> int:
    found = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not found:
        raise ValueError(f"bad time {text!r}")
    return ((day - 1) * 1440 + int(found[1]) * 60 + int(found[2]) - 270) // 10


def _meeting_attendance(
    store: Store, world: World, start: int, p: dict[str, Any]
) -> tuple[bool, str]:
    meeting: dict[str, Any] = world["meeting"] or {}
    present: list[str] = meeting.get("present", [])
    why = f"{len(present)} came: {', '.join(present)}" if present else "nobody came"
    return len(present) >= p["at_least"], why


def _load_at_site(store: Store, world: World, start: int, p: dict[str, Any]) -> tuple[bool, str]:
    by = _tick_at(clock(start)[0], p["by"])
    for run in store.village_runs(start, by, float(world.get("born", 0.0))):
        action: dict[str, Any] = run["village_action"] or {}
        given = action.get("action") == "give" and action.get("to") is None
        if given and action.get("goods") == p["goods"]:
            when = clock(run["village_tick"])[1]
            return True, f"{run['villager']} set down {p['goods']} at {when}"
    record: dict[str, Any] = world["day_record"] or {}
    for item in record.get("items", []):  # set down by an intention, with no give answer (M14)
        found = re.match(r"^(\w+) set down a load of (\w+) at the building site\.$", item["text"])
        if found and found[2] == p["goods"] and start <= item["tick"] <= by:
            return True, f"{found[1]} set down {p['goods']} at {clock(item['tick'])[1]}"
    return False, f"no {p['goods']} set down at the site by {p['by']}"


def _talk_then_go(store: Store, world: World, start: int, p: dict[str, Any]) -> tuple[bool, str]:
    pair = set(p["pair"])
    record: dict[str, Any] = world["day_record"] or {}
    items: list[dict[str, Any]] = record.get("items", [])
    talk = next(
        (i for i in items if (m := TALK.match(i["text"])) and {m[1], m[2]} == pair),
        None,
    )
    if talk is None:
        return False, f"{listed(sorted(pair))} never talked"
    found = TALK.match(talk["text"])
    lines = len(found[3].split(" / ")) if found and found[3] else 0
    if lines > p["max_lines"]:
        return False, f"they talked {lines} lines, more than {p['max_lines']}"
    hours = p["within_hours"]
    rows = store.trail(talk["tick"] + 1, talk["tick"] + hours * TICKS_PER_HOUR)
    for name in p["pair"]:
        states = {v[4] for _, row in rows for v in row["v"] if v[0] == name}
        if not states & {"walking", "working"}:
            return False, (
                f"after their talk of {lines} lines, {name} did not move on within "
                f"{hours} hour{'s' if hours != 1 else ''}"
            )
    return True, f"they talked {lines} lines and both moved on"


def _built(store: Store, world: World, start: int, p: dict[str, Any]) -> tuple[bool, str]:
    done = [b for b in world["built"] if b["key"] == p["key"] and b["day"] <= p["by_day"]]
    if done:
        return True, f"{p['key']} was built on day {done[0]['day']}"
    return False, f"{p['key']} was not built by day {p['by_day']}"


def _boat_trip(store: Store, world: World, start: int, p: dict[str, Any]) -> tuple[bool, str]:
    """A boat trip by the time given, from the notes (M15)."""
    by = _tick_at(clock(start)[0], p["by"])
    record: dict[str, Any] = world["day_record"] or {}
    for item in record.get("items", []):
        found = re.match(r"^(.+) rowed out on the lake\.$", item["text"])
        if found and start <= item["tick"] <= by:
            how = "together" if " and " in found[1] else "alone"
            return True, f"{found[1]} rowed out at {clock(item['tick'])[1]}, {how}"
    return False, f"nobody took the boat out by {p['by']}"


CONDITIONS: dict[str, Condition] = {
    "meeting_attendance": _meeting_attendance,
    "load_at_site": _load_at_site,
    "talk_then_go": _talk_then_go,
    "built": _built,
    "boat_trip": _boat_trip,
}


def load_scenarios(directory: str | Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for path in sorted(Path(directory).glob("*.json")):
        scenario: Scenario = json.loads(path.read_text())
        condition = scenario.get("condition", {})
        if condition.get("kind") not in CONDITIONS:
            raise ValueError(f"{path.name}: unknown condition {condition.get('kind')!r}")
        if not {"until", "hours"} & set(scenario.get("horizon", {})):
            raise ValueError(f"{path.name}: the horizon needs until or hours")
        try:
            build_world(scenario["start"])
        except FixtureError as exc:
            raise ValueError(f"{path.name}: {exc}") from None
        scenarios.append(scenario)
    return scenarios


def _end(start: int, horizon: dict[str, Any]) -> int:
    if "hours" in horizon:
        return start + int(horizon["hours"]) * TICKS_PER_HOUR
    end = _tick_at(clock(start)[0], horizon["until"])
    return end if end > start else end + 144


def _fresh_copy(path: Path, owner_db: str | Path, scenario: Scenario) -> Store:
    """A new database holding the owner's agents and the scenario's starting village."""
    owner, agent_ids = read_owner(owner_db)
    path.unlink(missing_ok=True)
    store = Store(path)
    store.copy_agents_from(owner_db, agent_ids)
    world = build_world(scenario["start"])
    for v in world["villagers"]:
        v["agent_id"] = next(o["agent_id"] for o in owner["villagers"] if o["name"] == v["name"])
    for key in SHARED_AGENTS:
        world[key] = owner.get(key)
    store.save_village(world)
    return store


async def _run_once(
    scenario: Scenario, models: Models, owner_db: str | Path, path: Path
) -> dict[str, Any]:
    store = _fresh_copy(path, owner_db, scenario)
    village = Village(store=store, models=models, bus=Bus(), move_gap=0)
    start = village.world["tick"]
    end = _end(start, scenario["horizon"])
    finished, why = True, ""
    try:
        while village.world["tick"] < end:
            await village.step()
            if village.world["failed_ticks"] >= FAILED_TICKS_PAUSE:
                finished, why = False, "every decision failed three steps in a row"
                break
    except Exception as exc:  # a scenario reports; it never stops the others
        finished, why = False, f"stopped: {exc}"
    held: bool | None = None
    if finished:
        condition = scenario["condition"]
        held, why = CONDITIONS[condition["kind"]](store, village.world, start, condition)
    days = clock(end)[0] - clock(start)[0] + 1
    health = [h for h in days_health(store, village.world, days) if h["day"] >= clock(start)[0]]
    return {
        "db": str(path),
        "held": held,
        "why": why,
        "finished": finished,
        "until": "day {}, {}".format(*clock(village.world["tick"])[:2]),
        "health": health,
        "chronicle": [
            {"day": e["day"], "title": e["title"], "text": e["text"]}
            for e in village.world["chronicle"]
            if e["day"] >= clock(start)[0]
        ],
    }


async def run_scenarios(
    scenarios: list[Scenario],
    models: Models,
    owner_db: str | Path,
    copies: str | Path,
    evals_db: str | Path,
    repeats: int,
) -> dict[str, Any]:
    """Each scenario `repeats` times on fresh copies; the owner's database is only read."""
    Path(copies).mkdir(parents=True, exist_ok=True)
    _, agent_ids = read_owner(owner_db)
    Store(Path(copies) / "agents.db").copy_agents_from(owner_db, agent_ids)
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        n = scenario.get("repeats", repeats)
        runs = [
            await _run_once(scenario, models, owner_db, Path(copies) / f"{scenario['name']}-{i}.db")
            for i in range(1, n + 1)
        ]
        finished = [r for r in runs if r["finished"]]
        held = sum(1 for r in finished if r["held"])
        rows.append(
            {
                "name": scenario["name"],
                "held": held,
                "finished": len(finished),
                "attempts": n,
                "interval": list(wilson(held, len(finished))),
                "runs": runs,
            }
        )
    default = models.default
    result: dict[str, Any] = {
        "result_id": uuid.uuid4().hex[:12],
        "kind": "scenarios",
        "created_at": time.time(),
        "model": f"{default.provider}/{default.model}",
        "settings": {
            "owner_db": str(owner_db),
            "copies": str(copies),
            "models": agent_models(Store(Path(copies) / "agents.db"), agent_ids, models),
        },
        "repeats": repeats,
        "data": {"scenarios": rows},
    }
    Results(evals_db).save(result)
    return result
