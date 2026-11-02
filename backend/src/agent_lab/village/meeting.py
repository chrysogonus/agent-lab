"""The town hall meeting: every third day Hilde proposes what to build, the others vote and Hilde
decides (specs/012-building-together/research.md §5)."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.village.build import Project, buildable, built_text, entry, project_named
from agent_lab.village.memory import recall, when
from agent_lab.village.seasons import WEATHER_TEXT, date_text, festival_in, weather
from agent_lab.village.world import VILLAGERS, clock, listed

MEETING_OPENS = 17 * 60
MEETING_CLOSES = 17 * 60 + 30  # who arrives by then still votes; then Hilde decides
REASON_TEXT = 120
PROPOSALS = 3
MEMORIES_SHOWN = 8

Meeting = dict[str, Any]


def meeting_day(day: int) -> bool:
    """Every third day, but the festival's meeting moves to the day after."""
    if day % 3 == 0:
        return festival_in(day) != 0
    return day > 1 and (day - 1) % 3 == 0 and festival_in(day - 1) == 0


def next_meeting(day: int) -> int:
    while not meeting_day(day):
        day += 1
    return day


def needs_text(project: Project) -> str:
    return listed([f"{n} {goods}" for goods, n in project.needs.items()])


def _proposals_text(proposals: list[dict[str, Any]]) -> str:
    return "; ".join(f"{entry(p['key']).name} ({p['reason']})" for p in proposals)


def meeting_text(world: dict[str, Any], name: str) -> str:
    """What a villager knows about the town hall meeting, today's or the next one."""
    day = clock(world["tick"])[0]
    if not meeting_day(day):
        return f"The next town hall meeting is on day {next_meeting(day)} at 17:00."
    m: Meeting | None = (
        world["meeting"] if world["meeting"] and world["meeting"]["day"] == day else None
    )
    if m and m["outcome"]:
        if m["outcome"] == "decided" and m["decision"]:
            decision = m["decision"]
            text = (
                f"At today's town hall meeting Hilde chose {entry(decision['key']).name}: "
                f"{decision['reason']}"
            )
            return text + (" She went against the vote." if decision["against"] else "")
        if m["outcome"] == "reviewed":
            return "At today's town hall meeting Hilde talked about how the building goes."
        if m["outcome"] == "nothing left to build":
            return "Today's town hall meeting found nothing left to build."
        if m["outcome"] == "no decision":
            return "Today's town hall meeting ended without a decision."
        return f"Today's town hall meeting was {m['outcome']}."  # called off: …
    proposed: list[dict[str, Any]] = m["proposals"] if m else []
    if name == "Hilde":
        text = "You chair today's town hall meeting at 17:00; be there."
        return text + (f" You proposed: {_proposals_text(proposed)}." if proposed else "")
    if m and m["kind"] == "review":
        return (
            "Today at 17:00 the villagers meet at the town hall to talk about how the building "
            "goes."
        )
    text = "Today at 17:00 the villagers meet at the town hall to choose what to build next."
    return text + (f" Hilde proposes: {_proposals_text(proposed)}." if proposed else "")


def _villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


def _known(world: dict[str, Any], name: str) -> list[str]:
    """Who the villager is, the day, and what it learned and remembers."""
    me, tick = _villager(world, name), world["tick"]
    day, time, _ = clock(tick)
    remembered = recall(me["memories"], tick, set(), "town_hall", MEMORIES_SHOWN)
    return [
        VILLAGERS[name].persona,
        f"Day {day} ({date_text(day)}), {time}. {WEATHER_TEXT[weather(day)]}.",
        "What you have learned:",
        *([f"- {item['text']}" for item in me["learnings"]] or ["- nothing yet"]),
        "What you remember:",
        *([f"- {when(m['tick'])} {m['text']}" for m in remembered] or ["- nothing yet"]),
    ]


def proposal_prompt(world: dict[str, Any]) -> str:
    known = _known(world, "Hilde")
    return "\n".join(
        [
            *known[:2],
            "Today at 17:00 you chair the town hall meeting, where the village chooses what to "
            "build next.",
            built_text(world) or "Nothing has been built yet.",
            "What the village can build (the loads each needs; the daily trader at the market "
            "sells wood, paint and saplings for one basket of fish, vegetables or flowers each):",
            *[f"- {p.name}: {needs_text(p)}" for p in buildable(world)],
            *known[2:],
            "Propose two or three of these projects for the villagers to vote on, each with a "
            "short reason. Answer with one JSON object: "
            '{"proposals": [{"project": "<name>", "reason": "<why>"}]}',
        ]
    )


def _proposal_lines(world: dict[str, Any]) -> list[str]:
    return [
        f"- {entry(p['key']).name} ({needs_text(entry(p['key']))}): {p['reason']}"
        for p in world["meeting"]["proposals"]
    ]


def vote_prompt(world: dict[str, Any], name: str) -> str:
    known = _known(world, name)
    views = _villager(world, name)["views"]
    return "\n".join(
        [
            *known[:2],
            "You are at the town hall meeting. Hilde proposes what the village builds next:",
            *_proposal_lines(world),
            "What you think of the others:",
            *[
                f"- {o}: {views[o]['text'] if o in views else 'no view yet'}"
                for o in VILLAGERS
                if o != name
            ],
            *known[2:],
            "Vote for one proposal and give a short reason. Answer with one JSON object: "
            '{"vote": "<project>", "reason": "<why>"}',
        ]
    )


