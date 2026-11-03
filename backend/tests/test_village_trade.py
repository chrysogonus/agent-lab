"""The daily trader and what villagers carry (FR-001 to FR-003)."""

from typing import Any

import pytest

from agent_lab.village.trade import (
    buy_refusal,
    carried_text,
    curiosity_named,
    trader_due,
    trader_stock,
    trader_text,
)
from agent_lab.village.world import new_world, place_cells

MARKET = place_cells("market")[0]


@pytest.mark.parametrize(
    ("goods", "text"),
    [
        ("fish", "basket of fish"),
        ("vegetables", "basket of vegetables"),
        ("flowers", "basket of flowers"),
        ("wood", "load of wood"),
        ("paint", "load of paint"),
        ("saplings", "load of saplings"),
    ],
)
def test_carried_text(goods: str, text: str) -> None:
    assert carried_text(goods) == text


def world_at(minute: int, day: int = 2, **changes: Any) -> dict[str, Any]:
    """Everyone awake at its door at `minute` of `day`; Lina at the market with fish."""
    world = new_world()
    world["tick"] = ((day - 1) * 1440 + minute - 270) // 10
    for v in world["villagers"]:
        v["asleep"] = False
    world["villagers"][3] |= {"x": MARKET[0], "y": MARKET[1], "basket": "fish"}
    return world | changes


def test_the_stock_is_the_same_every_time_the_day_comes() -> None:
    for day in range(1, 60):
        stock = trader_stock(day)
        assert stock == trader_stock(day)
        assert 2 <= stock["wood"] <= 6 and 1 <= stock["paint"] <= 3 and 0 <= stock["saplings"] <= 3
    assert len({tuple(trader_stock(d).values()) for d in range(1, 60)}) > 5


@pytest.mark.parametrize(
    ("minute", "trader", "due"),
    [
        (8 * 60 + 50, None, None),
        (9 * 60, None, "arrive"),
        (11 * 60, None, "arrive"),  # loaded in the middle of the window
        (11 * 60, {"day": 2, "stock": {}}, None),
        (13 * 60 + 50, {"day": 2, "stock": {}}, None),
        (14 * 60, {"day": 2, "stock": {}}, "leave"),
        (14 * 60, None, None),
        (10 * 60, {"day": 1, "stock": {}}, "arrive"),  # yesterday's never left: today's comes
        (8 * 60, {"day": 1, "stock": {}}, "leave"),
    ],
)
def test_trader_due(minute: int, trader: dict[str, Any] | None, due: str | None) -> None:
    assert trader_due(world_at(minute, trader=trader)) == due


def test_buy_refusals_in_order() -> None:
    here = {"day": 2, "stock": {"wood": 2, "paint": 0, "saplings": 1}}
    world = world_at(10 * 60, trader=here)
    assert buy_refusal(world, "Lina", "stone") == "the trader sells wood, paint and saplings"
    assert buy_refusal(world_at(15 * 60), "Lina", "wood") == (
        "no trader is at the market now; one comes every day from 09:00 to 14:00"
    )
    assert buy_refusal(world, "Hilde", "wood") == "the trader is at the market"
    assert buy_refusal(world, "Lina", "paint") == "the trader has no paint left"
    world["villagers"][3]["basket"] = None
    assert buy_refusal(world, "Lina", "wood") == "you have nothing to trade: bring a basket"
    world["villagers"][3]["basket"] = "wood"
    assert buy_refusal(world, "Lina", "wood") == "you already carry a load of wood"
    world["villagers"][3]["basket"] = "flowers"
    assert buy_refusal(world, "Lina", "wood") is None
    assert buy_refusal(world, "Lina", "Wood ") is None  # as the model may write it


def test_trader_text() -> None:
    assert (
        trader_text(world_at(7 * 60)) == "A trader comes to the market today from 09:00 to 14:00."
    )
    here = {"day": 2, "stock": {"wood": 4, "paint": 2, "saplings": 1}}
    assert trader_text(world_at(10 * 60, trader=here)) == (
        "A trader is at the market until 14:00, selling wood (4), paint (2) and saplings (1); it "
        "takes one basket of fish, vegetables or flowers for each load."
    )
    sold = {"day": 2, "stock": {"wood": 0, "paint": 0, "saplings": 0}}
    assert trader_text(world_at(10 * 60, trader=sold)) == (
        "A trader is at the market until 14:00 but has sold everything."
    )
    assert trader_text(world_at(15 * 60)) == (
        "The trader has left; the next one comes tomorrow at 09:00."
    )


# --- M15: the peddler's curiosity (FR-003, FR-005) ---


def peddler(state: str = "here", goods: str = "a lantern") -> dict[str, Any]:
    return {
        "kind": "peddler",
        "place": "square",
        "cell": list(place_cells("square")[0]),
        "state": state,
        "details": {"text": f"a peddler with {goods}", "goods": goods},
        "by": None,
    }


def test_the_peddler_trades_its_curiosity_for_a_basket() -> None:
    world = world_at(11 * 60)
    world["happenings"] = [peddler()]
    lina = world["villagers"][3]
    assert buy_refusal(world, "Lina", "lantern") == "the peddler is at the square"
    lina |= {"x": place_cells("square")[1][0], "y": place_cells("square")[1][1]}
    assert buy_refusal(world, "Lina", "a lantern") is None
    assert curiosity_named(world, "The Lantern") == "a lantern"
    lina["basket"] = "wood"
    assert buy_refusal(world, "Lina", "lantern") == "the peddler takes a basket, not a load of wood"
    lina["basket"] = None
    assert buy_refusal(world, "Lina", "lantern") == "you have nothing to trade: bring a basket"
    world["happenings"] = [peddler("dealt")]
    assert curiosity_named(world, "lantern") is None
    assert buy_refusal(world, "Lina", "lantern") == "the trader sells wood, paint and saplings"
