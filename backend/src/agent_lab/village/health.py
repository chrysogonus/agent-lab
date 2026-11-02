"""Village health: numbers for every village day, from the stored runs, the day's notes and the
day trail (specs/013-measuring-the-village/research.md §1-§3)."""

import re
from collections import Counter
from collections.abc import Callable
from statistics import median
from typing import Any

from agent_lab.village.chronicle import weather_slips
from agent_lab.village.seasons import weather
from agent_lab.village.trade import BASKET_GOODS, BUILDING_GOODS
from agent_lab.village.world import VILLAGERS, adjacent, door, place_at, place_named

Villager = dict[str, Any]


def trail_row(world: dict[str, Any], state_of: Callable[[Villager], str]) -> dict[str, Any]:
    """Where everyone is at this step, what they do and carry, and how far the building is."""
    project = world["project"]
    return {
        "v": [
            [v["name"], v["x"], v["y"], place_at(v["x"], v["y"]), state_of(v), v["basket"]]
            for v in world["villagers"]
        ],
        "project": project["key"] if project else None,
        "used": sum(project["used"].values()) if project else 0,
    }


DECISIONS = ("move", "find", "say", "goodbye", "work", "give", "buy", "wait")
MEETING_RUNS = ("propose", "vote", "decide", "assign")
TALK = re.compile(r"^(\w+) and (\w+) talked; what they said \(their claims\): (.*)$")
ENTRY = re.compile(r"^(\d{2}):(\d{2}) (?:see (\w+)|([^:]+)): ")
STUCK_STEPS = 6  # a village hour in the same place and state, awake and not working
GOODS = (*BASKET_GOODS, *BUILDING_GOODS)

Run = dict[str, Any]
Trail = list[tuple[int, dict[str, Any]]]


def reason_template(text: str) -> str:
    """A wait reason with names and goods taken out, so the same refusal counts as one."""
    for name in VILLAGERS:
        text = re.sub(rf"\b{name}\b", "<villager>", text)
    for goods in GOODS:
        text = re.sub(rf"\b{goods}\b", "<goods>", text)
    return text


def _action(run: Run) -> dict[str, Any]:
    action: dict[str, Any] = run["village_action"] or {}
    return action


def _kind(run: Run) -> str:
    action = _action(run).get("action")
    if action in DECISIONS:
        return "decision"
    if action in MEETING_RUNS:
        return "meeting"
    if action in ("plan", "reflect", "chronicle"):
        return action
    return "decision" if run["villager"] else "chronicle"


def _failed(run: Run) -> bool:
    reason = _action(run).get("reason") or ""
    return run["status"] != "completed" or reason.startswith("turn failed")


def _tick(day: int, minute: int) -> int:
    return ((day - 1) * 1440 + minute - 270) // 10


def _plan_adherence(day: int, runs: list[Run], trail: Trail) -> dict[str, int]:
    """Plan entries kept: at the place, or next to the villager, within an hour of the time."""
    rows = dict(trail)
    last = max(rows)
    plans: dict[str, list[tuple[int, list[str]]]] = {}
    for r in runs:
        a = _action(r)
        if a.get("action") == "plan" and a.get("entries"):
            plans.setdefault(r["villager"], []).append((r["village_tick"], a["entries"]))
    kept = entries = 0
    for name, made in plans.items():
        for i, (made_at, texts) in enumerate(made):
            replaced_at = made[i + 1][0] if i + 1 < len(made) else None
            for text in texts:
                found = ENTRY.match(text)
                if not found:
                    continue
                at = _tick(day, int(found[1]) * 60 + int(found[2]))
                if at < made_at or (replaced_at is not None and at >= replaced_at):
                    continue  # already past when planned, or replaced by a revision
                if at + STUCK_STEPS > last:
                    continue  # its hour is not over yet
                window = [rows[t] for t in range(at, at + STUCK_STEPS + 1) if t in rows]
                entries += 1
                kept += any(_at_entry(name, found, row) for row in window)
    return {"kept": kept, "entries": entries}


def _at_entry(name: str, entry: re.Match[str], row: dict[str, Any]) -> bool:
    cells = {v[0]: v for v in row["v"]}
    me = cells.get(name)
    if me is None:
        return False
    if entry[3]:  # see someone
        other = cells.get(entry[3])
        return bool(other) and adjacent((me[1], me[2]), (other[1], other[2]))
    place = place_named(entry[4].strip())
    if place == "home":
        return (me[1], me[2]) == door(name)
    return place is not None and me[3] == place


