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
from agent_lab.village.world import adjacent, label, listed, place_at

MOST = 6  # entries shown: the list stays short

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
        if buy_refusal(world, name, wanted) is None:
            left = trader["stock"][wanted]
            why = f"trade your basket for a load; the trader has {left} left"
            found.append(({"action": "buy", "goods": wanted}, why))
    if goods and give_refusal(world, name, None) is None:
        why = (
            f"set down your {carried_text(goods)} at the building site"
            if at_site
            else f"set out your {goods} on the festival stalls"
        )
        found.append(({"action": "give"}, why))
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


def can_do_lines(world: dict[str, Any], name: str) -> list[str]:
    """The observation's section."""
    entries = can_do(world, name)
    lines = [f"- {json.dumps(action, ensure_ascii=False)}: {why}" for action, why in entries]
    return [
        "What you can do here:",
        *(lines or ["- nothing here; walk somewhere with move, or find someone"]),
    ]
