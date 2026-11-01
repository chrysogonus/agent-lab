"""Work, baskets, giving and the festival stalls (M11)."""

from typing import Any

from agent_lab.village.world import adjacent, place_at, villager_named

GOODS = {"pier": "fish", "fields": "vegetables", "flower_garden": "flowers"}
BASKET_STEPS = 6  # one village hour of work, added up over everyone working a place
NO_GIVING = (
    "nobody to give it to: name someone next to you, or stand on the square to set it out for "
    "the festival"
)

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


def give_refusal(world: dict[str, Any], name: str, to: str | None) -> str | None:
    """Why a villager cannot give its basket to `to` (or, without a name, onto the stalls)."""
    me = _villager(world, name)
    if me["basket"] is None:
        return "your hands are empty"
    if to is None:
        return None if _here(me) == "square" else NO_GIVING
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
    return None


def work_step(world: dict[str, Any]) -> list[tuple[str, str]]:
    """One step of everyone's work: tending adds up, and each village hour of work at a place
    with goods fills a basket for the longest worker there with empty hands."""
    workers: dict[str, list[Villager]] = {}
    for v in world["villagers"]:
        if v["working"] and not v["asleep"]:
            workers.setdefault(v["working"]["place"], []).append(v)
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


def listed(items: list[str]) -> str:
    return " and ".join([", ".join(items[:-1]), items[-1]] if len(items) > 1 else items)


def stalls_text(stalls: dict[str, int]) -> str:
    """What the festival stalls hold and still lack."""
    held = [g for g in GOODS.values() if stalls[g]]
    lacking = [g for g in GOODS.values() if not stalls[g]]
    text = "The festival stalls on the square " + (f"hold {listed(held)}" if held else "are empty")
    return text + (f"; they still lack {listed(lacking)}." if lacking else ".")
