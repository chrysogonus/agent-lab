"""The village chronicle: a diary entry about each day, written at night by a block agent
(specs/010-village-seasons/research.md §6)."""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.village.build import built_text
from agent_lab.village.seasons import WEATHER_TEXT, date_text, festival_in, growth_text, weather
from agent_lab.village.work import stalls_text
from agent_lab.village.world import clock

CHRONICLE_KEPT = 28  # one village year
HAPPENED = (
    "What happened (what villagers said or planned are their claims and intentions, not events; "
    "never report one as an event; the weather is the one given above):"
)
WEATHER_WORDS = {  # how an entry names each weather
    "sun": r"\bsun",
    "clouds": r"\bcloud",
    "rain": r"\brain",
    "storm": r"\bstorm|\bthunder|\blightning",
    "fog": r"\bfog|\bmist",
    "snow": r"\bsnow",
}
GOES_WITH = {"storm": ("rain", "clouds"), "rain": ("clouds",), "snow": ("clouds",)}
TITLE_TEXT = 60
ENTRY_TEXT = 800


def chronicle_prompt(world: dict[str, Any], record: dict[str, Any]) -> str:
    day = record["day"]
    lines = [
        f"Day {day} ({date_text(day)}). {WEATHER_TEXT[weather(day)]}.",
        *[growth_text(place, world["growth"]) for place in ("fields", "flower_garden")],
        *([stalls_text(world["stalls"])] if festival_in(day) == 0 else []),
        *filter(None, [built_text(world), _today(world["happenings"])]),
        HAPPENED,
        *(
            [f"- {clock(i['tick'])[1]} {_marked(i['text'], day)}" for i in record["items"]]
            or ["- nothing"]
        ),
        "Write the chronicle entry for this day. Answer with one JSON object.",
    ]
    return "\n".join(lines)


def _today(happenings: list[dict[str, Any]]) -> str | None:
    """The day's happenings and how they ended (M15)."""
    told: list[str] = []
    for h in happenings:
        text, by, dealt = h["details"]["text"], h["by"], h["state"] == "dealt"
        if h["kind"] == "letter":
            told.append(f"a letter came for {h['concerns']}" + (" and was read" if dealt else ""))
        elif h["kind"] == "visitor":
            told.append(f"{text} came to visit {h['concerns']}")
        elif h["kind"] == "animal":
            told.append(f"{text} got lost" + (f", and {by} led it home" if dealt else ""))
        elif h["kind"] == "repair":
            told.append(f"{text} broke" + (f", and {by} mended it" if dealt else ""))
        else:
            goods = h["details"]["goods"]
            how = f"{by} traded for it" if dealt else "nobody traded for it"
            told.append(f"a peddler came with {goods}, and {how}")
    return f"Today: {'; '.join(told)}." if told else None


def _marked(note: str, day: int) -> str:
    """A note naming weather the day did not have is talk: the chronicler took it for the
    weather in 9 of 18 chronicles (M13)."""
    return f"{note} (talk, not the day's weather)" if weather_slips(note, weather(day)) else note


def weather_slips(text: str, kind: str) -> list[str]:
    """The weather an entry names that the day did not have (a storm day may rain, …)."""
    allowed = {kind, *GOES_WITH.get(kind, ())}
    return [
        k for k, words in WEATHER_WORDS.items() if k not in allowed and re.search(words, text, re.I)
    ]


def retry_prompt(prompt: str, entry: dict[str, str], slips: list[str], kind: str) -> str:
    """The prompt again, with the entry that named other weather and the day's real weather."""
    return (
        f'{prompt}\nYour entry, titled "{entry["title"]}": "{entry["text"]}"\n'
        f"It mentions {' and '.join(slips)}, but the day's weather was: {WEATHER_TEXT[kind]}. "
        "No other weather came or was on its way, whatever the villagers said. Write the entry "
        "again without it. Answer with one JSON object."
    )


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
