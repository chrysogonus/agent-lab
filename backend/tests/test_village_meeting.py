"""The town hall meeting: when, the prompts, proposals, votes and Hilde's decision
(FR-004 to FR-008)."""

import json
from typing import Any

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.build import new_project
from agent_lab.village.meeting import (
    decision_prompt,
    meeting_agent,
    meeting_day,
    meeting_text,
    next_meeting,
    parse_decision,
    parse_proposals,
    parse_vote,
    proposal_prompt,
    tally,
    vote_prompt,
)
from agent_lab.village.memory import remember
from agent_lab.village.world import new_world

PROPOSALS = [
    {"key": "market_stand", "reason": "Greta needs a place to sell."},
    {"key": "paint_lina", "reason": "Her house is grey."},
]


def tick_of(day: int, hour: int, minute: int = 0) -> int:
    return ((day - 1) * 1440 + hour * 60 + minute - 270) // 10


def world_on(day: int = 3, hour: int = 9, **changes: Any) -> dict[str, Any]:
    world = new_world()
    world["tick"] = tick_of(day, hour)
    for v in world["villagers"]:
        v["asleep"] = False
    return world | changes


def meeting(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "day": 3,
        "kind": "vote",
        "proposals": PROPOSALS,
        "votes": {},
        "present": [],
        "decision": None,
        "outcome": None,
    }
    return base | changes


def test_meeting_days() -> None:
    days = [d for d in range(1, 30) if meeting_day(d)]
    # every third day; day 21 is the festival (autumn day 7), so its meeting moves to day 22
    assert days == [3, 6, 9, 12, 15, 18, 22, 24, 27]
    assert next_meeting(1) == 3 and next_meeting(3) == 3 and next_meeting(19) == 22
    assert meeting_day(49 + 1) is False and meeting_day(48)  # year 2: day 49 is not divisible


def test_the_proposal_prompt() -> None:
    world = world_on(built=[{"key": "boat", "day": 2}])
    me = world["villagers"][0]
    me["learnings"] = [{"tick": 1, "text": "Greta wants a stand."}]
    remember(me, 2, "conversation", "Talked with Lina: her house needs paint.", ["Lina"], "square")
    prompt = proposal_prompt(world)
    assert prompt.startswith("You are Hilde,")
    assert "Day 3 (day 3 of spring, year 1)" in prompt
    assert "Built so far: A rowing boat lies at the pier." in prompt
    assert "- A market stand: 3 wood and 1 paint" in prompt
    assert "- Paint Lina's house: 2 paint" in prompt
    assert "A rowing boat" not in prompt.split("What the village can build")[1].split("\n- ")[0]
    assert "- Greta wants a stand." in prompt and "her house needs paint" in prompt
    assert prompt.endswith(
        'Answer with one JSON object: {"proposals": [{"project": "<name>", "reason": "<why>"}]}'
    )


def test_the_vote_prompt() -> None:
    world = world_on(meeting=meeting())
    greta = world["villagers"][2]
    greta["views"] = {"Hilde": {"tick": 1, "text": "Bossy but fair."}}
    prompt = vote_prompt(world, "Greta")
    assert prompt.startswith("You are Greta,")
    assert "- A market stand (3 wood and 1 paint): Greta needs a place to sell." in prompt
    assert "- Paint Lina's house (2 paint): Her house is grey." in prompt
    assert "- Hilde: Bossy but fair." in prompt
    assert prompt.endswith('Answer with one JSON object: {"vote": "<project>", "reason": "<why>"}')


def test_the_decision_prompt() -> None:
    votes = {
        "Greta": {"key": "market_stand", "reason": "I sell there."},
        "Jonas": {"key": "paint_lina", "reason": "It looks sad."},
        "Lina": {"key": None, "reason": "not one of the proposals"},
    }
    prompt = decision_prompt(world_on(meeting=meeting(votes=votes)))
    assert prompt.startswith("You are Hilde,")
    assert "- Greta: A market stand (I sell there.)" in prompt
    assert "- Jonas: Paint Lina's house (It looks sad.)" in prompt
    assert "- Lina:" not in prompt  # an invalid vote is not counted
    assert "Most votes: A market stand (1), Paint Lina's house (1)." in prompt
    assert prompt.endswith(
        'Answer with one JSON object: {"decision": "<project>", "reason": "<why>"}'
    )
    alone = decision_prompt(world_on(meeting=meeting()))
    assert "- nobody else came to vote" in alone


def proposals(*items: tuple[str, str]) -> str:
    return json.dumps({"proposals": [{"project": p, "reason": r} for p, r in items]})


