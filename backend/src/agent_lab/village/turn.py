"""One villager's decision: what it observes, and the action its answer becomes."""

import json
import re
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from agent_lab.village.affordances import can_do_lines
from agent_lab.village.build import needs_left, project_text, site_at, site_cells
from agent_lab.village.intention import intention_text
from agent_lab.village.meeting import meeting_text
from agent_lab.village.memory import recall, when
from agent_lab.village.plan import plan_lines
from agent_lab.village.seasons import WEATHER_TEXT, date, date_text, growth_text, weather
from agent_lab.village.trade import buy_refusal, carried_text, goods_named, trader_text
from agent_lab.village.work import give_refusal, stalls_text, work_refusal
from agent_lab.village.world import (
    PLACES,
    VILLAGERS,
    adjacent,
    clock,
    door,
    festival_lines,
    hhmm,
    label,
    minute_of_day,
    place_at,
    place_cells,
    place_named,
    sees,
    steps_to,
    usual_place,
    villager_named,
)

SPEECH_SHOWN = 200  # characters of a line shown on the map and heard by others
SAID_KEPT = 3  # a villager's own last lines it may not repeat


class Move(BaseModel):
    action: Literal["move"]
    place: str
    purpose: str | None = None  # M14: why, kept with the intention


class Find(BaseModel):
    action: Literal["find"]
    villager: str
    say: str | None = None  # M14: said on reaching them
    purpose: str | None = None


class Say(BaseModel):
    action: Literal["say"]
    text: str
    to: str | None = None


class Goodbye(BaseModel):
    action: Literal["goodbye"]
    text: str | None = None
    place: str | None = None  # where it goes next (M9)
    villager: str | None = None  # or whom it goes looking for


class Work(BaseModel):
    action: Literal["work"]
    place: str | None = None  # M14: walk there first; without it, work here
    until: str | None = None  # "HH:MM"
    purpose: str | None = None


class Build(BaseModel):
    action: Literal["build"]  # M14: go to the building site and build
    until: str | None = None
    purpose: str | None = None


class Bring(BaseModel):
    action: Literal["bring"]  # M14: take the load carried to the building site, set it down
    purpose: str | None = None


class Give(BaseModel):
    action: Literal["give"]
    to: str | None = None  # without a name: onto the festival stalls


class Buy(BaseModel):
    action: Literal["buy"]
    goods: str  # wood, paint or saplings, for the basket carried (M12)


class Wait(BaseModel):
    action: Literal["wait"]


type Action = Move | Find | Say | Goodbye | Work | Build | Bring | Give | Buy | Wait
ACTION = TypeAdapter[Action](Annotated[Action, Field(discriminator="action")])

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


def _routine_text(world: dict[str, Any], other: str) -> str:
    usual = usual_place(other, world["tick"])
    if usual == "home":
        return "at home asleep at this hour (their routine)"
    return f"usually at the {label(usual)} around now (their routine)"


def _belief_where(belief: dict[str, Any]) -> tuple[str, str]:
    return _place_phrase(belief["where"], (belief["cell"][0], belief["cell"][1])), clock(
        belief["tick"]
    )[1]


def belief_text(world: dict[str, Any], name: str, other: str) -> str:
    """Where `name` thinks `other` is, and how it knows."""
    belief = villager_of(world, name)["beliefs"].get(other)
    if not belief:
        return _routine_text(world, other)
    where, when = _belief_where(belief)
    if belief["source"] == "seen":
        return f"{where} (seen {when})"
    return f"{where} (heard from {belief['from']} at {when})"


def seen_text(world: dict[str, Any], name: str, other: str) -> str:
    """Where `name` last saw `other`, or their routine: what it knows for itself."""
    belief = villager_of(world, name)["beliefs"].get(other)
    if not belief or belief["source"] != "seen":
        return _routine_text(world, other)
    where, when = _belief_where(belief)
    return f"{where} (seen {when})"


def where_text(world: dict[str, Any], v: Villager) -> str:
    here = place_at(v["x"], v["y"])
    if v["asleep"]:
        return "You are asleep at home."
    if site_at(world, cell(v)):  # some sites lie on a place: the market, the town hall
        return "You are at the building site" + (f", at the {label(here)}." if here else ".")
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


def _usually(name: str, tick: int) -> str:
    usual = usual_place(name, tick)
    return f" At this hour you are usually at the {label(usual)}." if usual != "home" else ""