def _meeting(runs: list[Run], notes: list[str]) -> dict[str, Any] | None:
    present = [
        n.split(" came to the town hall meeting")[0]
        for n in notes
        if n.endswith(" came to the town hall meeting.")
    ]
    actions = [_action(r) for r in runs]
    meeting = [a for a in actions if a.get("action") in ("propose", "vote", "decide")]
    if not meeting and not present:
        return None
    outcome = "open"
    for a in meeting:
        if a["action"] == "decide":
            outcome = f"decided: {a['project']}" if a.get("project") else "no decision"
    for n in notes:
        if n.startswith("Today's town hall meeting was "):
            outcome = n.removeprefix("Today's town hall meeting was ").rstrip(".")
    votes = sum(1 for a in meeting if a["action"] == "vote" and a.get("project"))
    return {"present": present, "votes": votes, "outcome": outcome}


def _loads_worked_in(trail: Trail) -> int:
    worked, before = 0, None
    for _, row in trail:
        if before is not None and before["project"]:
            if row["project"] == before["project"]:
                worked += max(0, row["used"] - before["used"])
            else:  # finished: the last load went in with it
                worked += 1
        before = row
    return worked


def _load_minutes(runs: list[Run]) -> int | None:
    bought: dict[tuple[str, str], int] = {}
    minutes: list[int] = []
    for r in runs:
        a = _action(r)
        if a.get("action") == "buy" and "reason" not in a:
            bought[(r["villager"], a["goods"])] = r["village_tick"]
        elif a.get("action") == "give" and a.get("to") is None and a.get("goods") in BUILDING_GOODS:
            start = bought.pop((r["villager"], a["goods"]), None)
            if start is not None:
                minutes.append((r["village_tick"] - start) * 10)
    return round(median(minutes)) if minutes else None


def _given_back(runs: list[Run]) -> int:
    given: list[tuple[str, str, str]] = []
    back = 0
    for r in runs:
        a = _action(r)
        if a.get("action") == "give" and a.get("to"):
            if (a["to"], r["villager"], a["goods"]) in given:
                back += 1
            given.append((r["villager"], a["to"], a["goods"]))
        elif a.get("action") == "wait" and "just gave you this" in (a.get("reason") or ""):
            back += 1
    return back


def _stuck_hours(trail: Trail) -> float:
    steps = 0
    runs: dict[str, tuple[tuple[Any, ...], int]] = {}
    for _, row in trail:
        for name, x, y, _place, state, _carrying in row["v"]:
            key = (x, y, state)
            same, length = runs.get(name, (None, 0))
            length = length + 1 if same == key else 1
            runs[name] = (key, length)
            if state in ("asleep", "working", "bedtime"):
                continue
            if length == STUCK_STEPS:
                steps += STUCK_STEPS
            elif length > STUCK_STEPS:
                steps += 1
    return steps / STUCK_STEPS


def day_health(
    day: int,
    runs: list[Run],
    notes: list[str],
    trail: Trail,
    chronicle: dict[str, Any] | None,
    final: bool,
) -> dict[str, Any] | None:
    """One village day's numbers; None for a day without runs. A number whose source is
    missing that day is None, never 0."""
    if not runs:
        return None
    calls: dict[str, int] = dict.fromkeys(
        ("decision", "plan", "reflect", "chronicle", "meeting"), 0
    )
    for r in runs:
        calls[_kind(r)] += 1
    decisions = [r for r in runs if _kind(r) == "decision" and not _failed(r)]
    actions = [_action(r) for r in decisions]
    reasons = Counter(
        reason_template(a["reason"]) for a in actions if a["action"] == "wait" and a.get("reason")
    )
    talks = [len(m[3].split(" / ")) if m[3] else 0 for m in map(TALK.match, notes) if m]
    has_trail = bool(trail)
    return {
        "day": day,
        "final": final,
        "trail": has_trail,
        "decisions": len(decisions),
        "waits": sum(1 for a in actions if a["action"] == "wait"),
        "failed_calls": sum(1 for r in runs if _failed(r)),
        "calls": calls,
        "refusals": [{"reason": r, "count": n} for r, n in reasons.most_common()],
        "conversations": {
            "count": len(talks),
            "lines": talks,
            "median_lines": float(median(talks)) if talks else None,
        },
        "repeated_lines": reasons["you already said that"],
        "plan_adherence": _plan_adherence(day, runs, trail) if has_trail else None,
        "meeting": _meeting(runs, notes),
        "trades": sum(1 for a in actions if a["action"] == "buy"),
        "loads_set_down": sum(
            1
            for a in actions
            if a["action"] == "give" and a.get("to") is None and a.get("goods") in BUILDING_GOODS
        ),
        "loads_worked_in": _loads_worked_in(trail) if has_trail else None,
        "load_minutes": _load_minutes(decisions),
        "given_back": _given_back(decisions),
        "weather_slips": (
            weather_slips(f"{chronicle['title']} {chronicle['text']}", weather(day))
            if chronicle
            else None
        ),
        "stuck_hours": _stuck_hours(trail) if has_trail else None,
    }
