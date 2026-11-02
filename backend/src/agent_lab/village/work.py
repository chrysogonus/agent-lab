"""Work, baskets, giving and the festival stalls (M11)."""

import re
from typing import Any

from agent_lab.village.build import site_at, site_refusal
from agent_lab.village.trade import BASKET_GOODS
from agent_lab.village.world import adjacent, listed, place_at, villager_named

GOODS = {"pier": "fish", "fields": "vegetables", "flower_garden": "flowers"}
BASKET_STEPS = 6  # one village hour of work, added up over everyone working a place
NO_GIVING = (
    "nobody to give it to: name someone next to you, stand on the square to set it out for the "
    "festival, or stand at the building site to set down a load"
)
SITE_TAKES = "the building site takes loads of wood, paint or saplings"
STALLS_TAKE = "the festival stalls take fish, vegetables and flowers"
REQUEST_STEPS = 6  # a villager may give to whoever asked for the goods within the last hour (M14)
_GOODS_WORDS = {
    **{w: "fish" for w in ("fish", "fishes")},
    **{w: "vegetables" for w in ("vegetable", "vegetables", "veg", "veggies")},
    **{w: "flowers" for w in ("flower", "flowers")},
    **{w: "wood" for w in ("wood", "timber", "planks")},
    "paint": "paint",
    **{w: "saplings" for w in ("sapling", "saplings")},
}

Villager = dict[str, Any]


def _villager(world: dict[str, Any], name: str) -> Villager:
    return next(v for v in world["villagers"] if v["name"] == name)


def _here(v: Villager) -> str | None:
    return place_at(v["x"], v["y"])


def goods_at(world: dict[str, Any], place: str) -> str | None:
    """What working a place gives now: fish always, vegetables from ripe or harvested fields,
    flowers from a blooming garden."""
    growth = world["growth"]
    ready = {
        "pier": True,
        "fields": growth["fields"]["stage"] in ("ripe", "harvested"),
        "flower_garden": growth["flower_garden"]["stage"] == "blooming",
    }
    return GOODS[place] if ready.get(place) else None


def work_refusal(world: dict[str, Any], name: str) -> str | None:
    """Why a villager cannot work where it stands, or None."""
    me = _villager(world, name)
    here = _here(me)
    if site_at(world, (me["x"], me["y"])):  # building comes first where a site is
        if (me["working"] and me["working"]["place"] == "site") or any(
            world["project"]["site"].values()
        ):
            return None
        return "the building site has nothing to work with yet: bring goods first"
    if me["working"] and me["working"]["place"] == here:
        return None  # keeps going, even after Jonas left the pier
    if here in ("fields", "flower_garden"):
        return None
    if here == "pier":
        jonas = _villager(world, "Jonas")
        fishing = jonas["working"] and jonas["working"]["place"] == "pier"
        return (
            None
            if name == "Jonas" or fishing
            else ("only Jonas fishes here; work with him while he fishes")
        )
    return "there is no work for you here"


def _given_by(v: Villager) -> str | None:
    """Who gave the villager the basket it holds, if it was given (and not filled since)."""
    last = next((e for e in reversed(v["events"]) if e["kind"] in ("received", "basket")), None)
    return last.get("from") if last and last["kind"] == "received" else None


def goods_asked(text: str) -> list[str]:
    """The goods a line names, in order: a hearer may give them to the speaker for an hour."""
    found: list[str] = []
    for word in re.findall(r"[a-z]+", text.lower()):
        goods = _GOODS_WORDS.get(word)
        if goods and goods not in found:
            found.append(goods)
    return found


def _wanted_by(world: dict[str, Any], me: Villager, other: str) -> bool:
    """The one it set out to see (or just found), or who asked for its goods within the hour."""
    tick, intention = world["tick"], me["intention"]
    if intention and intention["kind"] == "see" and intention["villager"] == other:
        return True
    if any(
        e["kind"] == "found" and e.get("to") == other and tick - e["tick"] <= REQUEST_STEPS
        for e in me["events"]
    ):
        return True
    return any(
        r["from"] == other and r["goods"] == me["basket"] and tick - r["tick"] <= REQUEST_STEPS
        for r in me["requests"]
    )


