"""Daily plans: the planner's prompt, its answer, the marked entries and its agent (M11 US1)."""

import json
from typing import Any

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.memory import remember
from agent_lab.village.plan import (
    PURPOSE_TEXT,
    entry_text,
    marks,
    parse_plan,
    plan_lines,
    plan_note,
    plan_prompt,
    planner_agent,
)
from agent_lab.village.world import new_world


def plan(*entries: dict[str, Any]) -> str:
    return json.dumps({"plan": list(entries)})


def entry(time: str, purpose: str = "work", **where: str) -> dict[str, Any]:
    return {"time": time, **where, "purpose": purpose}


def jonas(world: dict[str, Any]) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == "Jonas")


def test_the_prompt_holds_the_day_ahead() -> None:
    world = new_world()
    world["tick"] = 3  # day 1, 05:00
    me = jonas(world)
    me["learnings"] = [{"tick": 1, "text": "Hilde wants fish for the festival."}]
    me["views"] = {"Greta": {"tick": 1, "text": "Hard-working."}}
    remember(me, 2, "conversation", "Talked with Lina: the nets are torn.", ["Lina"], "pier")
    prompt = plan_prompt(world, "Jonas")
    assert prompt.startswith("You are Jonas, the fisher.")
    assert "You get up at 05:00 and go to bed at 21:00." in prompt
    assert "Your usual day: 05:00 pier, 11:00 market, 14:00 pier." in prompt
    assert "Day 1 (day 1 of spring, year 1)" in prompt
    assert "The fields are resting." in prompt
    assert "- Hilde wants fish for the festival." in prompt
    assert "- Greta: Hard-working." in prompt
    assert "Talked with Lina: the nets are torn." in prompt
    assert "Your plan so far:" not in prompt
    assert prompt.endswith("Plan your day. Answer with one JSON object.")


def test_a_revision_sees_the_plan_and_the_conversation() -> None:
    world = new_world()
    me = jonas(world)
    me["plan"] = {"day": 1, "entries": [], "revisions": 0}
    entries, _ = parse_plan(
        plan(entry("05:00", place="pier"), entry("11:00", place="market")), "Jonas"
    )
    assert entries is not None
    me["plan"]["entries"] = entries
    prompt = plan_prompt(world, "Jonas", revise="Hilde: Bring fish to the square. / Jonas: I will.")
    assert "Your plan so far:\n- 05:00 pier: work\n- 11:00 market: work" in prompt
    assert (
        "The conversation you just had:\nHilde: Bring fish to the square. / Jonas: I will."
        in prompt
    )


def test_a_valid_plan_is_sorted_and_resolved() -> None:
    answer = plan(
        entry("11:00", "ask for fish", villager="Mayor Hilde"),
        entry("5:00", "catch fish", place="the pier"),
        entry("20:30", "rest", place="home"),
    )
    entries, reason = parse_plan(answer, "Jonas")
    assert reason is None
    assert entries == [
        {"minute": 300, "place": "pier", "villager": None, "purpose": "catch fish"},
        {"minute": 660, "place": None, "villager": "Hilde", "purpose": "ask for fish"},
        {"minute": 1230, "place": "home", "villager": None, "purpose": "rest"},
    ]


def test_unusable_entries_are_dropped() -> None:
    answer = plan(
        entry("25:00", place="pier"),  # no such time
        entry("noon", place="pier"),
        entry("09:00", place="castle"),  # unknown place and no villager
        entry("10:00", villager="Jonas"),  # itself
        entry("11:00", "   ", place="market"),  # empty purpose
        entry("12:00", place="castle", villager="Greta"),  # the villager stands in
        entry("14:00", place="pier"),
    )
    entries, reason = parse_plan(answer, "Jonas")
    assert reason is None and entries is not None
    assert [(e["minute"], e["place"], e["villager"]) for e in entries] == [
        (720, None, "Greta"),
        (840, "pier", None),
    ]


def test_long_plans_and_purposes_are_cut() -> None:
    answer = plan(*[entry(f"{h:02d}:00", "x" * 200, place="pier") for h in range(18, 5, -1)])
    entries, reason = parse_plan(answer, "Jonas")
    assert reason is None and entries is not None
    assert [e["minute"] // 60 for e in entries] == [6, 7, 8, 9, 10, 11]
    assert all(len(e["purpose"]) == PURPOSE_TEXT for e in entries)


def test_invalid_plans_say_why() -> None:
    assert parse_plan(None, "Jonas") == (None, "no answer")
    assert parse_plan("Fish all day.", "Jonas") == (None, "the answer is not JSON")
    assert parse_plan('{"plan": "fish"}', "Jonas")[1].startswith("not a valid plan:")  # type: ignore[union-attr]
    one_left = plan(entry("05:00", place="pier"), entry("09:00", place="castle"))
    assert parse_plan(one_left, "Jonas") == (None, "a plan needs at least 2 entries")


def test_the_current_and_the_next_entry() -> None:
    entries, _ = parse_plan(
        plan(
            entry("05:00", place="pier"),
            entry("11:00", place="market"),
            entry("14:00", place="pier"),
        ),
        "Jonas",
    )
    assert entries is not None
    assert marks(entries, 4 * 60) == (None, 0)  # before the first
    assert marks(entries, 5 * 60) == (0, 1)
    assert marks(entries, 12 * 60) == (1, 2)
    assert marks(entries, 20 * 60) == (2, None)  # after the last
    assert plan_lines(entries, 12 * 60) == [
        "Your plan for today:",
        "- 05:00 pier: work",
        "- 11:00 market: work (now)",
        "- 14:00 pier: work (next)",
    ]


def test_entry_text_names_a_place_or_a_villager() -> None:
    assert entry_text(
        {"minute": 450, "place": "town_hall", "villager": None, "purpose": "list"}
    ) == ("07:30 town hall: list")
    assert entry_text({"minute": 660, "place": None, "villager": "Jonas", "purpose": "fish"}) == (
        "11:00 see Jonas: fish"
    )
    assert entry_text({"minute": 1260, "place": "home", "villager": None, "purpose": "rest"}) == (
        "21:00 home: rest"
    )


def test_the_planner_is_a_block_agent() -> None:
    body = planner_agent()
    assert body["template_id"] == "blocks" and body["name"] == "Village planner"
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    model, check = config.blocks
    assert model.kind == "model" and model.name == "plan" and '"plan"' in model.system
    assert '"learnings"' not in model.system  # that marks a reflection
    assert check.kind == "check" and check.rule == "valid_json"


def test_in_autumn_the_plan_sees_the_stalls_and_the_basket() -> None:
    world = new_world()
    world["tick"] = 16 * 144 + 3  # day 17, autumn
    jonas(world)["basket"] = "fish"
    prompt = plan_prompt(world, "Jonas")
    assert "You carry a basket of fish." in prompt
    assert "The festival stalls on the square are empty; they still lack fish, " in prompt
    world["tick"] = 3  # spring
    jonas(world)["basket"] = None
    prompt = plan_prompt(world, "Jonas")
    assert "festival stalls" not in prompt and "basket" not in prompt


def test_the_day_record_notes_a_plan_as_intentions() -> None:
    assert plan_note("Jonas", "05:00 pier (Catch fish)", False) == (
        "Jonas planned the day (intentions, not events): 05:00 pier (Catch fish)"
    )
    assert plan_note("Jonas", "05:00 pier (Catch fish)", True).startswith(
        "Jonas changed the plan (intentions, not events): "
    )