def test_parse_proposals() -> None:
    world = world_on(built=[{"key": "boat", "day": 2}])
    answer = proposals(
        ("the market stand", "  Greta needs it  "),
        ("A rowing boat", "built already"),
        ("a castle", "nonsense"),
        ("market stand", "twice"),
        ("Paint Lina's house", "x" * 200),
        ("paint_town_hall", "third"),
        ("barn", "a fourth"),
    )
    found, why = parse_proposals(answer, world)
    assert why is None and found == [
        {"key": "market_stand", "reason": "Greta needs it"},
        {"key": "paint_lina", "reason": "x" * 120},
        {"key": "paint_town_hall", "reason": "third"},
    ]
    assert parse_proposals(proposals(("a castle", "no")), world) == (
        None,
        "no project Hilde proposed can be built",
    )
    assert parse_proposals("not json", world) == (None, "the answer is not JSON")
    assert parse_proposals('{"proposal": []}', world)[0] is None


def test_parse_vote() -> None:
    assert parse_vote('{"vote": "Market Stand", "reason": "I sell"}', PROPOSALS) == (
        {"key": "market_stand", "reason": "I sell"},
        None,
    )
    assert parse_vote('{"vote": "A barn", "reason": "big"}', PROPOSALS) == (
        None,
        "A barn is not one of Hilde's proposals",
    )
    assert parse_vote(None, PROPOSALS) == (None, "no answer")


def test_tally_counts_valid_votes() -> None:
    votes = {
        "Greta": {"key": "market_stand", "reason": ""},
        "Jonas": {"key": "market_stand", "reason": ""},
        "Lina": {"key": None, "reason": "invalid"},
    }
    assert tally(votes) == {"market_stand": 2}


def test_parse_decision_with_and_against_the_vote() -> None:
    votes = {
        "Greta": {"key": "market_stand", "reason": ""},
        "Jonas": {"key": "market_stand", "reason": ""},
        "Lina": {"key": "paint_lina", "reason": ""},
    }
    follow = '{"decision": "A market stand", "reason": "Most want it."}'
    assert parse_decision(follow, PROPOSALS, votes) == (
        {"key": "market_stand", "reason": "Most want it.", "against": False, "by": "hilde"},
        None,
    )
    against = '{"decision": "paint lina\'s house", "reason": "Lina deserves it."}'
    assert parse_decision(against, PROPOSALS, votes)[0] == {
        "key": "paint_lina",
        "reason": "Lina deserves it.",
        "against": True,
        "by": "hilde",
    }
    tie = {"Greta": votes["Greta"], "Lina": votes["Lina"]}
    tied = parse_decision(against, PROPOSALS, tie)[0]
    assert tied is not None and tied["against"] is False  # one of the most voted
    alone = parse_decision(against, PROPOSALS, {})[0]
    assert alone is not None and alone["against"] is False


def test_an_invalid_decision_falls_back_to_the_vote() -> None:
    votes = {
        "Greta": {"key": "paint_lina", "reason": ""},
        "Jonas": {"key": "market_stand", "reason": ""},
    }
    decision, why = parse_decision('{"decision": "a castle", "reason": "x"}', PROPOSALS, votes)
    assert decision == {
        "key": "market_stand",  # a tie: the first in Hilde's order
        "reason": "Hilde gave no valid decision; the vote decided",
        "against": False,
        "by": "vote",
    }
    assert why == "a castle is not one of Hilde's proposals"
    assert parse_decision("nonsense", PROPOSALS, {}) == (None, "the answer is not JSON")


def test_meeting_texts() -> None:
    assert (
        meeting_text(world_on(day=1), "Greta") == "The next town hall meeting is on day 3 at 17:00."
    )
    before = world_on(meeting=meeting())
    assert meeting_text(before, "Greta") == (
        "Today at 17:00 the villagers meet at the town hall to choose what to build next. Hilde "
        "proposes: A market stand (Greta needs a place to sell.); Paint Lina's house (Her house "
        "is grey.)."
    )
    assert meeting_text(before, "Hilde") == (
        "You chair today's town hall meeting at 17:00; be there. You proposed: A market stand "
        "(Greta needs a place to sell.); Paint Lina's house (Her house is grey.)."
    )
    assert meeting_text(world_on(), "Greta") == (
        "Today at 17:00 the villagers meet at the town hall to choose what to build next."
    )
    review = world_on(meeting=meeting(kind="review", proposals=[]))
    review["project"] = new_project("barn", 2)
    assert meeting_text(review, "Lina") == (
        "Today at 17:00 the villagers meet at the town hall to talk about how the building goes."
    )
    decision = {"key": "paint_lina", "reason": "Lina deserves it.", "against": True, "by": "hilde"}
    decided = world_on(meeting=meeting(decision=decision, outcome="decided"))
    assert meeting_text(decided, "Jonas") == (
        "At today's town hall meeting Hilde chose Paint Lina's house: Lina deserves it. She went "
        "against the vote."
    )
    off = world_on(meeting=meeting(outcome="called off: Hilde did not come"))
    assert meeting_text(off, "Jonas") == (
        "Today's town hall meeting was called off: Hilde did not come."
    )


def test_the_meeting_agent_is_a_valid_block_agent() -> None:
    body = meeting_agent()
    assert body["name"] == "Village meeting" and body["template_id"] == "blocks"
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    system = body["config"]["blocks"][0]["system"]
    for shape in ('{"proposals"', '{"vote"', '{"decision"', '{"tasks"'):
        assert shape in system
