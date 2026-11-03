"""What a villager set out to do, and the next step towards it
(specs/014-better-villagers/research.md §1, data-model.md "Intention steps").

Pure: the runner applies the steps. Walking, starting work on arrival, setting a needed load
down at the site and saying a stored line need no model call; the villager is asked again when
the intention ends or something happens.
"""

from typing import Any

from agent_lab.village.boat import in_boat
from agent_lab.village.build import needs_left, site_at
from agent_lab.village.trade import carried_text
from agent_lab.village.work import work_refusal
from agent_lab.village.world import (
    adjacent,
    door,
    hhmm,
    label,
    minute_of_day,
    place_at,
    sees,
)

KINDS = ("go", "work", "build", "bring", "see", "lead", "row")
PURPOSE_KEPT = 120

Intention = dict[str, Any]
Step = dict[str, Any]
Villager = dict[str, Any]


def _villager(world: dict[str, Any], name: str) -> Villager:
    return next(v for v in world["villagers"] if v["name"] == name)


def _cell(v: Villager) -> tuple[int, int]:
    return v["x"], v["y"]


def start(world: dict[str, Any], name: str, action: dict[str, Any]) -> Intention:
    """The intention a parsed move, work, build, bring or find (or a goodbye going on) starts."""
    kind = {"move": "go", "find": "see", "goodbye": "go"}.get(action["action"], action["action"])
    if action.get("villager"):
        kind = "see"
    if kind == "lead":  # take the animal next to it (or already led) home to its owner (M15)
        me = _villager(world, name)
        animal = next(
            h
            for h in world["happenings"]
            if h["kind"] == "animal"
            and h["state"] == "here"
            and (
                h["leader"] == name
                or (h["leader"] is None and adjacent(_cell(me), tuple(h["cell"])))
            )
        )
        action = {**action, "villager": animal["concerns"]}
    place = "site" if kind in ("build", "bring") else action.get("place")
    if kind == "work" and place is None:  # work where it stands
        me = _villager(world, name)
        place = "site" if site_at(world, _cell(me)) else place_at(me["x"], me["y"])
    if kind == "work" and place == "site":
        kind = "build"  # working at the site is building, and ends when nothing is left
    purpose = (action.get("purpose") or "").strip()[:PURPOSE_KEPT] or None
    return {
        "kind": kind,
        "place": None if kind == "see" else place,
        "villager": action.get("villager") if kind in ("see", "lead") else None,
        "until": action.get("until"),
        "purpose": purpose,
        "since": world["tick"],
        "say": action.get("say") if kind == "see" else None,
    }


def _goal(place: str) -> dict[str, Any]:
    return {"kind": "home"} if place == "home" else {"kind": "place", "place": place}


def _at(world: dict[str, Any], v: Villager, place: str) -> bool:
    if place == "lake":
        return in_boat(world, v["name"])  # the lake is worked from the boat (M15)
    if place == "home":
        return _cell(v) == door(v["name"])
    if place == "site":
        return site_at(world, _cell(v))
    return place_at(v["x"], v["y"]) == place


def _working_at(v: Villager, place: str) -> bool:
    return bool(v["working"]) and v["working"]["place"] == place


def next_step(world: dict[str, Any], v: Villager) -> Step:
    """The next step of `v`'s intention; "none" while it keeps at it (or has none)."""
    intention: Intention | None = v["intention"]
    if intention is None:
        return {"kind": "none"}
    kind, place = intention["kind"], intention["place"]
    until = intention["until"]
    if until is not None and minute_of_day(world["tick"]) >= until:
        return {"kind": "done", "why": f"it is {hhmm(until)}"}
    if kind == "see":
        return _see(world, v, intention)
    if kind == "lead":
        return _lead(world, v, intention)
    if kind == "row":
        boat = world["boat"]
        aboard = boat and (v["name"] in boat["rowers"] or boat["invited"] == v["name"])
        return {"kind": "none"} if aboard else {"kind": "done", "why": "the boat trip is over"}
    project = world["project"]
    if place == "site" and project is None:
        return {"kind": "given_up", "why": "nothing is being built any more"}
    goods = v["basket"]
    needed = bool(goods) and bool(needs_left(world).get(goods))
    if kind == "bring" and not needed:
        why = "your hands are empty" if goods is None else f"the site needs no more {goods}"
        return {"kind": "given_up", "why": why}
    if kind == "build" and not needed and not any(project["site"].values()):
        return {"kind": "given_up", "why": "the building site holds nothing to build with"}
    if not _at(world, v, place):
        return {"kind": "walk", "goal": _goal(place)}
    if kind == "go":
        where = "home" if place == "home" else f"at the {label(place)}"
        return {"kind": "done", "why": f"you arrived {where}"}
    if kind == "bring":
        return {"kind": "set_down", "goods": goods, "done": f"you set down the {goods}"}
    if kind == "build" and needed:
        return {"kind": "set_down", "goods": goods}  # then build with it
    if _working_at(v, place):
        return {"kind": "none"}
    why = work_refusal(world, v["name"])
    return {"kind": "given_up", "why": why} if why else {"kind": "start_work", "place": place}


