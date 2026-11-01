"""A villager's lasting memory: writing, recalling and reflecting (specs/008-village-memory)."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_lab.village.world import VILLAGERS, clock

IMPORTANCE = {"conversation": 3, "found": 2, "missed": 2, "met": 1, "reflection": 5}
MEMORIES_KEPT = 60
LEARNINGS_KEPT = 12
MEMORY_TEXT = 400  # characters of a memory
LEARNING_TEXT = 200  # characters of a learning or a view

Memory = dict[str, Any]


def recency(memory: Memory, tick: int) -> float:
    """3 for a memory from now, fading by 15% per village hour."""
    return 3 * 0.85 ** ((tick - memory["tick"]) / 6)


def remember(
    villager: dict[str, Any],
    tick: int,
    kind: str,
    text: str,
    about: list[str],
    place: str | None,
) -> None:
    memory: Memory = {
        "tick": tick,
        "kind": kind,
        "about": sorted(about),
        "place": place,
        "text": text[:MEMORY_TEXT],
        "importance": IMPORTANCE[kind],
    }
    memories: list[Memory] = [*villager["memories"], memory]
    if len(memories) > MEMORIES_KEPT:  # the least important, oldest memory goes first
        memories.remove(min(memories[:-1], key=lambda m: m["importance"] + recency(m, tick)))
    villager["memories"] = memories


def score(memory: Memory, tick: int, names: set[str], place: str | None) -> float:
    relevance = (4 if names & set(memory["about"]) else 0) + (
        2 if place and memory["place"] == place else 0
    )
    return relevance + memory["importance"] + recency(memory, tick)


def recall(
    memories: list[Memory], tick: int, names: set[str], place: str | None, limit: int = 5
) -> list[Memory]:
    """The memories that matter most right now, oldest first."""
    best = sorted(memories, key=lambda m: score(m, tick, names, place), reverse=True)[:limit]
    return sorted(best, key=lambda m: m["tick"])


def unreflected(memories: list[Memory]) -> list[Memory]:
    """Memories since the villager last reflected: what its next reflection looks back on."""
    last = max((m["tick"] for m in memories if m["kind"] == "reflection"), default=-1)
    return [m for m in memories if m["kind"] != "reflection" and m["tick"] > last]


def when(tick: int) -> str:
    day, time, _ = clock(tick)
    return f"Day {day} {time}"


def reflection_prompt(villager: dict[str, Any], tick: int) -> str:
    name = villager["name"]
    views = villager["views"]
    lines = [
        VILLAGERS[name].persona,
        f"Day {clock(tick)[0]} is over and you are going to bed.",
        "What you remember since you last looked back:",
        *[f"- {when(m['tick'])} {m['text']}" for m in unreflected(villager["memories"])],
        "What you learned before:",
        *(
            [f"- Day {clock(item['tick'])[0]}: {item['text']}" for item in villager["learnings"]]
            or ["- nothing yet"]
        ),
        "What you think of the others:",
        *[
            f"- {other}: {views[other]['text'] if other in views else 'no view yet'}"
            for other in VILLAGERS
            if other != name
        ],
        "Look back on your day. Answer with one JSON object.",
    ]
    return "\n".join(lines)


class _Reflection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learnings: list[str] = Field(default_factory=list[str], max_length=3)
    views: dict[str, str] = Field(default_factory=dict[str, str])


def parse_reflection(answer: str | None, name: str) -> tuple[dict[str, Any] | None, str | None]:
    """The learnings and views to keep, or None and the reason the answer is unusable."""
    if not answer:
        return None, "no answer"
    try:
        reflection = _Reflection.model_validate(json.loads(answer))
    except json.JSONDecodeError:
        return None, "the answer is not JSON"
    except ValidationError as exc:
        return None, f"not a valid reflection: {exc.errors()[0]['msg']}"
    learnings = [text.strip()[:LEARNING_TEXT] for text in reflection.learnings]
    if not all(learnings):
        return None, "an empty learning"
    views: dict[str, str] = {}
    for key, text in reflection.views.items():
        other = next((n for n in VILLAGERS if n.lower() == key.strip().lower()), None)
        if other is None or other == name:
            return None, f"unknown villager {key!r}"
        if text.strip():
            views[other] = text.strip()[:LEARNING_TEXT]
    return {"learnings": learnings, "views": views}, None


REFLECT = (
    "You help a villager of a small village look back on its day. You get its character, what "
    "it remembers, what it learned before and what it thinks of the other villagers. Reply with "
    "only one JSON object and nothing else:\n"
    '{"learnings": ["Jonas is at the market around midday."], "views": {"Jonas": "Quiet, but '
    'fair and helpful."}}\n'
    '"learnings": up to 3 short new things worth remembering for the coming days (habits, '
    "promises, plans, who to ask for what), in the villager's own words, leaving out what it "
    'already learned. "views": one sentence for each villager it dealt with, saying what it '
    "now thinks of them. Use the villagers' first names: Hilde, Jonas, Greta, Lina."
)


def reflection_agent() -> dict[str, Any]:
    """The block agent that runs every villager's reflection: one model call, a JSON check."""
    reflect = {"kind": "model", "name": "reflect", "system": REFLECT, "message": "{previous}"}
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": "Village reflection",
        "description": "Lets a villager look back on its day and learn from it.",
        "sample_prompt": "You are Jonas, the fisher.\nDay 1 is over and you are going to bed.",
        "config": {"reasoning": False, "blocks": [reflect, check]},
    }
