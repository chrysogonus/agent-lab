"""Work, baskets, giving and the festival stalls (FR-010, FR-011, FR-014, SC-003)."""

from typing import Any

import pytest

from agent_lab.village.work import (
    give_refusal,
    goods_at,
    stalls_text,
    work_refusal,
    work_step,
)
from agent_lab.village.world import label_cell, new_world, place_cells

PIER = place_cells("pier")
FIELDS = place_cells("fields")
SQUARE = label_cell("square")


def world_with(**changes: Any) -> dict[str, Any]:
    """Everyone awake at its door at 09:30 unless changed; fields ripe, garden blooming."""
    world = new_world()
    world["tick"] = 30
    world["growth"]["fields"]["stage"] = "ripe"
    world["growth"]["flower_garden"]["stage"] = "blooming"
    for v in world["villagers"]:
        v["asleep"] = False
        v.update(changes.get(v["name"], {}))
    return world


def at(cell: tuple[int, int], **more: Any) -> dict[str, Any]:
    return {"x": cell[0], "y": cell[1], **more}


def working(place: str, steps: int = 0) -> dict[str, Any]:
    return {"working": {"place": place, "steps": steps}}


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


@pytest.mark.parametrize(
    ("place", "stage", "goods"),
    [
        ("pier", None, "fish"),
        ("fields", "ripe", "vegetables"),
        ("fields", "harvested", "vegetables"),
        ("fields", "growing", None),
        ("flower_garden", "blooming", "flowers"),
        ("flower_garden", "wilting", None),
        ("market", None, None),
    ],
)
def test_goods_at_each_place_and_stage(place: str, stage: str | None, goods: str | None) -> None:
    world = world_with()
    if stage:
        world["growth"][place]["stage"] = stage
    assert goods_at(world, place) == goods


def test_work_refusals() -> None:
    world = world_with(
        Greta=at(FIELDS[0]),
        Lina=at(place_cells("flower_garden")[0]),
        Hilde=at(PIER[0]),
        Jonas=at(PIER[1]),
    )
    assert work_refusal(world, "Greta") is None
    assert work_refusal(world, "Lina") is None
    assert work_refusal(world, "Jonas") is None
    assert work_refusal(world, "Hilde") == "only Jonas fishes here; work with him while he fishes"
    villager(world, "Jonas").update(working("pier"))
    assert work_refusal(world, "Hilde") is None
    villager(world, "Hilde").update(at(SQUARE))
    assert work_refusal(world, "Hilde") == "there is no work for you here"


def test_fishing_goes_on_after_jonas_stops() -> None:
    world = world_with(Hilde=at(PIER[0], **working("pier", 2)), Jonas=at(PIER[1]))
    assert work_refusal(world, "Hilde") is None


def test_give_refusals() -> None:
    sx, sy = SQUARE
    world = world_with(
        Hilde=at((sx, sy), basket="fish"),
        Jonas=at((sx + 1, sy), basket="vegetables"),
        Greta=at((sx, sy + 1), asleep=True),
        Lina=at((sx + 5, sy)),
    )
    assert give_refusal(world, "Lina", None) == "your hands are empty"
    assert give_refusal(world, "Hilde", "Tom") == "unknown villager 'Tom'"
    assert give_refusal(world, "Hilde", "Hilde") == "unknown villager 'Hilde'"
    assert give_refusal(world, "Hilde", "Lina") == "Lina is not next to you"
    assert give_refusal(world, "Hilde", "Greta") == "Greta is asleep"
    assert give_refusal(world, "Hilde", "jonas") == "Jonas's hands are full"
    assert give_refusal(world, "Hilde", None) is None  # onto the stalls
    villager(world, "Jonas")["basket"] = None
    assert give_refusal(world, "Hilde", "Jonas") is None
    villager(world, "Hilde").update(at(PIER[0]))
    assert give_refusal(world, "Hilde", None) == (
        "nobody to give it to: name someone next to you, or stand on the square to set it out "
        "for the festival"
    )


def steps_until_basket(world: dict[str, Any], limit: int = 20) -> tuple[int, list[Any]]:
    for step in range(1, limit + 1):
        baskets = work_step(world)
        if baskets:
            return step, baskets
    return limit, []


