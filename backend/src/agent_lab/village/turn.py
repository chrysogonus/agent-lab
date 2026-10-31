"""One villager's decision: what it observes, and the action its answer becomes."""

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from agent_lab.village.world import (
    PLACES,
    VILLAGERS,
    adjacent,
    clock,
    door,
    hhmm,
    label,
    minute_of_day,
    place_at,
    place_cells,
    sees,
    steps_to,
    usual_place,
)

SPEECH_SHOWN = 200  # characters of a line shown on the map and heard by others


class Move(BaseModel):
    action: Literal["move"]
    place: str


class Find(BaseModel):
    action: Literal["find"]
    villager: str


class Say(BaseModel):
    action: Literal["say"]
    text: str
    to: str | None = None


class Goodbye(BaseModel):
    action: Literal["goodbye"]
    text: str | None = None


class Wait(BaseModel):
    action: Literal["wait"]


ACTION = TypeAdapter[Move | Find | Say | Goodbye | Wait](
    Annotated[Move | Find | Say | Goodbye | Wait, Field(discriminator="action")]
)

Villager = dict[str, Any]


def villager_of(world: dict[str, Any], name: str) -> Villager:
    return next(v for v in world["villagers"] if v["name"] == name)


def cell(v: Villager) -> tuple[int, int]:
    return v["x"], v["y"]


def awake_neighbours(world: dict[str, Any], name: str) -> list[str]:
    """Awake villagers right next to an awake villager: the only ones it can talk to."""
    me = villager_of(world, name)
    if me["asleep"]:
        return []
    return [
        v["name"]
        for v in world["villagers"]
        if v is not me and not v["asleep"] and adjacent(cell(me), cell(v))
    ]


def talked_out(world: dict[str, Any], a: str, b: str) -> bool:
    return sorted([a, b]) in world["talked_out"]


def partners(world: dict[str, Any], name: str) -> list[str]:
    """Who a villager is in a conversation with."""
    return [
        c["b"] if c["a"] == name else c["a"]
        for c in world["conversations"]
        if name in (c["a"], c["b"])
    ]


def _place_phrase(where: str | None, at: tuple[int, int]) -> str:
    if where == "home":
        return "at home"
    if where:
        return f"at the {label(where)}"
    nearest = min(PLACES, key=lambda p: steps_to(at[0], at[1], place_cells(p)))
    return f"near the {label(nearest)}"


def belief_text(world: dict[str, Any], name: str, other: str) -> str:
    """Where `name` thinks `other` is, and how it knows."""
    belief = villager_of(world, name)["beliefs"].get(other)
    if belief:
        where = _place_phrase(belief["where"], (belief["cell"][0], belief["cell"][1]))
        when = clock(belief["tick"])[1]
        if belief["source"] == "seen":
            return f"{where} (seen {when})"
        return f"{where} (heard from {belief['from']} at {when})"
    usual = usual_place(other, minute_of_day(world["tick"]))
    if usual == "home":
        return "at home asleep at this hour (their routine)"
    return f"usually at the {label(usual)} around now (their routine)"


def where_text(world: dict[str, Any], v: Villager) -> str:
    here = place_at(v["x"], v["y"])
    if v["asleep"]:
        return "You are asleep at home."
    if here:
        return f"You are at the {label(here)}."
    if cell(v) == door(v["name"]):
        return "You are at your home's door."
    return "You are outside, between places."


def goal_text(goal: dict[str, Any] | None) -> str | None:
    if goal is None:
        return None
    if goal["kind"] == "place":
        return f"walking to the {label(goal['place'])}"
    if goal["kind"] == "home":
        return "going home"
    return f"looking for {goal['villager']}"


def _heard(entry: dict[str, Any], listener: str) -> str:
    to = entry.get("to")
    who = entry["from"] if not to else f"{entry['from']} to {'you' if to == listener else to}"
    return f'- {who}: "{entry["text"]}"'


def observation(world: dict[str, Any], name: str) -> str:
    """The changing world as one villager sees it; persona and rules live in its agent."""
    me = villager_of(world, name)
    character = VILLAGERS[name]
    day, time, period = clock(world["tick"])
    next_to = awake_neighbours(world, name)
    in_sight = [
        f"{VILLAGERS[v['name']].title} ({max(abs(v['x'] - me['x']), abs(v['y'] - me['y']))}"
        " steps away)"
        for v in world["villagers"]
        if v is not me and not v["asleep"] and v["name"] not in next_to and sees(cell(me), cell(v))
    ]
    talking = partners(world, name)
    if talking:
        lines_so_far = {
            (c["b"] if c["a"] == name else c["a"]): c["lines"]
            for c in world["conversations"]
            if name in (c["a"], c["b"])
        }
        conversation = "You are talking with " + ", ".join(
            f"{p} ({lines_so_far[p]} lines so far)" for p in talking
        )
    else:
        conversation = "You are not talking with anyone"
    tired = [n for n in next_to if talked_out(world, name, n)]
    here = place_at(me["x"], me["y"])
    x, y = cell(me)
    places = [f"{label(p)} {steps_to(x, y, place_cells(p))} steps" for p in PLACES if p != here]
    places.append(f"your home {steps_to(x, y, [door(name)])} steps")
    goal = goal_text(me["goal"])
    lines = [
        f"Day {day}, {time}, {period}. {where_text(world, me)}",
        f"You get up at {hhmm(character.wake)} and go to bed at {hhmm(character.bed)}.",
        *([f"You are {goal}."] if goal else []),
        f"Next to you: {', '.join(VILLAGERS[n].title for n in next_to) or 'nobody'}.",
        f"In sight: {', '.join(in_sight) or 'nobody else'}.",
        f"{conversation}."
        + (
            f" You have talked a long time with {', '.join(tired)}; say goodbye or go on."
            if tired
            else ""
        ),
        "Said to you since your last turn:",
        *([_heard(e, name) for e in me["inbox"]] or ["- nothing"]),
        "Where the others are, as far as you know:",
        *[f"- {o}: {belief_text(world, name, o)}" for o in VILLAGERS if o != name],
        f"Places: {', '.join(places)}.",
        "Your last events:",
        *([f"- {clock(e['tick'])[1]} {e['text']}" for e in me["events"]] or ["- none yet"]),
        "What do you do? Answer with one JSON object.",
    ]
    return "\n".join(lines)


