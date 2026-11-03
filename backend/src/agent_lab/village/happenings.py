"""The day's happenings: a letter, a visitor, a lost animal, a repair or a peddler
(specs/015-daily-happenings/research.md §1-§3).

Pure, and chosen from the day like the weather and the trader's stock, so the same day always
brings the same happenings. They move by fixed rules and cost no model call; the runner applies
the changes `step` returns.
"""

import random
from typing import Any

from agent_lab.village.meeting import meeting_day
from agent_lab.village.seasons import festival_in
from agent_lab.village.world import adjacent, door, label, minute_of_day, place_cells, sees

KINDS = ("letter", "visitor", "animal", "repair", "peddler")
END_OF_DAY = 21 * 60  # what is still open by now has passed
MEETING_EARLY = 16 * 60 + 30  # on a meeting day nothing but a visitor lasts past this
TOGETHER = 6  # steps: an hour with the visitor deals with it
TWO = 0.4  # the chance of a second happening

LETTERS = {
    "Hilde": (
        "Your old friend from the council in town writes that the market there doubled its fees.",
        "Your cousin writes that she is getting married in the spring and hopes you will come.",
        "A letter from the county: a surveyor may visit before winter.",
    ),
    "Jonas": (
        "Your brother at sea writes that the herring came early this year.",
        "A boatwright down the river writes that he sells oars cheaply this month.",
    ),
    "Greta": (
        "Your sister writes that the harvest in her valley failed and she may need help.",
        "A seed merchant writes that he has a new kind of bean that grows in dry summers.",
    ),
    "Lina": (
        "A friend from town writes that roses sell for twice the price there.",
        "Your aunt writes that she is sending you her old flower press.",
    ),
}
VISITORS = (  # (as the others say it, as the host is told, host)
    ("Anna, Greta's sister", "Anna, your sister", "Greta"),
    ("Old Tomas, Jonas's uncle", "Old Tomas, your uncle", "Jonas"),
    ("Marta, Lina's friend from town", "Marta, your friend from town", "Lina"),
    ("Councillor Brandt, Hilde's old friend", "Councillor Brandt, your old friend", "Hilde"),
)
ANIMALS = (  # (the animal, its owner)
    ("goat", "Greta"),
    ("dog", "Jonas"),
    ("cat", "Lina"),
    ("hen", "Hilde"),
)
REPAIRS = {
    "fields": "the fence at the fields",
    "pier": "the boards of the pier",
    "flower_garden": "the garden gate",
}
CURIOSITIES = ("a lantern", "a fiddle", "a book of songs", "a kite")

Happening = dict[str, Any]
Villager = dict[str, Any]


def new_happening(
    kind: str, cell: tuple[int, int], start: int, end: int, **fields: Any
) -> Happening:
    base: Happening = {
        "kind": kind,
        "place": None,
        "cell": list(cell),
        "start": start,
        "end": end,
        "concerns": None,
        "details": {},
        "state": "coming",
        "by": None,
        "seen_by": [],
        "leader": None,
        "work": 0,
        "with_host": 0,
    }
    return base | fields


def _one(kind: str, rng: random.Random, meeting: bool) -> Happening:
    if kind == "letter":
        name = rng.choice(list(LETTERS))
        details = {"text": rng.choice(LETTERS[name])}
        return new_happening(kind, door(name), 8 * 60, END_OF_DAY, concerns=name, details=details)
    if kind == "visitor":
        said, told, host = rng.choice(VISITORS)
        details = {"text": said, "name": told}
        return new_happening(kind, door(host), 13 * 60, 19 * 60, concerns=host, details=details)
    if kind == "animal":
        animal, owner = rng.choice(ANIMALS)
        place = rng.choice([p for p in ("square", "market", "fields", "pier", "town_hall")])
        details = {"text": f"{owner}'s {animal}", "own": f"your {animal}"}
        end = MEETING_EARLY if meeting else 19 * 60
        cell = rng.choice(place_cells(place))
        return new_happening(kind, cell, 9 * 60, end, place=place, concerns=owner, details=details)
    if kind == "repair":
        place = rng.choice(list(REPAIRS))
        end = MEETING_EARLY if meeting else END_OF_DAY
        cell = place_cells(place)[0]
        return new_happening(kind, cell, 5 * 60, end, place=place, details={"text": REPAIRS[place]})
    goods = rng.choice(CURIOSITIES)
    cell = place_cells("square")[0]
    details = {"text": f"a peddler with {goods}", "goods": goods}
    return new_happening(kind, cell, 10 * 60, 15 * 60, place="square", details=details)


def day_happenings(day: int) -> list[Happening]:
    """One happening, or two of different kinds, the same every time the day comes."""
    rng = random.Random(f"happenings {day}")  # noqa: S311 -- reproducible days, not security
    kinds = [k for k in KINDS if not (k == "peddler" and festival_in(day) == 0)]
    count = 2 if rng.random() < TWO else 1
    meeting = meeting_day(day)
    return [_one(kind, rng, meeting) for kind in rng.sample(kinds, count)]


def _villager(world: dict[str, Any], name: str) -> Villager:
    return next(v for v in world["villagers"] if v["name"] == name)


def _cell(v: Villager) -> tuple[int, int]:
    return v["x"], v["y"]


