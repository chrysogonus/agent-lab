"""One villager's turn: what it observes, and the action its answer becomes."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from agent_lab.village.world import PLACES, VILLAGERS, clock, label, nearby, place_at, steps_between

SPEECH_SHOWN = 200  # characters of a speech shown on the map and heard by others


class Move(BaseModel):
    action: Literal["move"]
    place: str


class Say(BaseModel):
    action: Literal["say"]
    text: str
    to: str | None = None


class Wait(BaseModel):
    action: Literal["wait"]


ACTION = TypeAdapter[Move | Say | Wait](Annotated[Move | Say | Wait, Field(discriminator="action")])


def _villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def _heard(entry: dict[str, Any], listener: str) -> str:
    to = entry.get("to")
    who = entry["from"] if not to else f"{entry['from']} to {'you' if to == listener else to}"
    return f'- {who}: "{entry["text"]}"'


def observation(world: dict[str, Any], name: str) -> str:
    """The changing world as one villager sees it; persona and rules live in its agent."""
    me = _villager(world, name)
    day, time, period = clock(world["tick"])
    here = place_at(me["x"], me["y"])
    if here:
        where = f"You are at the {label(here)}."
    elif me["destination"]:
        where = f"You are on the way to the {label(me['destination'])}."
    else:
        where = "You are outside, between places."
    others = [
        VILLAGERS[v["name"]].title
        for v in world["villagers"]
        if v["name"] != name and nearby((me["x"], me["y"]), (v["x"], v["y"]))
    ]
    places = ", ".join(
        f"{label(p)} {steps_between(me['x'], me['y'], p)} steps" for p in PLACES if p != here
    )
    lines = [
        f"Day {day}, {time}, {period}. {where}",
        f"Nearby: {', '.join(others) if others else 'nobody'}.",
        f"Places: {places}.",
        "Heard since your last turn:",
        *([_heard(e, name) for e in me["inbox"]] or ["- nothing"]),
        "Your last events:",
        *([f"- {clock(e['tick'])[1]} {e['text']}" for e in me["events"]] or ["- none yet"]),
        "What do you do? Answer with one JSON object.",
    ]
    return "\n".join(lines)


def _place(text: str) -> str | None:
    wanted = text.strip().lower().removeprefix("the ").replace("_", " ")
    return next((key for key in PLACES if label(key) == wanted), None)


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
    if isinstance(action, Move):
        place = _place(action.place)
        if place is None:
            return wait, f"unknown place {action.place!r}"
        me = _villager(world, name)
        if place_at(me["x"], me["y"]) == place:
            return wait, f"already at the {label(place)}"
        return {"action": "move", "place": place}, None
    if isinstance(action, Say):
        text = action.text.strip()
        if not text:
            return wait, "nothing to say"
        to = None
        if action.to:
            to = next((n for n in VILLAGERS if n.lower() == action.to.strip().lower()), None)
            if to is None or to == name:
                return wait, f"unknown villager {action.to!r}"
        return {"action": "say", "text": text, "to": to}, None
    return wait, None


RULES = (
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden. "
    "Every turn is 10 minutes of village time: you read what you see and hear, then choose one "
    "action. Reply with only one JSON object and nothing else:\n"
    '{"action": "move", "place": "market"} to walk to a place (one step per turn),\n'
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to speak; "to" is optional and '
    "everyone nearby hears you,\n"
    '{"action": "wait"} to stay where you are.\n'
    "Say short things, stay in character, and answer people who talk to you."
)


def villager_agent(name: str) -> dict[str, Any]:
    """The block agent that plays a villager: one model call, then a JSON check."""
    character = VILLAGERS[name]
    decide = {
        "kind": "model",
        "name": "decide",
        "system": f"{character.persona}\n\n{RULES}",
        "message": "{previous}",
    }
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": character.title,
        "description": f"Plays {character.title} in the village.",
        "sample_prompt": "Day 1, 06:00, morning. You are at home.\nWhat do you do?",
        "config": {"reasoning": False, "blocks": [decide, check]},
    }
