"""The village chronicle: a diary entry about each day, written at night by a block agent
(specs/010-village-seasons/research.md §6)."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.village.seasons import WEATHER_TEXT, date_text, festival_in, growth_text, weather
from agent_lab.village.work import stalls_text
from agent_lab.village.world import clock

CHRONICLE_KEPT = 28  # one village year
TITLE_TEXT = 60
ENTRY_TEXT = 800


def chronicle_prompt(world: dict[str, Any], record: dict[str, Any]) -> str:
    day = record["day"]
    lines = [
        f"Day {day} ({date_text(day)}). {WEATHER_TEXT[weather(day)]}.",
        *[growth_text(place, world["growth"]) for place in ("fields", "flower_garden")],
        *([stalls_text(world["stalls"])] if festival_in(day) == 0 else []),
        "What happened (what villagers said are their claims, not events; never report a claim "
        "as an event; the weather is the one given above):",
        *([f"- {clock(i['tick'])[1]} {i['text']}" for i in record["items"]] or ["- nothing"]),
        "Write the chronicle entry for this day. Answer with one JSON object.",
    ]
    return "\n".join(lines)


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    text: str


def parse_entry(answer: str | None) -> tuple[dict[str, str] | None, str | None]:
    """The title and text to keep, or None and the reason the answer is unusable."""
    if not answer:
        return None, "no answer"
    try:
        entry = _Entry.model_validate(json.loads(answer))
    except json.JSONDecodeError:
        return None, "the answer is not JSON"
    except ValidationError as exc:
        return None, f"not a valid entry: {exc.errors()[0]['msg']}"
    title, text = entry.title.strip()[:TITLE_TEXT], entry.text.strip()[:ENTRY_TEXT]
    if not (title and text):
        return None, "an empty title or text"
    return {"title": title, "text": text}, None


CHRONICLE = (
    "You keep the chronicle of a small village with four villagers: Mayor Hilde, Jonas the "
    "fisher, Greta the farmer and Lina the flower girl. You get one day: its date and weather, "
    "how the fields and the flower garden are doing, and what happened, with times. Reply with "
    'only one JSON object and nothing else: {"title": "...", "text": "..."}\n'
    '"title": a few words of your own naming what made this day different from the others. '
    '"text": three to five sentences in the warm voice of a village chronicle about what really '
    "happened that day: who met whom, what they said or promised, the weather and the places. "
    "Do not invent events."
)


def chronicler_agent() -> dict[str, Any]:
    """The block agent that writes the chronicle: one model call, a JSON check."""
    write = {"kind": "model", "name": "chronicle", "system": CHRONICLE, "message": "{previous}"}
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": "Village chronicler",
        "description": "Writes the village chronicle: a diary entry about each day.",
        "sample_prompt": "Day 1 (day 1 of spring, year 1). Sunny.\nWhat happened:\n- nothing",
        "config": {"reasoning": False, "blocks": [write, check]},
    }
