"""Daily plans: each villager plans its day when it wakes and may revise it after a long talk
(specs/011-plans-and-purpose/research.md §1)."""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.village.meeting import meeting_text
from agent_lab.village.memory import recall, when
from agent_lab.village.seasons import WEATHER_TEXT, date, date_text, growth_text, weather
from agent_lab.village.trade import BASKET_GOODS, carried_text, trader_text
from agent_lab.village.work import stalls_text
from agent_lab.village.world import (
    VILLAGERS,
    clock,
    festival_lines,
    hhmm,
    label,
    place_named,
    villager_named,
)

PLAN_ENTRIES = 6
PURPOSE_TEXT = 120
REVISIONS = 2  # revisions a day, after conversations of at least 4 lines
MEMORIES_SHOWN = 8

Entry = dict[str, Any]  # {minute, place (key or "home") | None, villager | None, purpose}


def entry_text(entry: Entry) -> str:
    if entry["villager"]:
        where = f"see {entry['villager']}"
    else:
        where = "home" if entry["place"] == "home" else label(entry["place"])
    return f"{hhmm(entry['minute'])} {where}: {entry['purpose']}"


def marks(entries: list[Entry], minute: int) -> tuple[int | None, int | None]:
    """(current, next): the last entry whose time has come and the first still to come."""
    come = [i for i, e in enumerate(entries) if e["minute"] <= minute]
    current = come[-1] if come else None
    following = next((i for i, e in enumerate(entries) if e["minute"] > minute), None)
    return current, following


def plan_note(name: str, text: str, revised: bool) -> str:
    """A plan in the day record: what a villager meant to do, never what happened."""
    did = "changed the plan" if revised else "planned the day"
    return f"{name} {did} (intentions, not events): {text}"


def plan_lines(entries: list[Entry], minute: int) -> list[str]:
    current, following = marks(entries, minute)
    mark = {current: " (now)", following: " (next)"}
    return [
        "Your plan for today:",
        *[f"- {entry_text(e)}{mark.get(i, '')}" for i, e in enumerate(entries)],
    ]


def plan_prompt(world: dict[str, Any], name: str, revise: str | None = None) -> str:
    """What the planner gets for a villager's day; with `revise`, the conversation just had."""
    me = next(v for v in world["villagers"] if v["name"] == name)
    character = VILLAGERS[name]
    tick = world["tick"]
    day = clock(tick)[0]
    usual = ", ".join(f"{hour:02d}:00 {label(place)}" for hour, place in character.routine)
    views = me["views"]
    remembered = recall(me["memories"], tick, set(), None, MEMORIES_SHOWN)
    lines = [
        character.persona,
        f"You get up at {hhmm(character.wake)} and go to bed at {hhmm(character.bed)}. "
        f"Your usual day: {usual}.",
        f"Day {day} ({date_text(day)}), {clock(tick)[1]}. {WEATHER_TEXT[weather(day)]}.",
        *festival_lines(tick),
        *[growth_text(place, world["growth"]) for place in ("fields", "flower_garden")],
        *([stalls_text(world["stalls"])] if date(day)[1] == "autumn" else []),
        *([f"You carry a {carried_text(me['basket'])}."] if me["basket"] else []),
        trader_text(world),
        meeting_text(world, name),
        *(
            ["Plan to take your basket to the square and set it out on the festival stalls."]
            if me["basket"] in BASKET_GOODS and date(day)[1] == "autumn"
            else []
        ),
        "What you have learned:",
        *([f"- {item['text']}" for item in me["learnings"]] or ["- nothing yet"]),
        "What you think of the others:",
        *[
            f"- {other}: {views[other]['text'] if other in views else 'no view yet'}"
            for other in VILLAGERS
            if other != name
        ],
        "What you remember:",
        *([f"- {when(m['tick'])} {m['text']}" for m in remembered] or ["- nothing yet"]),
    ]
    if revise is not None:
        entries: list[Entry] = me["plan"]["entries"] if me["plan"] else []
        lines += [
            "Your plan so far:",
            *([f"- {entry_text(e)}" for e in entries] or ["- none"]),
            "The conversation you just had:",
            revise,
        ]
    lines.append("Plan your day. Answer with one JSON object.")
    return "\n".join(lines)


class _Entry(BaseModel):
    time: str
    place: str | None = None
    villager: str | None = None
    purpose: str


class _Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: list[_Entry]


def _minute(time: str) -> int | None:
    found = re.fullmatch(r"(\d{1,2}):(\d{2})", time.strip())
    if not found or int(found[1]) > 23 or int(found[2]) > 59:
        return None
    return int(found[1]) * 60 + int(found[2])


def parse_plan(answer: str | None, name: str) -> tuple[list[Entry] | None, str | None]:
    """The plan's entries, sorted by time, or None and the reason the answer is unusable.
    Entries with a bad time, nowhere to be or nobody to see, or no purpose are dropped."""
    if not answer:
        return None, "no answer"
    try:
        plan = _Plan.model_validate(json.loads(answer))
    except json.JSONDecodeError:
        return None, "the answer is not JSON"
    except ValidationError as exc:
        return None, f"not a valid plan: {exc.errors()[0]['msg']}"
    entries: list[Entry] = []
    for item in plan.plan:
        minute = _minute(item.time)
        place = place_named(item.place) if item.place else None
        villager = None if place or not item.villager else villager_named(item.villager)
        purpose = item.purpose.strip()[:PURPOSE_TEXT]
        if minute is None or not (place or (villager and villager != name)) or not purpose:
            continue
        entries.append({"minute": minute, "place": place, "villager": villager, "purpose": purpose})
    entries = sorted(entries, key=lambda e: e["minute"])[:PLAN_ENTRIES]
    if len(entries) < 2:
        return None, "a plan needs at least 2 entries"
    return entries, None


PLAN = (
    "You help a villager of a small village plan its day. You get its character, its usual day, "
    "the date and weather, how the fields and the flower garden are doing, what it learned, what "
    "it thinks of the others and what it remembers. Reply with only one JSON object and nothing "
    'else:\n{"plan": [{"time": "07:30", "place": "town hall", "purpose": "Go through the '
    'festival list"}, {"time": "11:00", "villager": "Jonas", "purpose": "Ask him for fish"}]}\n'
    '"plan": 2 to 6 entries in time order while the villager is up; each has a "time" (HH:MM), '
    'either a "place" (town hall, square, market, pier, fields, flower garden or home) or a '
    '"villager" to see (Hilde, Jonas, Greta or Lina), and a short "purpose" in the villager\'s '
    "own words. Plan what the villager wants to get done today, given its character, the season, "
    "the weather and what it remembers."
)


def planner_agent() -> dict[str, Any]:
    """The block agent that plans every villager's day: one model call, a JSON check."""
    model = {"kind": "model", "name": "plan", "system": PLAN, "message": "{previous}"}
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": "Village planner",
        "description": "Plans a villager's day when it wakes, and again after a long talk.",
        "sample_prompt": "You are Jonas, the fisher.\nPlan your day. Answer with one JSON object.",
        "config": {"reasoning": False, "blocks": [model, check]},
    }
