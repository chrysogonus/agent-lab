"""The day's happenings (FR-001, FR-002, FR-004)."""

from typing import Any

from agent_lab.village.evals.fixtures import build_world
from agent_lab.village.happenings import (
    END_OF_DAY,
    KINDS,
    day_happenings,
    happening_text,
    lead_refusal,
    noticed,
    repair_at,
    step,
    told_text,
)
from agent_lab.village.meeting import meeting_day
from agent_lab.village.seasons import festival_in
from agent_lab.village.world import door, label_cell, place_cells


def world_at(time: str, **villagers: Any) -> dict[str, Any]:
    return build_world({"day": 20, "time": time, "villagers": villagers})


def happening(kind: str, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": kind,
        "place": None,
        "cell": [0, 0],
        "start": 9 * 60,
        "end": 19 * 60,
        "concerns": None,
        "details": {"text": "x"},
        "state": "here",
        "by": None,
        "seen_by": [],
        "leader": None,
        "work": 0,
        "with_host": 0,
    }
    return base | fields


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def test_the_same_day_brings_the_same_happenings() -> None:
    assert day_happenings(30) == day_happenings(30)
    assert KINDS == ("letter", "visitor", "animal", "repair", "peddler")
    seen: set[str] = set()
    for day in range(1, 201):
        found = day_happenings(day)
        kinds = [h["kind"] for h in found]
        assert 1 <= len(found) <= 2 and len(set(kinds)) == len(kinds), day
        assert all(h["state"] == "coming" and h["by"] is None for h in found)
        seen |= set(kinds)
        if festival_in(day) == 0:
            assert "peddler" not in kinds
        if meeting_day(day):
            out = [h for h in found if h["kind"] not in ("visitor", "letter")]  # a letter waits
            assert all(h["end"] <= 16 * 60 + 30 for h in out), day
    assert seen == set(KINDS)


def test_each_kind_has_its_place_window_and_who_it_concerns() -> None:
    by_kind = {h["kind"]: h for day in range(1, 60) for h in day_happenings(day)}
    letter, visitor = by_kind["letter"], by_kind["visitor"]
    assert letter["start"] == 8 * 60 and letter["cell"] == list(door(letter["concerns"]))
    assert letter["details"]["text"]
    assert (visitor["start"], visitor["end"]) == (13 * 60, 19 * 60)
    assert visitor["cell"] == list(door(visitor["concerns"])) and visitor["details"]["name"]
    animal = by_kind["animal"]
    assert animal["start"] == 9 * 60 and animal["place"] and animal["concerns"]
    assert animal["cell"] in [list(c) for c in place_cells(animal["place"])]
    repair = by_kind["repair"]
    assert repair["place"] in ("fields", "pier", "flower_garden") and repair["end"] <= END_OF_DAY
    peddler = by_kind["peddler"]
    assert (peddler["place"], peddler["start"], peddler["end"]) == ("square", 10 * 60, 15 * 60)
    assert peddler["details"]["goods"]


def test_a_happening_comes_and_passes_with_its_window() -> None:
    world = world_at("08:50")
    goat = happening("animal", state="coming", place="market", concerns="Greta")
    world["happenings"] = [goat]
    assert step(world) == []
    world["tick"] += 1  # 09:00
    assert step(world) == [{"happening": goat, "change": "here"}]
    world["tick"] += (19 * 60 - 9 * 60) // 10
    assert step(world) == [{"happening": goat, "change": "passed"}]
    assert goat["state"] == "passed"