def test_one_worker_fills_a_basket_in_six_steps_two_in_three() -> None:
    world = world_with(Jonas=at(PIER[0], **working("pier")))
    assert steps_until_basket(world) == (6, [("Jonas", "fish")])
    assert villager(world, "Jonas")["basket"] == "fish"
    assert world["harvest"]["pier"] == 0 and villager(world, "Jonas")["working"]["steps"] == 0
    world = world_with(
        Greta=at(FIELDS[0], **working("fields")), Lina=at(FIELDS[1], **working("fields"))
    )
    assert steps_until_basket(world) == (3, [("Greta", "vegetables")])


def test_work_adds_up_to_tending_and_standing_does_not() -> None:
    world = world_with(
        Greta=at(FIELDS[0], **working("fields")),
        Lina=at(FIELDS[1], **working("fields")),
        Hilde=at(FIELDS[2]),
    )
    world["growth"]["fields"]["stage"] = "growing"
    for _ in range(3):
        work_step(world)
    assert world["tended"] == {"fields": 6, "flower_garden": 0}


def test_the_longest_worker_with_empty_hands_gets_the_basket() -> None:
    world = world_with(
        Greta=at(FIELDS[0], **working("fields", 1)),
        Lina=at(FIELDS[1], **working("fields", 4)),
    )
    world["harvest"]["fields"] = 4
    assert work_step(world) == [("Lina", "vegetables")]
    assert villager(world, "Greta")["working"]["steps"] == 2


def test_with_full_hands_the_work_is_kept_until_someone_has_empty_hands() -> None:
    world = world_with(Jonas=at(PIER[0], basket="fish", **working("pier")))
    for _ in range(8):
        assert work_step(world) == []
    assert world["harvest"]["pier"] == 6
    villager(world, "Jonas")["basket"] = None
    assert work_step(world) == [("Jonas", "fish")]


def test_no_basket_from_a_place_without_goods() -> None:
    world = world_with(Greta=at(FIELDS[0], **working("fields")))
    world["growth"]["fields"]["stage"] = "growing"
    assert steps_until_basket(world) == (20, [])
    assert world["harvest"]["fields"] == 0 and world["tended"]["fields"] == 20


def test_sleepers_do_not_work() -> None:
    world = world_with(Jonas=at(PIER[0], asleep=True, **working("pier")))
    assert work_step(world) == [] and world["harvest"]["pier"] == 0


@pytest.mark.parametrize(
    ("stalls", "text"),
    [
        (
            {"fish": 0, "vegetables": 0, "flowers": 0},
            "The festival stalls on the square are empty; they still lack fish, vegetables and "
            "flowers.",
        ),
        (
            {"fish": 2, "vegetables": 0, "flowers": 0},
            "The festival stalls on the square hold fish; they still lack vegetables and flowers.",
        ),
        (
            {"fish": 1, "vegetables": 1, "flowers": 0},
            "The festival stalls on the square hold fish and vegetables; they still lack flowers.",
        ),
        (
            {"fish": 1, "vegetables": 3, "flowers": 1},
            "The festival stalls on the square hold fish, vegetables and flowers.",
        ),
    ],
)
def test_stalls_text(stalls: dict[str, int], text: str) -> None:
    assert stalls_text(stalls) == text


def test_a_basket_is_not_given_straight_back() -> None:
    sx, sy = SQUARE
    received = {
        "tick": 29,
        "kind": "received",
        "text": "Greta gave you a basket of flowers.",
        "from": "Greta",
    }
    world = world_with(
        Hilde=at((sx, sy), basket="flowers", events=[received]),
        Greta=at((sx + 1, sy)),
        Jonas=at((sx, sy + 1)),
    )
    assert give_refusal(world, "Hilde", "Greta") == (
        "Greta just gave you this basket; set it out on the festival stalls on the square, or "
        "give it to someone else"
    )
    assert give_refusal(world, "Hilde", "Jonas") is None
    assert give_refusal(world, "Hilde", None) is None
    filled = {"tick": 30, "kind": "basket", "text": "You filled a basket of flowers."}
    villager(world, "Hilde")["events"] = [received, filled]  # a basket of its own since
    assert give_refusal(world, "Hilde", "Greta") is None