def give_refusal(world: dict[str, Any], name: str, to: str | None) -> str | None:
    """Why a villager cannot give its basket to `to` (or, without a name, onto the stalls)."""
    me = _villager(world, name)
    if me["basket"] is None:
        return "your hands are empty"
    if to is None:
        if site_at(world, (me["x"], me["y"])):
            return SITE_TAKES if me["basket"] in BASKET_GOODS else site_refusal(world, me["basket"])
        if _here(me) != "square":
            return NO_GIVING
        return None if me["basket"] in BASKET_GOODS else STALLS_TAKE
    other = villager_named(to)
    if other is None or other == name:
        return f"unknown villager {to!r}"
    them = _villager(world, other)
    if them["asleep"]:
        return f"{other} is asleep"
    if not adjacent((me["x"], me["y"]), (them["x"], them["y"])):
        return f"{other} is not next to you"
    if them["basket"]:
        return f"{other}'s hands are full"
    if _given_by(me) == other:  # baskets went back and forth instead of onto the stalls
        if me["basket"] in BASKET_GOODS:
            return (
                f"{other} just gave you this basket; set it out on the festival stalls on the "
                "square, or give it to someone else"
            )
        return (
            f"{other} just gave you this load; set it down at the building site, or give it to "
            "someone else"
        )
    if not _wanted_by(world, me, other):  # goods went to whoever stood near (M13 baseline)
        goods = me["basket"]
        meant = (
            "it is for the festival stalls or for someone who asks"
            if goods in BASKET_GOODS
            else "it belongs at the building site"
        )
        return f"{other} did not ask for your {goods}; {meant}"
    return None


def work_step(world: dict[str, Any]) -> list[tuple[str, str]]:
    """One step of everyone's work: tending adds up, and each village hour of work at a place
    with goods fills a basket for the longest worker there with empty hands."""
    workers: dict[str, list[Villager]] = {}
    for v in world["villagers"]:
        if v["working"] and v["working"]["place"] != "site" and not v["asleep"]:
            workers.setdefault(v["working"]["place"], []).append(v)  # the site: build_step
    baskets: list[tuple[str, str]] = []
    for place, here in workers.items():
        if place in world["tended"]:
            world["tended"][place] += len(here)
        for v in here:
            v["working"]["steps"] += 1
        goods = goods_at(world, place)
        harvest = min(world["harvest"][place] + len(here), BASKET_STEPS) if goods else 0
        empty = [v for v in here if v["basket"] is None]
        if goods and harvest == BASKET_STEPS and empty:
            v = max(empty, key=lambda v: v["working"]["steps"])  # ties: villager order
            v["basket"] = goods
            v["working"]["steps"] = 0
            harvest = 0
            baskets.append((v["name"], goods))
        world["harvest"][place] = harvest
    return baskets


def delivery_text(world: dict[str, Any], name: str) -> str | None:
    """Where a carried basket should go in autumn: villagers kept theirs instead of setting
    them out."""
    me = _villager(world, name)
    goods = me["basket"]
    if goods not in BASKET_GOODS:  # empty hands, or a load for building
        return None
    lack = "" if world["stalls"][goods] else f"The stalls still lack {goods}. "
    if _here(me) == "square":
        return (
            f"{lack}You are on the square: set out your {goods} on the festival stalls now "
            'with {"action": "give"}.'
        )
    return f"{lack}Take your basket to the square and set it out on the festival stalls."


def stalls_text(stalls: dict[str, int]) -> str:
    """What the festival stalls hold and still lack."""
    held = [g for g in GOODS.values() if stalls[g]]
    lacking = [g for g in GOODS.values() if not stalls[g]]
    text = "The festival stalls on the square " + (f"hold {listed(held)}" if held else "are empty")
    return text + (f"; they still lack {listed(lacking)}." if lacking else ".")