def tally(votes: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for vote in votes.values():
        if vote["key"]:
            counts[vote["key"]] = counts.get(vote["key"], 0) + 1
    return counts


def _tally_text(counts: dict[str, int]) -> str:
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return ", ".join(f"{entry(key).name} ({n})" for key, n in ranked)


def decision_prompt(world: dict[str, Any]) -> str:
    known = _known(world, "Hilde")
    votes = world["meeting"]["votes"]
    counted = {n: v for n, v in votes.items() if v["key"]}
    counts = tally(votes)
    return "\n".join(
        [
            *known[:2],
            "You chair the town hall meeting. You proposed:",
            *_proposal_lines(world),
            "The votes:",
            *(
                [f"- {n}: {entry(v['key']).name} ({v['reason']})" for n, v in counted.items()]
                or ["- nobody else came to vote"]
            ),
            *([f"Most votes: {_tally_text(counts)}."] if counts else []),
            *known[2:],
            "Decide what the village builds next: usually what most wanted, but you may choose "
            "another proposal if you give a reason. Answer with one JSON object: "
            '{"decision": "<project>", "reason": "<why>"}',
        ]
    )


class _Proposal(BaseModel):
    project: str
    reason: str = ""


class _Proposals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposals: list[_Proposal]


class _Vote(BaseModel):
    vote: str
    reason: str = ""


class _Decision(BaseModel):
    decision: str
    reason: str = ""


def _load[T: BaseModel](model: type[T], answer: str | None) -> tuple[T | None, str | None]:
    if not answer:
        return None, "no answer"
    try:
        return model.model_validate(json.loads(answer)), None
    except json.JSONDecodeError:
        return None, "the answer is not JSON"
    except ValidationError as exc:
        return None, f"not a valid answer: {exc.errors()[0]['msg']}"


def _reason(text: str) -> str:
    return text.strip()[:REASON_TEXT]


def parse_proposals(
    answer: str | None, world: dict[str, Any]
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Up to three buildable projects with Hilde's reasons; unknown, built and repeated ones are
    dropped."""
    parsed, why = _load(_Proposals, answer)
    if parsed is None:
        return None, why
    open_keys = {p.key for p in buildable(world)}
    found: list[dict[str, Any]] = []
    for item in parsed.proposals:
        key = project_named(item.project)
        if key in open_keys and all(p["key"] != key for p in found):
            found.append({"key": key, "reason": _reason(item.reason)})
    if not found:
        return None, "no project Hilde proposed can be built"
    return found[:PROPOSALS], None


def _proposed(text: str, proposals: list[dict[str, Any]]) -> str | None:
    key = project_named(text)
    return key if any(p["key"] == key for p in proposals) else None


def parse_vote(
    answer: str | None, proposals: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str | None]:
    parsed, why = _load(_Vote, answer)
    if parsed is None:
        return None, why
    key = _proposed(parsed.vote, proposals)
    if key is None:
        return None, f"{parsed.vote} is not one of Hilde's proposals"
    return {"key": key, "reason": _reason(parsed.reason)}, None


def parse_decision(
    answer: str | None, proposals: list[dict[str, Any]], votes: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, str | None]:
    """Hilde's decision (`against`: not one of the most voted), or the vote's when hers is not
    usable; None without either. The second value says why Hilde's answer was not usable."""
    counts = tally(votes)
    most = max(counts.values(), default=0)
    top = [p["key"] for p in proposals if counts.get(p["key"]) == most and most]
    parsed, why = _load(_Decision, answer)
    if parsed is not None:
        key = _proposed(parsed.decision, proposals)
        if key:
            against = bool(top) and key not in top
            return {
                "key": key,
                "reason": _reason(parsed.reason),
                "against": against,
                "by": "hilde",
            }, None
        why = f"{parsed.decision} is not one of Hilde's proposals"
    if not top:
        return None, why
    fallback = "Hilde gave no valid decision; the vote decided"
    return {"key": top[0], "reason": fallback, "against": False, "by": "vote"}, why


MEET = (
    "You help the villagers of a small village with their town hall meeting: the mayor Hilde "
    "proposes what the village builds next, the others vote, Hilde decides and hands out the "
    "work. You get who you speak for and what they know. Reply with only one JSON object and "
    "nothing else, in the shape the prompt asks for:\n"
    '{"proposals": [{"project": "A market stand", "reason": "Greta needs a place to sell"}]} '
    "for Hilde's two or three proposals,\n"
    '{"vote": "A market stand", "reason": "I sell there every day"} for a villager\'s vote,\n'
    '{"decision": "A market stand", "reason": "Most of you want it"} for Hilde\'s decision,\n'
    '{"tasks": [{"task": "buy", "goods": "wood", "villagers": ["Jonas"]}, {"task": "build", '
    '"villagers": ["Greta", "Lina"]}]} for the work Hilde hands out (buy, bring or build).\n'
    "Name projects as they are listed. Keep reasons short and in the speaker's own words."
)


def meeting_agent() -> dict[str, Any]:
    """The block agent of the town hall meeting: one model call, a JSON check."""
    model = {"kind": "model", "name": "meet", "system": MEET, "message": "{previous}"}
    check = {"kind": "check", "name": "answer-is-json", "rule": "valid_json", "value": None}
    return {
        "template_id": "blocks",
        "name": "Village meeting",
        "description": "Hilde's proposals, the villagers' votes, her decision and the work she "
        "hands out at the town hall meeting.",
        "sample_prompt": "You are Hilde, the mayor.\nPropose two or three projects. Answer with "
        "one JSON object.",
        "config": {"reasoning": False, "blocks": [model, check]},
    }
