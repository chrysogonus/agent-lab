"""Village health of the recent days, gathered from the store and the world
(specs/013-measuring-the-village/research.md §1, §7)."""

import re
from typing import Any

from agent_lab.store import Store
from agent_lab.village.health import day_health
from agent_lab.village.world import clock

TICKS_PER_DAY = 144
DAYS_KEPT = 28  # as the chronicle and the day trail
NOTE = re.compile(r"^- \d{2}:\d{2} (.*)$")


def day_ticks(day: int) -> tuple[int, int]:
    """The first and last step of a village day, midnight to midnight (tick 0 is day 1, 04:30)."""
    first = max(0, ((day - 1) * 1440 - 270) // 10)
    return first, (day * 1440 - 270) // 10 - 1


_cache: dict[tuple[int, float, int], dict[str, Any]] = {}  # finished days, by store, born, day


def _notes(store: Store, world: dict[str, Any], day: int, born: float) -> list[str]:
    """The day's happenings: still in the day record, or in the prompt of its chronicle."""
    record = world["day_record"]
    if record and record["day"] == day:
        return [item["text"] for item in record["items"]]
    prompt = store.chronicle_prompt_of(day, born) or ""
    return [m[1] for m in map(NOTE.match, prompt.splitlines()) if m]


def _runs(store: Store, day: int, born: float) -> list[dict[str, Any]]:
    """The day's runs, with its chronicle, which is written after midnight."""
    first, last = day_ticks(day)
    found: list[dict[str, Any]] = []
    for run in store.village_runs(first, last + TICKS_PER_DAY, born):
        action: dict[str, Any] = run["village_action"] or {}
        if action.get("action") == "chronicle":
            if action.get("day") == day:
                found.append(run)
        elif run["village_tick"] <= last:
            found.append(run)
    return found


def days_health(store: Store, world: dict[str, Any], days: int = 14) -> list[dict[str, Any]]:
    """Village health of up to `days` recent days (at most 28), newest first; days without
    runs are left out."""
    born = float(world.get("born", 0.0))
    today = clock(world["tick"])[0]
    found: list[dict[str, Any]] = []
    for day in range(today, max(0, today - min(days, DAYS_KEPT)), -1):
        key = (id(store), born, day)
        if key in _cache:
            found.append(_cache[key])
            continue
        chronicle = next((e for e in world["chronicle"] if e["day"] == day), None)
        first, last = day_ticks(day)
        health = day_health(
            day,
            _runs(store, day, born),
            _notes(store, world, day, born),
            store.trail(first, last),
            chronicle,
            final=day < today,
        )
        if health is None:
            continue
        if day < today and chronicle:  # nothing about it changes any more
            _cache[key] = health
        found.append(health)
    return found
