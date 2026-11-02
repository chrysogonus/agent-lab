"""Lasting memories, recall and reflection (FR-001 to FR-005, FR-008)."""

import json
from typing import Any

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.memory import (
    IMPORTANCE,
    MEMORIES_KEPT,
    OLD_REFLECT,
    REFLECT,
    older_reflections,
    parse_reflection,
    recall,
    reflection_agent,
    reflection_prompt,
    remember,
    score,
    unreflected,
)
from agent_lab.village.world import VILLAGERS, new_world, upgrade


def hilde() -> dict[str, Any]:
    return new_world()["villagers"][0]


def test_remember_sets_importance_by_kind_and_cuts_long_text() -> None:
    v = hilde()
    remember(v, 10, "conversation", "x" * 500, ["Lina"], "square")
    [memory] = v["memories"]
    assert memory == {
        "tick": 10,
        "kind": "conversation",
        "about": ["Lina"],
        "place": "square",
        "text": "x" * 400,
        "importance": IMPORTANCE["conversation"],
    }
    assert IMPORTANCE == {
        "conversation": 3,
        "found": 2,
        "missed": 2,
        "met": 1,
        "reflection": 5,
        "festival": 5,
        "meeting": 4,
        "built": 5,
        "summary": 4,
    }


def test_the_limit_drops_the_least_valuable_old_memory() -> None:
    v = hilde()
    remember(v, 0, "reflection", "an old reflection", [], None)
    remember(v, 0, "met", "an old meeting", ["Jonas"], None)
    for tick in range(1, MEMORIES_KEPT):
        remember(v, tick, "conversation", f"talk {tick}", ["Lina"], None)
    assert len(v["memories"]) == MEMORIES_KEPT
    texts = [m["text"] for m in v["memories"]]
    assert "an old meeting" not in texts and "an old reflection" in texts
    assert texts[-1] == f"talk {MEMORIES_KEPT - 1}"  # the newest always stays


def test_recall_prefers_relevant_then_important_then_recent() -> None:
    v = hilde()
    remember(v, 0, "conversation", "Lina promised sunflowers", ["Lina"], "square")
    remember(v, 50, "met", "Met Jonas", ["Jonas"], "pier")
    for tick in range(51, 57):
        remember(v, tick, "met", f"Met Greta {tick}", ["Greta"], "fields")
    picked = recall(v["memories"], 60, {"Lina"}, None)
    assert picked[0]["text"] == "Lina promised sunflowers"  # relevant, though oldest
    assert len(picked) == 5 and [m["tick"] for m in picked] == sorted(m["tick"] for m in picked)
    at_pier = recall(v["memories"], 60, set(), "pier", limit=1)
    assert at_pier[0]["text"] == "Met Jonas"


def test_the_reflection_prompt_lists_unreflected_memories_learnings_and_views() -> None:
    v = hilde()
    remember(v, 10, "conversation", "Talked about the weather", ["Greta"], None)
    remember(v, 20, "reflection", "You reflected", [], None)
    remember(
        v, 60, "conversation", "Talked with Lina: Hilde: Sunflowers? / Lina: Yes!", ["Lina"], None
    )
    v["learnings"] = [{"tick": 20, "text": "Greta worries about rain."}]
    v["views"] = {"Lina": {"tick": 20, "text": "Cheerful and reliable."}}
    assert [m["text"] for m in unreflected(v["memories"])] == [v["memories"][2]["text"]]
    text = reflection_prompt(v, 112)
    assert text.startswith(VILLAGERS["Hilde"].persona)
    assert "Day 1 is over and you are going to bed." in text
    assert "- Day 1 14:30 Talked with Lina: Hilde: Sunflowers? / Lina: Yes!" in text
    assert "weather" not in text  # already reflected on
    assert "- Day 1: Greta worries about rain." in text
    assert "- Lina: Cheerful and reliable." in text and "- Jonas: no view yet" in text
    assert text.endswith("Answer with one JSON object.")


