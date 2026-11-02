"""What the village can build, where, and how the building goes
(specs/012-building-together/research.md §3-§4)."""

from dataclasses import dataclass
from typing import Any

from agent_lab.village.trade import BASKET_GOODS
from agent_lab.village.world import HOMES, Cell, door, letter_cells, listed, place_cells


@dataclass(frozen=True)
class Project:
    key: str
    name: str
    kind: str  # how the view draws it: paint, trees, stand, building or boat
    needs: dict[str, int]  # loads by goods; one load is one village hour of work
    site: list[Cell]  # where villagers set down loads and build
    where: str  # the site in words: "at the town hall", "in front of Lina's house"
    at: list[Cell]  # where the result is drawn
    done_text: str


def _house(name: str) -> Project:
    return Project(
        key=f"paint_{name.lower()}",
        name=f"Paint {name}'s house",
        kind="paint",
        needs={"paint": 2},
        site=[door(name)],
        where=f"in front of {name}'s house",
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
        where="at the town hall",
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
        where="by the square, east of it",
        at=[(18, 10), (20, 10), (22, 10)],
        done_text="Young trees now grow by the square.",
    ),
    Project(
        key="market_stand",
        name="A market stand",
        kind="stand",
        needs={"wood": 3, "paint": 1},
        site=place_cells("market"),
        where="at the market",
        at=[(26, 8)],  # beside the market's own stalls
        done_text="The market has a new stand.",
    ),
    Project(
        key="boat",
        name="A rowing boat",
        kind="boat",
        needs={"wood": 4, "paint": 1},
        site=[(16, 16), (17, 16), (18, 16)],
        where="on the shore west of the pier",
        at=[(20, 17)],
        done_text="A rowing boat lies at the pier.",
    ),
    Project(
        key="bakehouse",
        name="A bakehouse on the meadow",
        kind="building",
        needs={"wood": 14, "paint": 3},
        site=[(14, 12), (15, 12), (16, 12)],
        where="on the meadow south of the square",
        at=letter_cells("b"),
        done_text="The bakehouse on the meadow is finished.",
    ),
    Project(
        key="barn",
        name="A barn by the fields",
        kind="building",
        needs={"wood": 16, "paint": 3},
        site=[(10, 16), (11, 16), (12, 16)],
        where="by the fields, next to Greta's house",
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


def needs_left(world: dict[str, Any]) -> dict[str, int]:
    """The loads the current project still needs brought to its site, by goods."""
    project = world["project"]
    if project is None:
        return {}
    needs = entry(project["key"]).needs
    left = {g: n - project["site"][g] - project["used"][g] for g, n in needs.items()}
    return {g: n for g, n in left.items() if n > 0}


def _loads(loads: dict[str, int]) -> str:
    return listed([f"{n} {goods}" for goods, n in loads.items() if n])


def task_text(task: dict[str, Any]) -> str:
    if task["task"] == "buy":
        return f"buy {task['goods']} from the trader"
    if task["task"] == "bring":
        return f"bring {task['goods']} to the building site"
    return "build at the building site"


def _site_hints(world: dict[str, Any], name: str) -> list[str]:
    """Where a carried load belongs, and building when loads lie where the villager stands:
    on the real model loads were bought and kept, or handed around, instead of set down."""
    me = next(v for v in world["villagers"] if v["name"] == name)
    project, here = world["project"], site_at(world, (me["x"], me["y"]))
    goods = me["basket"]
    if goods and needs_left(world).get(goods):
        if here:
            return [
                f"You are at the building site: set down your load of {goods} now with "
                '{"action": "give"}.'
            ]
        return [
            f"Take your load of {goods} to the building site ({entry(project['key']).where}) and "
            'set it down there: {"action": "move", "place": "building site"}, then '
            '{"action": "give"}.'
        ]
    if goods in BASKET_GOODS and not any(project["site"].values()):
        wanted = next(iter(needs_left(world)), None)
        if wanted:  # the work plan often forgot the buying (real model)
            action = f'{{"action": "buy", "goods": "{wanted}"}}'
            return [
                f"Nothing can be built until someone buys {wanted}: trade your basket for a load "
                f"at the market while the trader is there ({action})."
            ]
    working = me["working"] and me["working"]["place"] == "site"
    if here and not working and any(project["site"].values()):
        held = _loads(project["site"])
        return [f'The building site holds {held}: build here with {{"action": "work"}}.']
    return []


def project_text(world: dict[str, Any], name: str) -> list[str]:
    """What a villager knows about the building: the project, its own share and what stands."""
    lines: list[str] = []
    project = world["project"]
    if project:
        p = entry(project["key"])
        done, total = sum(project["used"].values()), sum(p.needs.values())
        lines.append(
            f"The village is building: {p.name} (the building site is {p.where}). It still "
            f"needs {_loads(needs_left(world)) or 'nothing more'}; the site holds "
            f"{_loads(project['site']) or 'nothing'}; {done} of {total} loads worked in."
        )
        mine = "; ".join(task_text(t) for t in project["tasks"] if name in t["villagers"])
        if not project["tasks"]:
            lines.append("Hilde has not handed out the work yet.")
        elif name == "Hilde":
            lines.append(
                f"You took on: {mine}." if mine else "You handed out the work; you may help too."
            )
        else:
            lines.append(
                f"Hilde asked you to: {mine}."
                if mine
                else "Nothing is asked of you; you may still help."
            )
        lines += _site_hints(world, name)
    built = built_text(world)
    return lines + ([built] if built else [])


# --- the building site (research §4) ---

BUILD_STEPS = 6  # one village hour of work, added up over everyone at the site, uses one load


def site_cells(world: dict[str, Any]) -> list[Cell]:
    return entry(world["project"]["key"]).site if world["project"] else []


def site_at(world: dict[str, Any], cell: Cell) -> bool:
    return cell in site_cells(world)


def site_refusal(world: dict[str, Any], goods: str) -> str | None:
    """Why a load of `goods` cannot be set down at the building site, or None."""
    if goods not in entry(world["project"]["key"]).needs:
        return f"the building site does not need {goods}"
    if not needs_left(world).get(goods):
        return f"the building site has all the {goods} it needs"
    return None


def build_step(world: dict[str, Any]) -> str | None:
    """One step of building: everyone working at the site adds up, and each village hour of it
    works in one load lying there. The project's key once its last load is worked in."""
    project = world["project"]
    if project is None:
        return None
    workers = [
        v
        for v in world["villagers"]
        if v["working"] and v["working"]["place"] == "site" and not v["asleep"]
    ]
    needs = entry(project["key"]).needs
    lying = [goods for goods in needs if project["site"][goods]]  # catalogue order
    if not workers or not lying:
        return None
    for v in workers:
        v["working"]["steps"] += 1
    project["work"] = min(project["work"] + len(workers), BUILD_STEPS)
    if project["work"] < BUILD_STEPS:
        return None
    goods = lying[0]
    project["site"][goods] -= 1
    project["used"][goods] += 1
    project["work"] = 0
    return project["key"] if all(project["used"][g] == n for g, n in needs.items()) else None
