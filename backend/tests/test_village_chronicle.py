"""The village chronicle's prompt, answers and agent (M10, FR-003, FR-004)."""

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.chronicle import (
    ENTRY_TEXT,
    TITLE_TEXT,
    chronicle_prompt,
    chronicler_agent,
    parse_entry,
    retry_prompt,
    weather_slips,
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
        "What happened (what villagers said or planned are their claims and intentions, not "
        "events; never report one as an event; the weather is the one given above):\n"
        "- 09:30 Greta met Jonas." in prompt
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


@pytest.mark.parametrize(
    ("kind", "text", "slips"),
    [
        ("sun", "They hurried before the storm arrived.", ["storm"]),
        ("sun", "A sunny day; Greta met Jonas.", []),
        ("rain", "The storm worsened under low clouds.", ["storm"]),
        ("storm", "Rain lashed the pier under dark clouds.", []),
        ("fog", "The mist lifted by noon.", []),
        ("clouds", "It rained at noon.", ["rain"]),
        ("snow", "Snow fell from grey clouds.", []),
        ("sun", "Fog and thunder.", ["storm", "fog"]),
    ],
)
def test_weather_other_than_the_days_is_found(kind: str, text: str, slips: list[str]) -> None:
    assert weather_slips(text, kind) == slips


def test_an_entry_naming_other_weather_is_sent_back() -> None:
    entry = {"title": "Storm coming", "text": "They hurried before the storm arrived."}
    prompt = retry_prompt("Day 1 …\nWrite the chronicle entry.", entry, ["storm"], "sun")
    assert prompt.startswith("Day 1 …\nWrite the chronicle entry.\n")
    assert '"They hurried before the storm arrived."' in prompt
    assert "It mentions storm, but the day's weather was: Sunny." in prompt
    assert prompt.endswith("Answer with one JSON object.")


def test_notes_naming_other_weather_are_marked_as_talk() -> None:
    """M14 (FR-013): villagers talk about storms they expect; the chronicler took them for real."""
    world = new_world()
    day = next(d for d in range(1, 29) if weather(d) == "sun")
    record = {
        "day": day,
        "items": [
            {"tick": (day - 1) * 144 + 30, "text": "Greta and Jonas talked: Greta: A storm comes!"},
            {"tick": (day - 1) * 144 + 31, "text": "Lina set out to go to the market."},
        ],
    }
    prompt = chronicle_prompt(world, record)
    assert "Greta: A storm comes! (talk, not the day's weather)" in prompt
    assert "Lina set out to go to the market.\n" in prompt


def test_the_prompt_opens_the_day_with_its_happenings() -> None:
    """M15 (FR-004): the day's happenings are events, and how they ended."""
    world = new_world()
    world["happenings"] = [
        {
            "kind": "animal",
            "state": "dealt",
            "by": "Jonas",
            "concerns": "Greta",
            "details": {"text": "Greta's goat"},
        },
        {
            "kind": "peddler",
            "state": "passed",
            "by": None,
            "concerns": None,
            "details": {"text": "a peddler with a kite", "goods": "a kite"},
        },
    ]
    prompt = chronicle_prompt(world, {"day": 1, "items": []})
    assert (
        "Today: Greta's goat got lost, and Jonas led it home; a peddler came with a kite, "
        "and nobody traded for it."
    ) in prompt
    assert "Today:" not in chronicle_prompt(new_world(), {"day": 1, "items": []})
