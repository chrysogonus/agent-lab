"""The village map, its clock and its four villagers (specs/006-village/data-model.md)."""

from collections import deque
from dataclasses import dataclass
from typing import Any

# 20 x 15 cells: . grass, = path, ~ water (not walkable), letters: places.
ROWS = (
    "....................",
    ".TTT.......GGGG.....",
    ".TTT==.....GGGG.....",
    "...=.=====.==.......",
    "...=.....=.=........",
    "...=..SSSS==........",
    "...===SSSS....MMM...",
    "......SSSS====MMM...",
    ".......=.....=MMM...",
    "FFFF...=.....=......",
    "FFFF====.....==~~~~~",
    "FFFF.........P~~~~~~",
    "FFFF........PP~~~~~~",
    "..........~~~~~~~~~~",
    "..........~~~~~~~~~~",
)
WIDTH, HEIGHT = len(ROWS[0]), len(ROWS)

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
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and ROWS[y][x] != "~"


def place_at(x: int, y: int) -> str | None:
    return _PLACE_BY_LETTER.get(ROWS[y][x])


def place_cells(place: str) -> list[Cell]:
    letter = PLACES[place][0]
    return [(x, y) for y, row in enumerate(ROWS) for x, char in enumerate(row) if char == letter]


def label_cell(place: str) -> Cell:
    """Where the UI writes the place's name: its top-left cell."""
    return min(place_cells(place), key=lambda c: (c[1], c[0]))


def home_cell(place: str) -> Cell:
    """Where a villager starts: the cell nearest the middle of its home (labels sit top-left)."""
    cells = place_cells(place)
    mx, my = sum(x for x, _ in cells) / len(cells), sum(y for _, y in cells) / len(cells)
    return min(
        cells, key=lambda c: ((c[0] - mx) ** 2 + (c[1] - my) ** 2, -c[1], c[0])
    )  # ties: lower row


def _distances(place: str) -> dict[Cell, int]:
    """Steps from every walkable cell to the nearest cell of `place` (breadth-first search)."""
    targets = place_cells(place)
    distance = dict.fromkeys(targets, 0)
    queue = deque(targets)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if walkable(nx, ny) and (nx, ny) not in distance:
                distance[(nx, ny)] = distance[(x, y)] + 1
                queue.append((nx, ny))
    return distance


def steps_between(x: int, y: int, place: str) -> int:
    return _distances(place)[(x, y)]


def step_towards(x: int, y: int, place: str) -> Cell:
    """The next cell on a shortest path into `place`; the same cell once inside it."""
    distance = _distances(place)
    if distance[(x, y)] == 0:
        return x, y
    neighbours = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return min((c for c in neighbours if c in distance), key=lambda c: distance[c])


def nearby(a: Cell, b: Cell) -> bool:
    """In the same place, or within 3 cells of each other outside places."""
    place_a, place_b = place_at(*a), place_at(*b)
    if place_a or place_b:
        return place_a == place_b
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 3


def clock(tick: int) -> tuple[int, str, str]:
    """(day, "HH:MM", period) after `tick` ticks of 10 minutes from day 1, 06:00."""
    minutes = 360 + 10 * tick
    day, minute_of_day = 1 + minutes // 1440, minutes % 1440
    hour = minute_of_day // 60
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
    return day, f"{hour:02d}:{minute_of_day % 60:02d}", period


@dataclass(frozen=True)
class Character:
    name: str  # first name: unique, what others use as "to"
    title: str
    color: str
    home: str
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
            "You are Hilde, the mayor. Sociable and a little self-important, you want the village "
            "to look good. You are planning a harvest festival on the square and need fish from "
            "Jonas, vegetables from Greta and flowers from Lina, so you go and talk to them. "
            "Mornings you spend at the town hall, around midday you walk through the square and "
            "the market, evenings you like the square.",
        ),
        Character(
            "Jonas",
            "Jonas the fisher",
            "#0f7f81",
            "pier",
            "You are Jonas, the fisher. Quiet and patient, you say little until you warm up, then "
            "you tell long stories about the lake. Early mornings you fish at the pier, around "
            "midday you bring your catch to the market and trade fish for vegetables, evenings "
            "you mend nets at the pier.",
        ),
        Character(
            "Greta",
            "Greta the farmer",
            "#a35a12",
            "fields",
            "You are Greta, the farmer. Practical and hard-working, you worry about the weather "
            "and the coming harvest and would welcome a helping hand. Mornings and afternoons you "
            "work in the fields, around midday you sell vegetables at the market.",
        ),
        Character(
            "Lina",
            "Lina the flower girl",
            "#c22d6f",
            "flower_garden",
            "You are Lina, the flower girl. Cheerful and curious, you know everyone's news and "
            "love passing it on. Mornings you tend the flower garden, later you sell flowers on "
            "the square and the market and visit the others to chat.",
        ),
    )
}


def new_world() -> dict[str, Any]:
    """Tick 0, paused, every villager at a cell of its home."""
    villagers: list[dict[str, Any]] = []
    for character in VILLAGERS.values():
        x, y = home_cell(character.home)
        villagers.append(
            {
                "name": character.name,
                "agent_id": None,
                "x": x,
                "y": y,
                "destination": None,
                "last_action": None,
                "speech": None,
                "inbox": [],
                "events": [],
            }
        )
    return {
        "tick": 0,
        "running": False,
        "interval": 5,
        "paused_reason": None,
        "failed_ticks": 0,
        "villagers": villagers,
    }
