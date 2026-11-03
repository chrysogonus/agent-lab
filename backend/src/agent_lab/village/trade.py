"""The daily trader at the market, and what villagers carry
(specs/012-building-together/research.md §1-§2)."""

import random
from typing import Any

from agent_lab.village.world import clock, hhmm, listed, minute_of_day, place_at

BASKET_GOODS = ("fish", "vegetables", "flowers")  # from work, M11
BUILDING_GOODS = ("wood", "paint", "saplings")  # from the trader
TRADER_ARRIVES = 9 * 60
TRADER_LEAVES = 14 * 60
_STOCK = {"wood": (2, 6), "paint": (1, 3), "saplings": (0, 3)}


def carried_text(goods: str) -> str:
    """ "basket of fish" or "load of wood": a villager carries one of either at a time."""
    return f"{'basket' if goods in BASKET_GOODS else 'load'} of {goods}"


def goods_named(text: str) -> str:
    return text.strip().lower()


def trader_stock(day: int) -> dict[str, int]:
    """What the day's trader brings: the same every time the day comes, like the weather."""
    rng = random.Random(f"trader {day}")  # noqa: S311 -- reproducible stock, not security
    return {goods: rng.randint(low, high) for goods, (low, high) in _STOCK.items()}


def trader_due(world: dict[str, Any]) -> str | None:
    """ "arrive" or "leave" when the trader comes or goes at this step, else None."""
    day, minute, trader = clock(world["tick"])[0], minute_of_day(world["tick"]), world["trader"]
    if TRADER_ARRIVES <= minute < TRADER_LEAVES and (trader is None or trader["day"] != day):
        return "arrive"
    if trader and (minute >= TRADER_LEAVES or trader["day"] != day):
        return "leave"
    return None


def _villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def _plain(text: str) -> str:
    words = text.strip().lower().split()
    return " ".join(words[1:] if words and words[0] in ("a", "an", "the") else words)


def curiosity_named(world: dict[str, Any], text: str) -> str | None:
    """The peddler's curiosity ("a lantern") when `text` names it and the peddler is here (M15)."""
    peddler = next(
        (h for h in world["happenings"] if h["kind"] == "peddler" and h["state"] == "here"),
        None,
    )
    goods: str | None = peddler and peddler["details"]["goods"]
    return goods if goods and _plain(goods) == _plain(text) else None


def buy_refusal(world: dict[str, Any], name: str, goods: str) -> str | None:
    """Why a villager cannot trade its basket for a load of `goods` (or the peddler's curiosity)
    now, or None."""
    if curiosity_named(world, goods):
        me = _villager(world, name)
        if place_at(me["x"], me["y"]) != "square":
            return "the peddler is at the square"
        if me["basket"] is None:
            return "you have nothing to trade: bring a basket"
        if me["basket"] not in BASKET_GOODS:
            return f"the peddler takes a basket, not a {carried_text(me['basket'])}"
        return None
    goods, me, trader = goods_named(goods), _villager(world, name), world["trader"]
    if goods not in BUILDING_GOODS:
        return f"the trader sells {listed(list(BUILDING_GOODS))}"
    if trader is None:
        return (
            f"no trader is at the market now; one comes every day from {hhmm(TRADER_ARRIVES)} "
            f"to {hhmm(TRADER_LEAVES)}"
        )
    if place_at(me["x"], me["y"]) != "market":
        return "the trader is at the market"
    if not trader["stock"][goods]:
        return f"the trader has no {goods} left"
    if me["basket"] is None:
        return "you have nothing to trade: bring a basket"
    if me["basket"] not in BASKET_GOODS:
        return f"you already carry a {carried_text(me['basket'])}"
    return None


def trader_text(world: dict[str, Any]) -> str:
    """What a villager knows about the trader: coming, here (with its goods) or gone."""
    trader, leaves = world["trader"], hhmm(TRADER_LEAVES)
    if trader:
        stock = [f"{goods} ({n})" for goods, n in trader["stock"].items() if n]
        if not stock:
            return f"A trader is at the market until {leaves} but has sold everything."
        return (
            f"A trader is at the market until {leaves}, selling {listed(stock)}; it takes one "
            f"basket of {listed(list(BASKET_GOODS)).replace(' and ', ' or ')} for each load."
        )
    if minute_of_day(world["tick"]) < TRADER_LEAVES:
        return f"A trader comes to the market today from {hhmm(TRADER_ARRIVES)} to {leaves}."
    return f"The trader has left; the next one comes tomorrow at {hhmm(TRADER_ARRIVES)}."
