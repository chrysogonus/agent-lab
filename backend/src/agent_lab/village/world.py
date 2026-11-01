"""The village map, its clock and its four villagers (specs/007-village-life/data-model.md)."""

from collections import deque
from dataclasses import dataclass
from functools import cache
from typing import Any

from agent_lab.village.seasons import date, festival_in, new_growth

# 32 x 22 cells. Walkable: . grass, = path, the place letters. Not walkable: ~ water, B the town
# hall building, h j g l the villagers' houses, t trees, i lamps.
ROWS = (
    "tt.....t.....t...t......t.....tt",
    "..BBBB..hhh..............lll....",
    "..TTTT..hhh.......tGGGGG.lll.t..",
    "..TTTT...=......t..GGGGG..=.....",
    "t...=..i.=.........GGGGG..=.....",
    "..============================..",
    "....=......i..=........=........",
    "....=.......SSSSS.....MMMM.....t",
    "....=...t...SSSSS=====MMMM......",
    "t...=.......SSSSS.....MMMM......",
    "....=.......SSSSS.............t.",
    "....========================....",
    "t...=......=.....i...=..=.......",
    "....=......=.......t.=..=jjj.t..",
    ".FFFFFF.ggg=.........=..=jjj....",
    ".FFFFFF.ggg=.t......i=..===.....",
    ".FFFFFF..===...t...~~P~~~~~~~~~~",
    ".FFFFFF..........~~~~PP~~~~~~~~~",
    ".FFFFFF..........~~~~~~~~~~~~~~~",
    "..........t......~~~~~~~~~~~~~~~",
    "..t...t.......~~~~~~~~~~~~~~~~~~",
    "..............~~~~~~~~~~~~~~~~~~",
)
WIDTH, HEIGHT = len(ROWS[0]), len(ROWS)
BLOCKED = frozenset("~Bhjglti")
SIGHT = 6  # cells a villager sees, for knowing where others are

PLACES = {
    "town_hall": ("T", "town hall"),
    "square": ("S", "square"),
    "market": ("M", "market"),
    "pier": ("P", "pier"),
    "fields": ("F", "fields"),
    "flower_garden": ("G", "flower garden"),
}
_PLACE_BY_LETTER = {letter: key for key, (letter, _) in PLACES.items()}

Cell = tuple[int, int]


def label(place: str) -> str:
    return PLACES[place][1]


def walkable(x: int, y: int) -> bool:
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and ROWS[y][x] not in BLOCKED


def place_at(x: int, y: int) -> str | None:
    return _PLACE_BY_LETTER.get(ROWS[y][x])


def _cells(letter: str) -> list[Cell]:
    return [(x, y) for y, row in enumerate(ROWS) for x, char in enumerate(row) if char == letter]


def place_cells(place: str) -> list[Cell]:
    return _cells(PLACES[place][0])


def label_cell(place: str) -> Cell:
    """Where the UI writes the place's name: its top-left cell."""
    return min(place_cells(place), key=lambda c: (c[1], c[0]))


@cache
def _distances(targets: frozenset[Cell]) -> dict[Cell, int]:
    """Steps from every walkable cell to the nearest target (breadth-first search)."""
    distance = dict.fromkeys(targets, 0)
    queue = deque(targets)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if walkable(nx, ny) and (nx, ny) not in distance:
                distance[(nx, ny)] = distance[(x, y)] + 1
                queue.append((nx, ny))
    return distance


def steps_to(x: int, y: int, targets: list[Cell]) -> int:
    return _distances(frozenset(targets))[(x, y)]


def step_towards(x: int, y: int, targets: list[Cell]) -> Cell:
    """The next cell on a shortest path to the nearest target; the same cell once on one."""
    distance = _distances(frozenset(targets))
    if distance[(x, y)] == 0:
        return x, y
    neighbours = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return min((c for c in neighbours if c in distance), key=lambda c: distance[c])


