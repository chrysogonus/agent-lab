"""What the village can build, where, and how the building goes
(specs/012-building-together/research.md §3-§4)."""

from dataclasses import dataclass
from typing import Any

from agent_lab.village.world import HOMES, Cell, door, letter_cells, place_cells


@dataclass(frozen=True)
class Project:
    key: str
    name: str
    kind: str  # how the view draws it: paint, trees, stand, building or boat
    needs: dict[str, int]  # loads by goods; one load is one village hour of work
    site: list[Cell]  # where villagers set down loads and build
    at: list[Cell]  # where the result is drawn
    done_text: str


def _house(name: str) -> Project:
    return Project(
        key=f"paint_{name.lower()}",
        name=f"Paint {name}'s house",
        kind="paint",
        needs={"paint": 2},
        site=[door(name)],
        at=letter_cells(HOMES[name]),
        done_text=f"{name}'s house has been painted.",
    )


CATALOGUE = (
    Project(
        key="paint_town_hall",
        name="Paint the town hall",
        kind="paint",
        needs={"paint": 2},
        site=place_cells("town_hall"),
        at=letter_cells("B"),
        done_text="The town hall has been painted.",
    ),
    *(_house(name) for name in HOMES),
    Project(
        key="trees_square",
        name="Plant trees by the square",
        kind="trees",
        needs={"saplings": 3},
        # shortcut: planted trees do not block walking, block them if villagers visibly walk
        # through them
        site=[(18, 10), (20, 10), (22, 10)],
        at=[(18, 10), (20, 10), (22, 10)],
        done_text="Young trees now grow by the square.",
    ),
    Project(
        key="market_stand",
        name="A market stand",
        kind="stand",
        needs={"wood": 3, "paint": 1},
        site=place_cells("market"),
        at=[(26, 8)],  # beside the market's own stalls
        done_text="The market has a new stand.",
    ),
    Project(
        key="boat",
        name="A rowing boat",
        kind="boat",
        needs={"wood": 4, "paint": 1},
        site=[(16, 16), (17, 16), (18, 16)],
        at=[(20, 17)],
        done_text="A rowing boat lies at the pier.",
    ),
    Project(
        key="bakehouse",
        name="A bakehouse on the meadow",
        kind="building",
        needs={"wood": 14, "paint": 3},
        site=[(14, 12), (15, 12), (16, 12)],
        at=letter_cells("b"),
        done_text="The bakehouse on the meadow is finished.",
    ),
    Project(
        key="barn",
        name="A barn by the fields",
        kind="building",
        needs={"wood": 16, "paint": 3},
        site=[(10, 16), (11, 16), (12, 16)],
        at=letter_cells("r"),
        done_text="The barn by the fields is finished.",
    ),
)
_BY_KEY = {p.key: p for p in CATALOGUE}


def entry(key: str) -> Project:
    return _BY_KEY[key]


def _plain(text: str) -> str:
    words = text.strip().lower().replace("_", " ").split()
    return " ".join(words[1:] if words and words[0] in ("a", "an", "the") else words)


def project_named(text: str) -> str | None:
    """A catalogue key from how a villager names a project ("the market stand", "boat")."""
    wanted = _plain(text)
    if not wanted:
        return None
    return next(
        (p.key for p in CATALOGUE if wanted in (_plain(p.name), _plain(p.key))),
        None,
    )


def new_project(key: str, day: int) -> dict[str, Any]:
    empty = {"wood": 0, "paint": 0, "saplings": 0}
    return {
        "key": key,
        "site": dict(empty),  # loads set down, not yet worked in
        "used": dict(empty),  # loads worked in: per goods, as loads arrive in any order
        "work": 0,  # working steps toward the next load
        "tasks": [],
        "day": day,
    }


def buildable(world: dict[str, Any]) -> list[Project]:
    """What can still be chosen: not built and not being built, in catalogue order."""
    taken = {b["key"] for b in world["built"]}
    if world["project"]:
        taken.add(world["project"]["key"])
    return [p for p in CATALOGUE if p.key not in taken]


def built_text(world: dict[str, Any]) -> str | None:
    if not world["built"]:
        return None
    return "Built so far: " + " ".join(entry(b["key"]).done_text for b in world["built"])
