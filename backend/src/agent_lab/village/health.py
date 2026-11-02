"""Village health: numbers for every village day, from the stored runs, the day's notes and the
day trail (specs/013-measuring-the-village/research.md §1-§3)."""

from collections.abc import Callable
from typing import Any

from agent_lab.village.world import place_at

Villager = dict[str, Any]


def trail_row(world: dict[str, Any], state_of: Callable[[Villager], str]) -> dict[str, Any]:
    """Where everyone is at this step, what they do and carry, and how far the building is."""
    project = world["project"]
    return {
        "v": [
            [v["name"], v["x"], v["y"], place_at(v["x"], v["y"]), state_of(v), v["basket"]]
            for v in world["villagers"]
        ],
        "project": project["key"] if project else None,
        "used": sum(project["used"].values()) if project else 0,
    }
