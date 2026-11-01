"""The village chronicle's prompt, answers and agent (M10, FR-003, FR-004)."""

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.chronicle import (
    ENTRY_TEXT,
    TITLE_TEXT,
    chronicle_prompt,
    chronicler_agent,
    parse_entry,
)
from agent_lab.village.seasons import WEATHER_TEXT, weather
from agent_lab.village.world import new_world


def test_the_prompt_names_the_day_its_weather_the_places_and_what_happened() -> None:
    world = new_world()
    record = {"day": 17, "items": [{"tick": 144 * 16 + 30, "text": "Greta met Jonas."}]}
    prompt = chronicle_prompt(world, record)
    assert prompt.startswith(f"Day 17 (day 3 of autumn, year 1). {WEATHER_TEXT[weather(17)]}.")
    assert "The fields are resting." in prompt and "The flower garden is budding." in prompt
    assert (
        "What happened (what villagers said are their claims, not events; never report a claim "
        "as an event; the weather is the one given above):\n- 09:30 Greta met Jonas." in prompt
    )
    assert '"learnings"' not in prompt


def test_an_empty_day_still_gets_a_prompt() -> None:
    assert "- nothing" in chronicle_prompt(new_world(), {"day": 1, "items": []})


def test_a_valid_answer_becomes_an_entry_cut_to_size() -> None:
    entry, reason = parse_entry('{"title": " Rain ", "text": "It rained."}')
    assert (entry, reason) == ({"title": "Rain", "text": "It rained."}, None)
    long = parse_entry(f'{{"title": "{"t" * 100}", "text": "{"x" * 1000}"}}')[0]
    assert long is not None
    assert (len(long["title"]), len(long["text"])) == (TITLE_TEXT, ENTRY_TEXT)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "no answer"),
        ("", "no answer"),
        ("a quiet day", "the answer is not JSON"),
        ("[]", "not a valid entry"),
        ('{"title": "Rain"}', "not a valid entry"),
        ('{"title": "Rain", "text": 3}', "not a valid entry"),
        ('{"title": "Rain", "text": "x", "mood": "sad"}', "not a valid entry"),
        ('{"title": " ", "text": "x"}', "an empty title or text"),
    ],
)
def test_invalid_answers_add_nothing(answer: str | None, reason: str) -> None:
    entry, why = parse_entry(answer)
    assert entry is None and why is not None and why.startswith(reason)


def test_the_chronicler_is_a_valid_block_agent() -> None:
    body = chronicler_agent()
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    write, check = config.blocks
    assert write.kind == "model" and '"learnings"' not in write.system  # not a reflection
    assert check.kind == "check" and check.rule == "valid_json"
    assert not body["description"].endswith("in the village.")  # not counted as a villager


def test_the_festival_day_names_the_stalls() -> None:
    world = new_world()
    world["stalls"] = {"fish": 1, "vegetables": 0, "flowers": 2}
    stalls = "The festival stalls on the square hold fish and flowers; they still lack vegetables."
    assert stalls in chronicle_prompt(world, {"day": 21, "items": []})
    assert "festival stalls" not in chronicle_prompt(world, {"day": 20, "items": []})
