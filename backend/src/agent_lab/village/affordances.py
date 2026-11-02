"""What a villager can do where it stands, as the exact answers the village would accept
(specs/014-better-villagers/research.md §2).

Pure, and built from the same refusals the parser uses, so it never offers what would be refused.
It replaces the hints M11 and M12 added one by one.
"""

import json
from typing import Any

from agent_lab.village.build import needs_left, site_at
from agent_lab.village.trade import BUILDING_GOODS, buy_refusal, carried_text
from agent_lab.village.work import give_refusal, goods_at, work_refusal
from agent_lab.village.world import (
    adjacent,
    clock,
    door,
    hhmm,
    label,
    listed,
    minute_of_day,
    place_at,
)

MOST = 6  # entries shown: the list stays short
DUE_SOON = 30  # minutes: a talker whose plan takes it elsewhere this soon is offered to leave

Entry = tuple[dict[str, Any], str]


def _villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def _loads(loads: dict[str, int]) -> str:
    return listed([f"{n} {goods}" for goods, n in loads.items() if n])


def can_do(world: dict[str, Any], name: str) -> list[Entry]:
    """(answer, why) for each action accepted now: work, build, bring, buy, give, say."""
    me = _villager(world, name)
    here = place_at(me["x"], me["y"])
    at_site = site_at(world, (me["x"], me["y"]))
    project, goods = world["project"], me["basket"]
    needed = bool(goods) and bool(needs_left(world).get(goods or ""))
    found: list[Entry] = []
    if here and not at_site and work_refusal(world, name) is None:
        fills = goods_at(world, here)
        hour = f"fills a basket of {fills}" if fills else "tends them"
        found.append(
            ({"action": "work"}, f"you can work the {label(here)} here; an hour of work {hour}")
        )
    if project and any(project["site"].values()):
        found.append(({"action": "build"}, f"the building site holds {_loads(project['site'])}"))
    elif needed and at_site:
        found.append(({"action": "build"}, f"you can set down your {goods} and build with them"))
    if needed:
        found.append(({"action": "bring"}, f"the building site still needs the {goods} you carry"))
    trader = world["trader"]
    for wanted in BUILDING_GOODS if trader else ():
        if needs_left(world).get(wanted) and buy_refusal(world, name, wanted) is None:
            left = trader["stock"][wanted]
            why = f"trade your basket for a load; the trader has {left} left"
            found.append(({"action": "buy", "goods": wanted}, why))
    if goods and give_refusal(world, name, None) is None:
        if at_site:
            why = f"set down your {carried_text(goods)} at the building site"
        elif world["stalls"][goods]:
            why = f"set out your {goods} on the festival stalls"
        else:  # as the M11 hint said it: without it, baskets stayed in hand (M14 checks)
            why = f"the festival stalls still lack {goods}: set yours out now"
        found.append(({"action": "give"}, why))
    due = _due_elsewhere(world, me)
    talking = any(name in (c["a"], c["b"]) for c in world["conversations"])
    if due and due["villager"]:  # find them; talking, say goodbye and go
        why = f"your plan has you see {due['villager']} at {hhmm(due['minute'])}"
        kind = "goodbye" if talking else "find"
        found.append(({"action": kind, "villager": due["villager"]}, why))
    elif due and talking:  # not talking, it simply moves: the places are listed
        where = "home" if due["place"] == "home" else label(due["place"])
        at = "home" if due["place"] == "home" else f"at the {where}"
        why = f"your plan has you {at} at {hhmm(due['minute'])}"
        found.append(({"action": "goodbye", "place": where}, why))
    for v in world["villagers"]:
        if (
            v is not me
            and not v["asleep"]
            and not me["asleep"]
            and adjacent((me["x"], me["y"]), (v["x"], v["y"]))
            and sorted([name, v["name"]]) not in world["talked_out"]
        ):
            found.append(
                ({"action": "say", "to": v["name"], "text": "…"}, f"{v['name']} is next to you")
            )
    return found[:MOST]


def _due_elsewhere(world: dict[str, Any], me: dict[str, Any]) -> dict[str, Any] | None:
    """Today's plan entry for now or the next half hour, when it is somewhere else or someone
    not next to the villager."""
    plan, tick = me["plan"], world["tick"]
    if not plan or plan["day"] != clock(tick)[0]:
        return None
    soon = minute_of_day(tick) + DUE_SOON
    entries = [e for e in plan["entries"] if (e["place"] or e["villager"]) and e["minute"] <= soon]
    if not entries:
        return None
    entry = entries[-1]
    if entry["villager"]:
        other = _villager(world, entry["villager"])
        return None if adjacent((me["x"], me["y"]), (other["x"], other["y"])) else entry
    if entry["place"] == "home":
        return None if (me["x"], me["y"]) == door(me["name"]) else entry
    if entry["place"] == "site":
        return None if site_at(world, (me["x"], me["y"])) else entry
    return None if place_at(me["x"], me["y"]) == entry["place"] else entry


def can_do_lines(world: dict[str, Any], name: str) -> list[str]:
    """The observation's section."""
    entries = can_do(world, name)
    lines = [f"- {json.dumps(action, ensure_ascii=False)}: {why}" for action, why in entries]
    return [
        "What you can do here:",
        *(lines or ["- nothing here; walk somewhere with move, or find someone"]),
    ]