def step(world: dict[str, Any]) -> list[dict[str, Any]]:
    """One step of the day's happenings: what came, was dealt with or passed."""
    minute = minute_of_day(world["tick"])
    changes: list[dict[str, Any]] = []
    for h in world["happenings"]:
        if h["state"] == "coming" and h["start"] <= minute < h["end"]:
            h["state"] = "here"
            changes.append({"happening": h, "change": "here"})
        if h["state"] in ("coming", "here") and minute >= h["end"]:
            h["state"] = "passed"
            changes.append({"happening": h, "change": "passed"})
            continue
        if h["kind"] == "visitor" and h["start"] <= minute < h["end"]:
            dealt = _visit(world, h)
        elif h["state"] != "here":
            continue
        elif h["kind"] == "animal" and h["leader"]:
            dealt = _follow(world, h)
        elif h["kind"] == "letter":
            them = _villager(world, h["concerns"])
            dealt = (
                h["concerns"] if not them["asleep"] and _cell(them) == door(them["name"]) else None
            )
        else:
            dealt = None
        if dealt and h["state"] == "here":
            h |= {"state": "dealt", "by": dealt}
            changes.append({"happening": h, "change": "dealt", "by": dealt})
    return changes


def _visit(world: dict[str, Any], h: Happening) -> str | None:
    """The visitor waits at the host's door, then keeps the host company."""
    host = _villager(world, h["concerns"])
    if h["leader"] is None and not host["asleep"] and adjacent(_cell(host), tuple(h["cell"])):
        h["leader"] = host["name"]
    if h["leader"] is None or host["asleep"]:
        return None
    h["cell"] = [host["x"], host["y"]]
    h["with_host"] += 1
    return host["name"] if h["with_host"] >= TOGETHER else None


def _follow(world: dict[str, Any], h: Happening) -> str | None:
    """A led animal follows its leader and is home at its owner's door, or with its owner."""
    leader, owner = _villager(world, h["leader"]), _villager(world, h["concerns"])
    h["cell"] = [leader["x"], leader["y"]]
    home = _cell(leader) == door(owner["name"])
    met = not owner["asleep"] and adjacent(_cell(leader), _cell(owner))
    return leader["name"] if home or met else None


def noticed(world: dict[str, Any], v: Villager) -> list[Happening]:
    """What `v` sees now and was not told of yet; a letter is only for its addressee."""
    if v["asleep"]:
        return []
    return [
        h
        for h in world["happenings"]
        if h["state"] == "here"
        and h["kind"] != "letter"
        and v["name"] not in h["seen_by"]
        and v["name"] != h["concerns"]
        and sees(_cell(v), tuple(h["cell"]))
    ]


def happening_text(h: Happening) -> str:
    """The happening as anyone who sees it knows it."""
    details, kind = h["details"], h["kind"]
    if kind == "animal":
        if h["leader"]:
            return f"{h['leader']} is leading {details['text']} home."
        return f"{details['text'].capitalize()} wandered to the {label(h['place'])}."
    if kind == "repair":
        return f"{details['text'].capitalize()} broke; an hour of work there mends it."
    if kind == "peddler":
        return f"A peddler stands at the square with {details['goods']} to trade for a basket."
    if kind == "visitor":
        return f"{details['text']} is visiting {h['concerns']}."
    return f"A letter came for {h['concerns']}."


def told_text(h: Happening) -> str | None:
    """What the villager a happening concerns is told when it starts."""
    if h["kind"] == "letter":
        return "The postman brought you a letter; it waits at home."
    if h["kind"] == "visitor":
        return (
            f"{h['details']['name']}, comes to visit this afternoon and waits at your door from "
            "13:00."
        )
    if h["kind"] == "animal":
        return f"{h['details']['own'].capitalize()} got out and wandered off."
    return None


def lead_refusal(world: dict[str, Any], name: str) -> str | None:
    """Why a villager cannot lead a lost animal home now, or None."""
    me = _villager(world, name)
    animal = next(
        (
            h
            for h in world["happenings"]
            if h["kind"] == "animal"
            and h["state"] == "here"
            and adjacent(_cell(me), tuple(h["cell"]))
        ),
        None,
    )
    if animal is None:
        return "there is no lost animal next to you"
    if animal["leader"] == name:
        return f"you already lead {animal['details']['text']}"
    if animal["leader"]:
        return f"{animal['leader']} already leads it"
    return None


def animal_next_to(world: dict[str, Any], name: str) -> Happening | None:
    me = _villager(world, name)
    return next(
        (
            h
            for h in world["happenings"]
            if h["kind"] == "animal"
            and h["state"] == "here"
            and h["leader"] is None
            and adjacent(_cell(me), tuple(h["cell"]))
        ),
        None,
    )


def repair_at(world: dict[str, Any], place: str | None) -> Happening | None:
    return next(
        (
            h
            for h in world["happenings"]
            if h["kind"] == "repair" and h["state"] == "here" and h["place"] == place
        ),
        None,
    )


def known_lines(world: dict[str, Any], name: str) -> list[str]:
    """The happenings a villager knows of for itself: seen, or concerning it."""
    lines: list[str] = []
    for h in world["happenings"]:
        if h["state"] != "here":
            continue
        if h["concerns"] == name and h["kind"] == "letter":
            lines.append("A letter waits for you at home.")
        elif h["concerns"] == name and h["kind"] == "visitor":
            lines.append(f"{h['details']['name']}, is visiting you.")
        elif h["concerns"] == name and h["kind"] == "animal":
            own = h["details"]["own"]
            lines.append(
                f"{h['leader']} is bringing {own} home."
                if h["leader"]
                else f"{own.capitalize()} got out and wandered off."
            )
        elif name in h["seen_by"]:
            lines.append(happening_text(h))
    return [f"Happening: {line}" for line in lines]