def _place(text: str) -> str | None:
    wanted = text.strip().lower().removeprefix("the ").replace("_", " ")
    if wanted in ("home", "my home", "your home"):
        return "home"
    return next((key for key in PLACES if label(key) == wanted), None)


def _name(text: str) -> str | None:
    return next((n for n in VILLAGERS if n.lower() == text.strip().lower()), None)


def parse_action(
    answer: str | None, world: dict[str, Any], name: str
) -> tuple[dict[str, Any], str | None]:
    """The action to apply and, when it had to become `wait`, the reason."""
    wait = {"action": "wait"}
    if not answer:
        return wait, "no answer"
    try:
        action = ACTION.validate_python(json.loads(answer))
    except json.JSONDecodeError:
        return wait, "the answer is not JSON"
    except ValidationError as exc:
        return wait, f"not a valid action: {exc.errors()[0]['msg']}"
    me = villager_of(world, name)
    if isinstance(action, Move):
        place = _place(action.place)
        if place is None:
            return wait, f"unknown place {action.place!r}"
        if place == "home" and cell(me) == door(name):
            return wait, "already at your home"
        if place != "home" and place_at(me["x"], me["y"]) == place:
            return wait, f"already at the {label(place)}"
        return {"action": "move", "place": place}, None
    if isinstance(action, Find):
        other = _name(action.villager)
        if other is None or other == name:
            return wait, f"unknown villager {action.villager!r}"
        if other in awake_neighbours(world, name):
            return wait, f"{other} is already next to you"
        return {"action": "find", "villager": other}, None
    if isinstance(action, Say | Goodbye):
        text = (action.text or "").strip()
        if isinstance(action, Goodbye):
            return {"action": "goodbye", "text": text or None}, None
        if not text:
            return wait, "nothing to say"
        to = None
        if action.to:
            to = _name(action.to)
            if to is None or to == name:
                return wait, f"unknown villager {action.to!r}"
        next_to = awake_neighbours(world, name)
        if to and to not in next_to:
            return wait, f"{to} is not next to you"
        if not next_to:
            return wait, "nobody is next to you"
        hearers = [to] if to else next_to
        if all(talked_out(world, name, h) for h in hearers):
            return wait, (
                f"you have talked a long time with {', '.join(hearers)}; say goodbye or go on"
            )
        return {"action": "say", "text": text, "to": to}, None
    return wait, None


def heard_places(text: str, speaker: str, hearer: str) -> dict[str, str]:
    """Villagers a line places somewhere: a sentence naming one of them and one place (or home)."""
    found: dict[str, str] = {}
    for sentence in re.split(r"[.!?]", text.lower()):
        names = [n for n in VILLAGERS if n not in (speaker, hearer) and n.lower() in sentence]
        places = [p for p in PLACES if label(p) in sentence]
        if "home" in sentence:
            places.append("home")
        if len(names) == 1 and len(places) == 1:
            found[names[0]] = places[0]
    return found


RULES = (
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden, "
    "and everyone's own home. Time passes in steps of 10 minutes. You are asked what to do when "
    "something happens: you woke up, arrived somewhere, met someone, someone spoke to you, or a "
    "while passed. Reply with only one JSON object and nothing else:\n"
    '{"action": "move", "place": "market"} to walk to a place or "home" (one step every 10 '
    "minutes until you arrive),\n"
    '{"action": "find", "villager": "Lina"} to go and look for someone where you think they '
    "are,\n"
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to talk to someone standing right '
    'next to you ("to" is optional). You can only talk to people right next to you: to talk to '
    "someone else, find them first,\n"
    '{"action": "goodbye", "text": "See you later!"} to end a conversation ("text" is '
    "optional),\n"
    '{"action": "wait"} to go on with what you are doing.\n'
    "You go home to sleep at your bedtime by yourself. Say short things, stay in character, "
    "answer people who talk to you, and say goodbye when you have said what you wanted."
)


def villager_agent(name: str) -> dict[str, Any]:
    """The block agent that plays a villager: one model call, then a JSON check."""
    character = VILLAGERS[name]
    home = (
        f"You live in {character.home}. You get up at {hhmm(character.wake)} and go to bed at "
        f"{hhmm(character.bed)}."
    )
    decide = {
        "kind": "model",
        "name": "decide",
        "system": f"{character.persona} {home}\n\n{RULES}",
        "message": "{previous}",
    }
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": character.title,
        "description": f"Plays {character.title} in the village.",
        "sample_prompt": "Day 1, 05:00, morning. You are at your home's door.\nWhat do you do?",
        "config": {"reasoning": False, "blocks": [decide, check]},
    }