def test_a_led_animal_follows_and_is_home_at_its_owners_door() -> None:
    world = world_at("10:00", Jonas={"at": "market"}, Greta={"at": "fields"})
    jonas = villager(world, "Jonas")
    goat = happening(
        "animal",
        place="market",
        concerns="Greta",
        cell=[jonas["x"] + 1, jonas["y"]],
        details={"text": "Greta's goat"},
    )
    world["happenings"] = [goat]
    assert lead_refusal(world, "Jonas") is None
    assert lead_refusal(world, "Greta") == "there is no lost animal next to you"
    goat["leader"] = "Jonas"
    assert lead_refusal(world, "Jonas") == "you already lead Greta's goat"
    jonas["x"], jonas["y"] = 12, 5
    assert step(world) == [] and goat["cell"] == [12, 5]
    jonas["x"], jonas["y"] = door("Greta")
    assert step(world) == [{"happening": goat, "change": "dealt", "by": "Jonas"}]
    assert goat["state"] == "dealt" and goat["by"] == "Jonas"


def test_a_visitor_joins_the_host_and_an_hour_together_deals_with_it() -> None:
    world = world_at("13:00", Greta={"at": "fields"})
    greta = villager(world, "Greta")
    anna = happening("visitor", concerns="Greta", cell=list(door("Greta")), start=780, end=1140)
    world["happenings"] = [anna]
    step(world)
    assert anna["leader"] is None  # waits at the door
    greta["x"], greta["y"] = door("Greta")
    changes: list[dict[str, Any]] = []
    for _ in range(6):
        changes += step(world)
    assert anna["leader"] == "Greta" and anna["with_host"] == 6
    assert changes == [{"happening": anna, "change": "dealt", "by": "Greta"}]


def test_a_letter_is_read_when_its_addressee_is_at_home() -> None:
    world = world_at("09:00", Lina={"at": "market"})
    letter = happening("letter", concerns="Lina", cell=list(door("Lina")), start=480, end=1260)
    world["happenings"] = [letter]
    assert step(world) == []
    lina = villager(world, "Lina")
    lina["x"], lina["y"] = door("Lina")
    assert step(world) == [{"happening": letter, "change": "dealt", "by": "Lina"}]


def test_noticing_within_sight_once_each() -> None:
    world = world_at("10:00", Lina={"at": "square"}, Jonas={"at": "pier"})
    sx, sy = label_cell("square")
    peddler = happening("peddler", place="square", cell=[sx + 1, sy])
    letter = happening("letter", concerns="Hilde", cell=list(door("Hilde")))
    world["happenings"] = [peddler, letter]
    assert noticed(world, villager(world, "Lina")) == [peddler]
    assert noticed(world, villager(world, "Jonas")) == []  # out of sight
    peddler["seen_by"].append("Lina")
    assert noticed(world, villager(world, "Lina")) == []


def test_the_texts() -> None:
    goat = happening("animal", place="market", concerns="Greta", details={"text": "Greta's goat"})
    assert happening_text(goat) == "Greta's goat wandered to the market."
    goat["leader"] = "Jonas"
    assert happening_text(goat) == "Jonas is leading Greta's goat home."
    fence = happening("repair", place="fields", details={"text": "the fence at the fields"})
    assert happening_text(fence) == (
        "The fence at the fields broke; an hour of work there mends it."
    )
    peddler = happening("peddler", place="square", details={"text": "x", "goods": "a lantern"})
    assert happening_text(peddler) == (
        "A peddler stands at the square with a lantern to trade for a basket."
    )
    letter = happening("letter", concerns="Lina", details={"text": "Your cousin weds in spring."})
    assert told_text(letter) == "The postman brought you a letter; it waits at home."
    anna = happening(
        "visitor", concerns="Greta", details={"text": "x", "name": "Anna, your sister"}
    )
    assert told_text(anna) == (
        "Anna, your sister, comes to visit this afternoon and waits at your door from 13:00."
    )


def test_a_repair_at_a_place() -> None:
    world = world_at("10:00")
    fence = happening("repair", place="fields")
    world["happenings"] = [fence]
    assert repair_at(world, "fields") is fence and repair_at(world, "pier") is None
    fence["state"] = "dealt"
    assert repair_at(world, "fields") is None