def adjacent(a: Cell, b: Cell) -> bool:
    """The same cell or one of its eight neighbours: close enough to talk."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1


def sees(a: Cell, b: Cell) -> bool:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= SIGHT


START_MINUTES = 270  # day 1, 04:30: before anyone wakes


def minute_of_day(tick: int) -> int:
    return (START_MINUTES + 10 * tick) % 1440


def hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def clock(tick: int) -> tuple[int, str, str]:
    """(day, "HH:MM", period) after `tick` steps of 10 minutes from day 1, 04:30."""
    minutes = START_MINUTES + 10 * tick
    day, hour = 1 + minutes // 1440, minutes % 1440 // 60
    if 5 <= hour < 11:
        period = "morning"
    elif 11 <= hour < 14:
        period = "midday"
    elif 14 <= hour < 18:
        period = "afternoon"
    elif 18 <= hour < 22:
        period = "evening"
    else:
        period = "night"
    return day, hhmm(minutes % 1440), period


@dataclass(frozen=True)
class Character:
    name: str  # first name: unique, what others use as "to"
    title: str
    color: str
    work: str  # the place it works at; its home is next to it
    home: str  # how its house is called
    wake: int  # minutes of the day
    bed: int
    routine: tuple[tuple[int, str], ...]  # (from hour, place) during its waking hours
    persona: str

    @property
    def initial(self) -> str:
        return self.name[0]


VILLAGERS = {
    c.name: c
    for c in (
        Character(
            "Hilde",
            "Mayor Hilde",
            "#7c4dcc",
            "town_hall",
            "the mayor's house by the town hall",
            7 * 60 + 30,
            23 * 60,
            ((7, "town_hall"), (11, "square"), (12, "market"), (14, "town_hall"), (18, "square")),
            "You are Hilde, the mayor. Sociable and a little self-important, you want the village "
            "to look good. You are planning a harvest festival on the square and need fish from "
            "Jonas, vegetables from Greta and flowers from Lina, so you go and find them. "
            "Mornings you spend at the town hall, around midday you walk through the square and "
            "the market, evenings you like the square.",
        ),
        Character(
            "Jonas",
            "Jonas the fisher",
            "#0f7f81",
            "pier",
            "the fisher's hut by the pier",
            5 * 60,
            21 * 60,
            ((5, "pier"), (11, "market"), (14, "pier")),
            "You are Jonas, the fisher. Quiet and patient, you say little until you warm up, then "
            "you tell long stories about the lake. Early mornings you fish at the pier, around "
            "midday you bring your catch to the market and trade fish for vegetables, afternoons "
            "and evenings you mend nets at the pier.",
        ),
        Character(
            "Greta",
            "Greta the farmer",
            "#a35a12",
            "fields",
            "the farmhouse by the fields",
            5 * 60 + 30,
            21 * 60 + 30,
            ((5, "fields"), (11, "market"), (14, "fields")),
            "You are Greta, the farmer. Practical and hard-working, you worry about the weather "
            "and the coming harvest and would welcome a helping hand. Mornings and afternoons you "
            "work in the fields, around midday you sell vegetables at the market.",
        ),
        Character(
            "Lina",
            "Lina the flower girl",
            "#c22d6f",
            "flower_garden",
            "the cottage by the flower garden",
            6 * 60 + 30,
            22 * 60,
            ((6, "flower_garden"), (10, "square"), (12, "market"), (15, "square")),
            "You are Lina, the flower girl. Cheerful and curious, you know everyone's news and "
            "love passing it on. Mornings you tend the flower garden, later you sell flowers on "
            "the square and the market and visit the others to chat.",
        ),
    )
}
HOMES = {"Hilde": "h", "Jonas": "j", "Greta": "g", "Lina": "l"}  # map letter of each house


def door(name: str) -> Cell:
    """The cell in front of a villager's house: below the middle of its bottom row."""
    cells = _cells(HOMES[name])
    bottom = max(y for _, y in cells)
    xs = sorted(x for x, y in cells if y == bottom)
    return xs[len(xs) // 2], bottom + 1


def awake_at(name: str, minute: int) -> bool:
    character = VILLAGERS[name]
    return character.wake <= minute < character.bed


FESTIVAL_EVENING = 18 * 60  # the harvest festival on the square, until each villager's bedtime


def usual_place(name: str, tick: int) -> str:
    """Where the village expects a villager at a step: a place key, or "home"."""
    minute = minute_of_day(tick)
    if not awake_at(name, minute):
        return "home"
    if festival_in(clock(tick)[0]) == 0 and minute >= FESTIVAL_EVENING:
        return "square"
    routine = VILLAGERS[name].routine
    return next((p for hour, p in reversed(routine) if hour * 60 <= minute), routine[0][1])


VERSION = 4  # the world's shape: 2 and 3 are upgraded in place, anything else starts fresh


def new_world() -> dict[str, Any]:
    """Day 1, 04:30, paused, every villager asleep at home."""
    villagers: list[dict[str, Any]] = []
    for name in VILLAGERS:
        x, y = door(name)
        villagers.append(
            {
                "name": name,
                "agent_id": None,
                "x": x,
                "y": y,
                "asleep": True,
                "bedtime": False,
                "goal": None,
                "triggers": [],
                "last_decided": 0,
                "neighbours": [],
                "beliefs": {},
                "memories": [],
                "learnings": [],
                "views": {},
                "last_action": None,
                "speech": None,
                "inbox": [],
                "events": [],
            }
        )
    return {
        "version": VERSION,
        "tick": 0,
        "running": False,
        "interval": 5,
        "paused_reason": None,
        "failed_ticks": 0,
        "villagers": villagers,
        "conversations": [],
        "talked_out": [],
        "log": [],
        "reflection_agent_id": None,
        "growth": new_growth(),
        "tended": {"fields": 0, "flower_garden": 0},
        "day_record": None,
        "festival": None,
        "chronicle": [],
        "chronicler_agent_id": None,
    }


def upgrade(world: dict[str, Any]) -> dict[str, Any]:
    """An older world brought to the current shape, so the village keeps going: version 2 (M7)
    gets empty memory (M8), version 3 the seasons with places as the season finds them (M10)."""
    if world["version"] == 2:
        for v in world["villagers"]:
            v |= {"memories": [], "learnings": [], "views": {}}
        for c in world["conversations"]:
            c.setdefault("transcript", [])
        world |= {"version": 3, "reflection_agent_id": None}
    day = clock(world["tick"])[0]
    return world | {
        "version": VERSION,
        "growth": new_growth(date(day)[1]),
        "tended": {"fields": 0, "flower_garden": 0},
        "day_record": None,
        "festival": None,
        "chronicle": [],
        "chronicler_agent_id": None,
    }
