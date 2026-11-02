"""The daily trader and what villagers carry (FR-001 to FR-003)."""

import pytest

from agent_lab.village.trade import carried_text


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