@pytest.mark.parametrize(
    ("answer", "result"),
    [
        (
            '{"learnings": [" Jonas sells fish at noon. "], "views": {"jonas": "Fair."}}',
            {"learnings": ["Jonas sells fish at noon."], "views": {"Jonas": "Fair."}},
        ),
        ('{"learnings": []}', {"learnings": [], "views": {}}),
        ('{"views": {"Lina": "x"}}', {"learnings": [], "views": {"Lina": "x"}}),
        (
            json.dumps({"learnings": ["y" * 300]}),
            {"learnings": ["y" * 200], "views": {}},
        ),
    ],
)
def test_valid_reflections(answer: str, result: dict[str, Any]) -> None:
    assert parse_reflection(answer, "Hilde") == (result, None)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "no answer"),
        ("I learned a lot.", "the answer is not JSON"),
        ('{"learnings": ["a", "b", "c", "d"]}', "not a valid reflection"),
        ('{"learnings": "one"}', "not a valid reflection"),
        ('{"mood": "happy"}', "not a valid reflection"),
        ('{"learnings": ["  "]}', "an empty learning"),
        ('{"views": {"Bob": "x"}}', "unknown villager 'Bob'"),
        ('{"views": {"Hilde": "me"}}', "unknown villager 'Hilde'"),
    ],
)
def test_invalid_reflections(answer: str | None, reason: str) -> None:
    result, why = parse_reflection(answer, "Hilde")
    assert result is None and why is not None and why.startswith(reason)


def test_the_reflection_agent_is_a_valid_block_agent() -> None:
    body = reflection_agent()
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    reflect, check = config.blocks
    assert reflect.kind == "model" and '"learnings"' in reflect.system
    assert check.kind == "check" and check.rule == "valid_json"
    assert not body["description"].endswith("in the village.")  # not counted as a villager


def test_upgrading_an_m7_world_keeps_it_and_adds_empty_memory() -> None:
    world = new_world()
    for v in world["villagers"]:
        for key in ("memories", "learnings", "views"):
            del v[key]
    del world["reflection_agent_id"]
    world |= {"version": 2, "tick": 40, "conversations": [{"a": "Hilde", "b": "Lina"}]}
    upgraded = upgrade(world)
    assert (upgraded["version"], upgraded["tick"], upgraded["reflection_agent_id"]) == (7, 40, None)
    assert all(v["memories"] == [] and v["views"] == {} for v in upgraded["villagers"])
    assert upgraded["conversations"][0]["transcript"] == []


# --- M14 US4: memory that fades and fits the season (FR-011, FR-012) ---

DAY = 144  # ticks


def test_a_memory_from_another_season_counts_for_less() -> None:
    v = hilde()
    remember(v, 20 * DAY, "festival", "The harvest festival on the square.", ["Lina"], "square")
    remember(v, 36 * DAY, "reflection", "You looked back on your day.", [], None)
    now = 37 * DAY + 30  # summer of year 2; the festival was last autumn
    festival, yesterday = v["memories"]
    assert score(festival, now, set(), None) < score(yesterday, now, set(), None)
    assert [m["kind"] for m in recall(v["memories"], now, set(), None, limit=1)] == ["reflection"]
    with_lina = score(festival, now, {"Lina"}, None)
    assert with_lina > score(yesterday, now, {"Lina"}, None)  # about someone at hand: kept


def test_older_reflections_are_listed_and_asked_to_be_summed_up() -> None:
    v = hilde()
    for day in range(1, 8):
        remember(v, day * DAY, "reflection", f"Looked back on day {day}.", [], None)
    remember(v, 9 * DAY, "conversation", "Talked with Jonas.", ["Jonas"], None)
    now = 10 * DAY
    old = older_reflections(v["memories"], now)
    assert [m["text"] for m in old] == [f"Looked back on day {d}." for d in range(1, 7)]
    text = reflection_prompt(v, now)
    assert "Your older reflections:\n- Day 2 04:30 Looked back on day 1.\n" in text
    assert '"summary"' in text
    v["memories"] = v["memories"][2:]  # five old ones are not yet worth folding
    assert older_reflections(v["memories"], now) == []
    assert "Your older reflections:" not in reflection_prompt(v, now)


def test_a_reflection_may_carry_a_summary() -> None:
    answer = json.dumps({"learnings": [], "summary": " Spring was busy. " + "z" * 500})
    result, why = parse_reflection(answer, "Hilde")
    assert why is None and result is not None
    assert result["summary"] == ("Spring was busy. " + "z" * 500)[:400]
    assert "summary" not in (parse_reflection('{"learnings": []}', "Hilde")[0] or {})
    assert IMPORTANCE["summary"] == 4


def test_the_reflection_text_asks_for_a_summary_and_keeps_its_history() -> None:
    assert '"summary"' in REFLECT and all('"summary"' not in old for old in OLD_REFLECT)
    assert REFLECT.startswith(OLD_REFLECT[0][:200])