def _lead(world: dict[str, Any], v: Villager, intention: Intention) -> Step:
    owner = intention["villager"]
    animal = next(
        (h for h in world["happenings"] if h["kind"] == "animal" and h["concerns"] == owner),
        None,
    )
    if animal and animal["state"] == "dealt":
        return {"kind": "done", "why": f"{animal['details']['text']} is home"}
    if animal is None or animal["state"] != "here" or animal["leader"] != v["name"]:
        return {"kind": "given_up", "why": "the animal is gone"}
    return {
        "kind": "walk",
        "goal": {"kind": "door", "villager": owner, "target": [list(door(owner))]},
    }


def _see(world: dict[str, Any], v: Villager, intention: Intention) -> Step:
    name = intention["villager"]
    other = _villager(world, name)
    if other["asleep"]:
        return {"kind": "given_up", "why": f"{name} is asleep"}
    if adjacent(_cell(v), _cell(other)):
        found = f"you found {name}"
        if intention["say"]:
            return {"kind": "say", "to": name, "text": intention["say"], "done": found}
        return {"kind": "done", "why": found}
    if sees(_cell(v), _cell(other)):
        return {"kind": "walk", "goal": {"kind": "find", "villager": name}, "seen": True}
    if intention.get("seen"):
        belief = v["beliefs"].get(name)
        where = belief and belief["where"]
        near = f" at the {label(where)}" if where and where != "home" else ""
        return {"kind": "given_up", "why": f"you lost sight of {name}{near}"}
    return {"kind": "walk", "goal": {"kind": "find", "villager": name}}


def _phrase(intention: Intention, basket: str | None = None) -> str:
    kind, place = intention["kind"], intention["place"]
    if kind == "see":
        say = intention["say"]
        return f"see {intention['villager']}" + (f' and say "{say}"' if say else "")
    if kind == "go":
        return "go home" if place == "home" else f"go to the {label(place)}"
    if kind == "lead":
        return f"take the lost animal home to {intention['villager']}"
    if kind == "row":
        return "row the boat on the lake"
    if kind == "build":
        return "build at the building site"
    if kind == "bring":
        return f"take the {carried_text(basket) if basket else 'load'} to the building site"
    return f"work at the {label(place)}"


def described(intention: Intention, basket: str | None = None) -> str:
    """ "build at the building site until 15:00 (to plant the trees)" """
    until = intention["until"]
    text = _phrase(intention, basket) + (f" until {hhmm(until)}" if until is not None else "")
    return text + (f" ({intention['purpose']})" if intention["purpose"] else "")


def _next_text(step: Step, intention: Intention) -> str:
    kind = step["kind"]
    if kind == "walk":
        return f"walk to {intention['villager']}" if intention["kind"] == "see" else "walk there"
    if kind == "start_work":
        return "start working"
    if kind == "set_down":
        return "set down your load"
    if kind == "say":
        return f"say it to {step['to']}"
    if kind in ("done", "given_up"):
        return f"nothing more ({step['why']})"
    return "keep working" if intention["kind"] in ("work", "build") else "keep at it"


def intention_text(world: dict[str, Any], v: Villager) -> str:
    """The observation's line: "You are set on: build at the building site until 15:00 (to
    plant the trees). Next: walk there." """
    intention = v["intention"]
    if intention is None:
        return "You are not set on anything."
    step = next_step(world, v)
    return (
        f"You are set on: {described(intention, v['basket'])}. Next: {_next_text(step, intention)}."
    )


def started_text(name: str, intention: Intention, basket: str | None = None) -> str:
    return f"{name} set out to {described(intention, basket)}."


def ended_text(name: str, intention: Intention, why: str, basket: str | None = None) -> str:
    """ "Greta is done with: build at the building site until 12:00: it is 12:00." """
    return f"{name} is done with: {described(intention, basket)}: {why}."
