"""The daily trader at the market, and what villagers carry
(specs/012-building-together/research.md §1-§2)."""

BASKET_GOODS = ("fish", "vegetables", "flowers")  # from work, M11
BUILDING_GOODS = ("wood", "paint", "saplings")  # from the trader


def carried_text(goods: str) -> str:
    """ "basket of fish" or "load of wood": a villager carries one of either at a time."""
    return f"{'basket' if goods in BASKET_GOODS else 'load'} of {goods}"