def _heard(entry: dict[str, Any], listener: str) -> str:
    to = entry.get("to")
    who = entry["from"] if not to else f"{entry['from']} to {'you' if to == listener else to}"
    return f'- {who}: "{entry["text"]}"'


GROWING = ("fields", "flower_garden")


def same_line(a: str, b: str) -> bool:
    """The same words, whatever the case, spaces and punctuation."""
    return re.sub(r"[\W_]+", "", a.lower()) == re.sub(r"[\W_]+", "", b.lower())


def _repeats(v: Villager, text: str) -> bool:
    return any(same_line(text[:SPEECH_SHOWN], line) for line in v["said"])  # kept as spoken


def _knows(world: dict[str, Any], name: str, place: str) -> bool:
    """A villager knows how a growing place is doing if it works there or can see it."""
    me = cell(villager_of(world, name))
    return VILLAGERS[name].work == place or any(sees(me, c) for c in place_cells(place))


def observation(world: dict[str, Any], name: str) -> str:
    """The changing world as one villager sees it; persona and rules live in its agent."""
    me = villager_of(world, name)
    character = VILLAGERS[name]
    day, time, period = clock(world["tick"])
    minute = minute_of_day(world["tick"])
    next_to = awake_neighbours(world, name)
    in_sight = [
        f"{v['name']} ({max(abs(v['x'] - me['x']), abs(v['y'] - me['y']))} steps away)"
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
    if world["project"] and not site_at(world, (x, y)):
        places.append(f"building site {steps_to(x, y, site_cells(world))} steps")
    goal = goal_text(me["goal"])
    matters = {*next_to, *talking}  # whose memories matter right now
    if me["goal"] and me["goal"]["kind"] == "find":
        matters.add(me["goal"]["villager"])
    remembered = recall(me["memories"], world["tick"], matters, here)
    views = me["views"]
    heard = {
        o: b
        for o, b in me["beliefs"].items()
        if b["source"] == "heard" and o in VILLAGERS and o != name
    }
    lines = [
        "What you know for sure:",
        f"Day {day} ({date_text(day)}), {time}, {period}. {WEATHER_TEXT[weather(day)]}; "
        "this is the real weather.",
        *festival_lines(world["tick"], name),
        where_text(world, me) + (" You are working here." if me["working"] else ""),
        *([f"You carry a {carried_text(me['basket'])}."] if me["basket"] else []),
        trader_text(world),
        meeting_text(world, name),
        *project_text(world, name),
        *([stalls_text(world["stalls"])] if date(day)[1] == "autumn" else []),
        *[growth_text(p, world["growth"]) for p in GROWING if _knows(world, name, p)],
        f"You get up at {hhmm(character.wake)} and go to bed at {hhmm(character.bed)}."
        + _usually(name, world["tick"]),
        *(
            plan_lines(me["plan"]["entries"], minute)
            if me["plan"] and me["plan"]["day"] == day
            else []
        ),
        *([f"You are {goal}."] if goal else []),
        intention_text(world, me),
        f"Next to you: {', '.join(next_to) or 'nobody'}.",  # M14: names, as answers use them
        f"In sight: {', '.join(in_sight) or 'nobody else'}.",
        f"{conversation}."
        + (
            f" You have talked a long time with {', '.join(tired)}; say goodbye or go on."
            if tired
            else ""
        ),
        f"Places: {', '.join(places)}.",
        *can_do_lines(world, name),
        "What you said lately:",
        *([f'- "{line}"' for line in me["said"]] or ["- nothing yet"]),
        "Where the others are, as far as you know:",
        *[
            f"- {o}: {seen_text(world, name, o)}"
            + (f"; you think: {views[o]['text']}" if o in views else "")
            for o in VILLAGERS
            if o != name
        ],
        "What others told you (claims; they may be wrong):",
        "Said to you since your last turn:",
        *([_heard(e, name) for e in me["inbox"]] or ["- nothing"]),
        "Heard about where others are:",
        *(
            [
                f"- {o}: {where} ({b['from']} said at {when})"
                for o, b in heard.items()
                for where, when in [_belief_where(b)]
            ]
            or ["- nothing"]
        ),
        "What you have learned:",
        *([f"- {item['text']}" for item in me["learnings"]] or ["- nothing yet"]),
        "What you remember:",
        *([f"- {when(m['tick'])} {m['text']}" for m in remembered] or ["- nothing yet"]),
        "Your last events:",
        *([f"- {clock(e['tick'])[1]} {e['text']}" for e in me["events"]] or ["- none yet"]),
        "What do you do? Answer with one JSON object.",
    ]
    return "\n".join(lines)


def parse_action(
    answer: str | None, world: dict[str, Any], name: str
) -> tuple[dict[str, Any], str | None]:
    """The action to apply and, when it had to become `wait`, the reason."""
    wait = {"action": "wait"}
    if not answer:
        return wait, "no answer"
    try:
        action = ACTION.validate_python(_slips(json.loads(answer)))
    except json.JSONDecodeError:
        return wait, "the answer is not JSON"
    except ValidationError as exc:
        return wait, f"not a valid action: {exc.errors()[0]['msg']}"
    extra: dict[str, Any] = {}
    if isinstance(action, Work | Build) and action.until:
        until, why = _until(world, action.until)
        if why:
            return wait, why
        extra |= {} if until is None else {"until": until}
    if isinstance(action, Move | Find | Work | Build | Bring):
        purpose = (action.purpose or "").strip()
        extra |= {"purpose": purpose} if purpose else {}
    if isinstance(action, Move):
        place, why = _destination(world, name, action.place)
        if place is None:
            return wait, why
        return _leaving(world, name, {"action": "move", "place": place, **extra}), None
    if isinstance(action, Find):
        other, why = _seek(world, name, action.villager)
        say = (action.say or "").strip()[:SPEECH_SHOWN]
        extra |= {"say": say} if say else {}
        if other is None:
            return wait, why
        return _leaving(world, name, {"action": "find", "villager": other, **extra}), None
    if isinstance(action, Work):
        place, why = _work_place(world, name, action.place)
        if place == "elsewhere-site":
            action = Build(action="build")
        else:
            if why:
                return wait, why
            return _leaving(world, name, {"action": "work", "place": place, **extra}), None
    if isinstance(action, Build):
        why = _build_refusal(world, name)
        if why:
            return wait, why
        at_site = site_at(world, cell(villager_of(world, name)))
        if at_site:
            return {"action": "work", "place": "site", **extra}, None
        return _leaving(world, name, {"action": "build", **extra}), None
    if isinstance(action, Bring):
        why = _bring_refusal(world, name)
        return (wait, why) if why else (_leaving(world, name, {"action": "bring", **extra}), None)
    if isinstance(action, Buy):
        why = buy_refusal(world, name, action.goods)
        if why:
            return wait, why
        paid = villager_of(world, name)["basket"]
        return {"action": "buy", "goods": goods_named(action.goods), "paid": paid}, None
    if isinstance(action, Give):
        to = action.to or None
        if to and re.search(r"\bstalls?\b|\bsite\b", to.lower()):
            to = None  # "festival stalls", "building site": the place, not a villager
        why = give_refusal(world, name, to)
        if why:
            return wait, why
        goods = villager_of(world, name)["basket"]
        return {"action": "give", "to": to and villager_named(to), "goods": goods}, None
    text = (action.text or "").strip() if isinstance(action, Say | Goodbye) else ""
    if isinstance(action, Goodbye):
        repeated = _repeats(villager_of(world, name), text)
        goodbye: dict[str, Any] = {"action": "goodbye", "text": None if repeated else text or None}
        if action.place:
            place, why = _destination(world, name, action.place)
            goodbye |= {"place": place} if place else {"ignored": why}
        elif action.villager:
            other, why = _seek(world, name, action.villager)
            goodbye |= {"villager": other} if other else {"ignored": why}
        return goodbye, None
    if isinstance(action, Say):
        if not text:
            return wait, "nothing to say"
        if _repeats(villager_of(world, name), text):
            return wait, "you already said that"
        to = None
        if action.to:
            to = villager_named(action.to)
            if to is None or to == name:
                return wait, f"unknown villager {action.to!r}"
        next_to = awake_neighbours(world, name)
        if to and to not in next_to:
            them = villager_of(world, to)
            if them["asleep"] or not sees(cell(villager_of(world, name)), cell(them)):
                return wait, f"{to} is not next to you"
            seek = {"action": "find", "villager": to, "say": text[:SPEECH_SHOWN]}
            return _leaving(world, name, seek), None
        if not next_to:
            return wait, "nobody is next to you"
        hearers = [to] if to else next_to
        if all(talked_out(world, name, h) for h in hearers):
            return wait, (
                f"you have talked a long time with {', '.join(hearers)}; say goodbye or go on"
            )
        return {"action": "say", "text": text, "to": to}, None
    return wait, None


def _destination(world: dict[str, Any], name: str, text: str) -> tuple[str | None, str | None]:
    """A place key (or "home") to walk to, or why not."""
    me = villager_of(world, name)
    place = place_named(text)
    if place is None:
        return None, f"unknown place {text!r}"
    if place == "home" and cell(me) == door(name):
        return None, "already at your home"
    if place == "site":
        if world["project"] is None:
            return None, "nothing is being built"
        if site_at(world, cell(me)):
            return None, "already at the building site"
        return place, None
    if place != "home" and place_at(me["x"], me["y"]) == place:
        return None, f"already at the {label(place)}"
    return place, None


def _leaving(world: dict[str, Any], name: str, action: dict[str, Any]) -> dict[str, Any]:
    """Setting out elsewhere while talking: a goodbye that sets out, instead of the refusal
    "say goodbye first" (M14). Work here goes on, and talkers going the same way walk on
    together."""
    talking = partners(world, name)
    if not talking:
        return action
    me = villager_of(world, name)
    here = "site" if site_at(world, cell(me)) else place_at(me["x"], me["y"])
    kind = action["action"]
    place = {"move": action.get("place"), "work": action.get("place")}.get(kind, "site")
    if kind in ("work", "bring") and place == here:
        return action
    if kind != "find" and all(
        (intention := villager_of(world, p)["intention"]) and intention["place"] == place
        for p in talking
    ):
        return action
    if kind in ("move", "find"):
        return {
            "action": "goodbye",
            "text": None,
            **{k: v for k, v in action.items() if k != "action"},
        }
    return {"action": "goodbye", "text": None, "then": action}


def _slips(data: object) -> object:
    """Answers small models give a few times a day for a move: "walk", "go", "home"."""
    if not isinstance(data, dict):
        return data
    found = cast(dict[str, Any], data)
    if not isinstance(found.get("action"), str):
        return found
    action = str(found["action"]).strip().lower()
    if action in ("walk", "go"):
        return {**found, "action": "move"}
    if action in ("home", "go home"):
        return {"action": "move", "place": "home"}
    return found


def _until(world: dict[str, Any], text: str) -> tuple[int | None, str | None]:
    """A minute of the day later than now, from "HH:MM", or why not."""
    found = re.fullmatch(r"(\d{1,2}):(\d{2})", text.strip())
    if not found or int(found[1]) > 23 or int(found[2]) > 59:
        return None, f'"until" must be a time like 12:00, not {text!r}'
    until, now = int(found[1]) * 60 + int(found[2]), minute_of_day(world["tick"])
    if until < now:
        return None, f'"until" must be later than now ({hhmm(now)})'
    return (None if until == now else until), None  # until now: no end time


def _work_place(
    world: dict[str, Any], name: str, text: str | None
) -> tuple[str | None, str | None]:
    """Where a villager works, here or at a named place it walks to first, or why not.
    "elsewhere-site": the building site away from here, which is building."""
    me = villager_of(world, name)
    here = "site" if site_at(world, cell(me)) else place_at(me["x"], me["y"])
    place = here if text is None else place_named(text)
    if text is not None and place is None:
        return None, f"unknown place {text!r}"
    if place is None or place == here:
        return (None, why) if (why := work_refusal(world, name)) else (here, None)
    if place == "home":
        return None, "there is no work for you at your home"
    if place == "site" and here != "site":
        return "elsewhere-site", None
    x, y = place_cells(place)[0]  # as if it stood there, not yet working
    there = {**me, "x": x, "y": y, "working": None}
    moved = {**world, "villagers": [there if v is me else v for v in world["villagers"]]}
    why = work_refusal(moved, name)
    if why:
        return None, why.replace("for you here", f"for you at the {label(place)}")
    return place, None


def _build_refusal(world: dict[str, Any], name: str) -> str | None:
    project = world["project"]
    if project is None:
        return "nothing is being built"
    me = villager_of(world, name)
    working = me["working"] and me["working"]["place"] == "site"
    if working or any(project["site"].values()) or needs_left(world).get(me["basket"] or ""):
        return None
    return "the building site has nothing to work with yet: bring goods first"


def _bring_refusal(world: dict[str, Any], name: str) -> str | None:
    if world["project"] is None:
        return "nothing is being built"
    goods = villager_of(world, name)["basket"]
    if goods is None:
        return "your hands are empty"
    return None if needs_left(world).get(goods) else "you carry nothing the building site needs"


def _seek(world: dict[str, Any], name: str, text: str) -> tuple[str | None, str | None]:
    """A villager to go looking for, or why not."""
    other = villager_named(text)
    if other is None or other == name:
        return None, f"unknown villager {text!r}"
    if other in awake_neighbours(world, name):
        hint = f'{{"action": "say", "to": "{other}", ...}}'
        return None, f"{other} is right next to you; say what you want: {hint}"
    return other, None


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


# Earlier rules: stored villager agents still holding one verbatim get RULES on load.
_M7_RULES = (
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


_M9_RULES = (
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden, "
    "and everyone's own home. Time passes in steps of 10 minutes. You are asked what to do when "
    "something happens: you woke up, arrived somewhere, met someone, someone spoke to you, or a "
    "while passed. Reply with only one JSON object and nothing else:\n"
    '{"action": "move", "place": "market"} to walk to a place or "home" (a few steps every 10 '
    "minutes until you arrive),\n"
    '{"action": "find", "villager": "Lina"} to go and look for someone where you think they '
    "are,\n"
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to talk to someone standing right '
    'next to you ("to" is optional). You can only talk to people right next to you: to talk to '
    "someone else, find them first,\n"
    '{"action": "goodbye", "text": "See you later!", "place": "market"} to end a conversation '
    'and leave: "text" is optional, and "place" (or "villager": "Lina" to go looking for '
    "someone) says where you go next; leave both out to stay,\n"
    '{"action": "wait"} to go on with what you are doing.\n'
    "While you talk with someone, you both stay where you are: say goodbye before you walk "
    "off. You go home to sleep at your bedtime by yourself. Say short things, stay in "
    "character, answer people who talk to you, and say goodbye when you have said what you "
    "wanted."
)


_M11_PLAN_RULES = (
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden, "
    "and everyone's own home. Time passes in steps of 10 minutes. You are asked what to do when "
    "something happens: you woke up, arrived somewhere, met someone, someone spoke to you, or a "
    "while passed. Reply with only one JSON object and nothing else:\n"
    '{"action": "move", "place": "market"} to walk to a place or "home" (a few steps every 10 '
    "minutes until you arrive),\n"
    '{"action": "find", "villager": "Lina"} to go and look for someone where you think they '
    "are,\n"
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to talk to someone standing right '
    'next to you ("to" is optional). You can only talk to people right next to you: to talk to '
    "someone else, find them first,\n"
    '{"action": "goodbye", "text": "See you later!", "place": "market"} to end a conversation '
    'and leave: "text" is optional, and "place" (or "villager": "Lina" to go looking for '
    "someone) says where you go next; leave both out to stay,\n"
    '{"action": "wait"} to go on with what you are doing.\n'
    "While you talk with someone, you both stay where you are: say goodbye before you walk "
    "off. You go home to sleep at your bedtime by yourself. Trust what you see over what you "
    "hear; the weather you are told is the real weather. Follow your plan for the day unless "
    "something more important comes up. Say short things, stay in character, answer people who "
    "talk to you, and say goodbye when you have said what you wanted."
)


_M11_RULES = (
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden, "
    "and everyone's own home. Time passes in steps of 10 minutes. You are asked what to do when "
    "something happens: you woke up, arrived somewhere, met someone, someone spoke to you, or a "
    "while passed. Reply with only one JSON object and nothing else:\n"
    '{"action": "move", "place": "market"} to walk to a place or "home" (a few steps every 10 '
    "minutes until you arrive),\n"
    '{"action": "find", "villager": "Lina"} to go and look for someone where you think they '
    "are,\n"
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to talk to someone standing right '
    'next to you ("to" is optional). You can only talk to people right next to you: to talk to '
    "someone else, find them first,\n"
    '{"action": "goodbye", "text": "See you later!", "place": "market"} to end a conversation '
    'and leave: "text" is optional, and "place" (or "villager": "Lina" to go looking for '
    "someone) says where you go next; leave both out to stay,\n"
    '{"action": "work"} to work where you stand until you walk off: anyone may tend the fields '
    "or the flower garden, and fish at the pier with Jonas while he fishes there; an hour of "
    "work fills a basket with fish, ripe vegetables or blooming flowers,\n"
    '{"action": "give", "to": "Hilde"} to hand your basket to someone next to you, or '
    '{"action": "give"} on the square to set it out on the festival stalls,\n'
    '{"action": "wait"} to go on with what you are doing.\n'
    "While you talk with someone, you both stay where you are: say goodbye before you walk "
    "off. You go home to sleep at your bedtime by yourself. Trust what you see over what you "
    "hear; the weather you are told is the real weather. Follow your plan for the day unless "
    "something more important comes up. Say short things, stay in character, answer people who "
    "talk to you, and say goodbye when you have said what you wanted."
)


_M12_BUY_RULES = _M11_RULES.replace(
    '{"action": "wait"} to go on',
    '{"action": "buy", "goods": "wood"} at the market while the trader is there: trade the '
    "basket you carry for a load of wood, paint or saplings for building,\n"
    '{"action": "wait"} to go on',
)
_M12_MEETING_RULES = _M12_BUY_RULES.replace(
    "something more important comes up.",
    "something more important comes up. Hilde holds a town hall meeting every third day at "
    "17:00 where the village chooses what to build.",
)
_M12_SITE_RULES = _M12_MEETING_RULES.replace(
    '{"action": "wait"} to go on',
    '{"action": "move", "place": "building site"} to walk to what the village is building, '
    '{"action": "give"} at the building site to set down a load it needs, and '
    '{"action": "work"} there to build with the loads lying there,\n'
    '{"action": "wait"} to go on',
)
RULES = (  # M14: intentions, and what you can do where you are
    "You live in a small village with Hilde (the mayor), Jonas (the fisher), Greta (the farmer) "
    "and Lina (the flower girl). Places: town hall, square, market, pier, fields, flower garden, "
    "and everyone's own home. Time passes in steps of 10 minutes. Reply with only one JSON "
    "object and nothing else.\n"
    "These set you on something, and you keep doing it until it is done: the village walks you "
    "there, starts your work and sets down your load, and asks you again when it is done or "
    'something happens (you woke up, met someone, someone spoke to you). Add "purpose" to '
    "say why.\n"
    '{"action": "move", "place": "market"} to walk to a place, "home" or the "building site",\n'
    '{"action": "work", "place": "fields", "until": "12:00"} to work at a place (here, without '
    '"place") until a time (or until you stop): anyone may tend the fields or the flower garden, '
    "and fish at the pier with Jonas while he fishes there; an hour of work fills a basket with "
    "fish, ripe vegetables or blooming flowers,\n"
    '{"action": "build", "until": "15:00"} to go to the building site and build with the loads '
    "lying there,\n"
    '{"action": "bring"} to take the load you carry to the building site and set it down,\n'
    '{"action": "find", "villager": "Lina", "say": "Any flowers?"} to go to someone and say '
    'something when you reach them ("say" is optional).\n'
    "These happen at once:\n"
    '{"action": "say", "text": "Good morning!", "to": "Jonas"} to talk to someone standing right '
    'next to you ("to" is optional),\n'
    '{"action": "goodbye", "text": "See you later!", "place": "market"} to end a conversation '
    'and leave: "text" is optional, and "place" (or "villager": "Lina" to go looking for '
    "someone) says where you go next; leave both out to stay,\n"
    '{"action": "give", "to": "Hilde"} to hand what you carry to someone next to you who asked '
    'for it or whom you set out to see, or {"action": "give"} on the square to set it out on '
    "the festival stalls, or at the building site to set down a load,\n"
    '{"action": "buy", "goods": "wood"} at the market while the trader is there: trade the '
    "basket you carry for a load of wood, paint or saplings for building,\n"
    '{"action": "wait"} to go on with what you are doing.\n'
    "Each turn lists what you can do where you are. If you set out elsewhere while you talk, you "
    "say goodbye and go; if you both go the same way, you walk on together. You go home to sleep "
    "at your bedtime by yourself. Trust what you see over what you hear; the weather you are told"
    " is the real weather. Follow your plan for the day unless something more important comes up."
    " Hilde holds a town hall meeting every third day at 17:00 where the village chooses what to "
    "build. Say short things, stay in character, answer people who talk to you, and say goodbye "
    "when you have said what you wanted."
)
OLD_RULES = (
    _M7_RULES,
    _M9_RULES,
    _M11_PLAN_RULES,
    _M11_RULES,
    _M12_BUY_RULES,
    _M12_MEETING_RULES,
    _M12_SITE_RULES,
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
        "sample_prompt": "Day 1 (day 1 of spring, year 1), 05:00, morning. Sunny.\n"
        "You are at your home's door.\nWhat do you do?",
        "config": {"reasoning": False, "blocks": [decide, check]},
    }
