"""Fixtures, turn checks, scenarios and their results (FR-004 to FR-014, SC-005)."""

import json
from pathlib import Path
from typing import Any

import pytest
from helpers import answer, fake_models
from test_village_runner import responder

from agent_lab.agents.react import build_graph
from agent_lab.bus import Bus
from agent_lab.llm.fake import FakeLLM
from agent_lab.llm.models import Models
from agent_lab.store import Run, Store
from agent_lab.village.build import entry
from agent_lab.village.evals.__main__ import main, parser
from agent_lab.village.evals.checks import (
    add_check,
    judge,
    load_checks,
    prompt_of,
    read_owner,
    run_checks,
)
from agent_lab.village.evals.fixtures import FixtureError, build_world
from agent_lab.village.evals.results import Results, checks_table, compare, compare_table, wilson
from agent_lab.village.evals.scenarios import CONDITIONS, run_scenarios
from agent_lab.village.runner import Village
from agent_lab.village.trade import trader_stock
from agent_lab.village.turn import observation
from agent_lab.village.world import clock, door, place_at, place_cells

A_PLAN_ANSWER = json.dumps(
    {
        "plan": [
            {"time": "06:00", "place": "fields", "purpose": "Weed the rows"},
            {"time": "11:00", "place": "market", "purpose": "Sell vegetables"},
        ]
    }
)


def villager(world: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in world["villagers"] if v["name"] == name)


# --- fixtures ---


def test_a_fixture_sets_the_clock_and_wakes_who_it_names() -> None:
    world = build_world({"day": 66, "time": "10:30", "villagers": {"Lina": {"at": "market"}}})
    assert clock(world["tick"])[:2] == (66, "10:30")
    lina = villager(world, "Lina")
    assert not lina["asleep"] and place_at(lina["x"], lina["y"]) == "market"
    assert lina["last_decided"] == world["tick"]
    jonas = villager(world, "Jonas")
    assert jonas["asleep"] and (jonas["x"], jonas["y"]) == door("Jonas")
    assert world["day_record"] == {"day": 66, "items": []}  # notes are kept from the start
    assert world["growth"]["flower_garden"]["stage"] == "blooming"  # summer
    assert world["born"] > 0


def test_a_fixture_with_everything() -> None:
    world = build_world(
        {
            "day": 67,
            "time": "10:00",
            "villagers": {
                "Lina": {
                    "at": "site",
                    "carrying": "saplings",
                    "working": "site",
                    "goal": "town_hall",
                    "memories": ["Hilde asked me for saplings."],
                    "learnings": ["The trader comes at nine."],
                    "inbox": [{"from": "Greta", "text": "Need help?"}],
                    "said": ["Morning!"],
                    "events": ["You arrived at the building site."],
                    "plan": [
                        {"time": "11:00", "villager": "Greta", "purpose": "Talk"},
                        {"time": "14:00", "place": "market", "purpose": "Sell"},
                    ],
                },
                "Greta": {"at": [18, 11]},
                "Hilde": {"at": "home", "asleep": True},
            },
            "conversations": [["Lina", "Greta", 2]],
            "trader": True,
            "project": {
                "key": "trees_square",
                "site": {"saplings": 1},
                "used": {"saplings": 1},
                "tasks": [{"task": "build", "goods": None, "villagers": ["Lina"]}],
            },
            "built": ["boat"],
            "meeting": {
                "kind": "vote",
                "proposals": [{"key": "barn", "reason": "Room."}],
                "votes": {"Greta": {"key": "barn", "reason": "Yes."}},
                "present": ["Greta"],
            },
            "stalls": {"fish": 1},
        }
    )
    lina = villager(world, "Lina")
    assert (lina["x"], lina["y"]) == entry("trees_square").site[0]
    assert lina["basket"] == "saplings" and lina["working"] == {"place": "site", "steps": 0}
    assert lina["goal"] == {"kind": "place", "place": "town_hall"}
    assert lina["memories"][0]["text"] == "Hilde asked me for saplings."
    assert lina["learnings"][0]["text"] == "The trader comes at nine."
    assert lina["inbox"][0] | {"tick": 0} == {
        "from": "Greta",
        "to": "Lina",
        "text": "Need help?",
        "tick": 0,
    }
    assert lina["said"] == ["Morning!"] and lina["events"][0]["text"].startswith("You arrived")
    assert [e["minute"] for e in lina["plan"]["entries"]] == [660, 840]
    assert lina["plan"]["entries"][0]["villager"] == "Greta"
    assert lina["neighbours"] == ["Greta"]  # already next to each other: no "met" on step one
    assert world["conversations"][0] | {"last_tick": 0, "transcript": []} == {
        "a": "Lina",
        "b": "Greta",
        "lines": 2,
        "last_tick": 0,
        "transcript": [],
    }
    assert world["trader"] == {"day": 67, "stock": trader_stock(67)}
    assert world["project"]["site"]["saplings"] == 1 and world["project"]["used"]["saplings"] == 1
    assert world["built"] == [{"key": "boat", "day": 66}]
    assert world["meeting"]["proposals"] == [{"key": "barn", "reason": "Room.", "run_id": None}]
    assert world["meeting"]["votes"]["Greta"]["run_id"] is None
    assert world["stalls"] == {"fish": 1, "vegetables": 0, "flowers": 0}
    facts = observation(world, "Lina")
    assert "You carry a load of saplings." in facts and "A trader is at the market" in facts
    assert "The village is building: Plant trees by the square" in facts


@pytest.mark.parametrize(
    ("fixture", "error"),
    [
        ({"day": 3, "time": "10:00", "weather": "sun"}, "unknown key 'weather'"),
        ({"day": 3, "time": "25:00"}, "bad time '25:00'"),
        ({"day": 1, "time": "03:00"}, "before the village's first morning"),
        ({"day": 3, "time": "10:00", "villagers": {"Tom": {}}}, "unknown villager 'Tom'"),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"at": "harbour"}}},
            "unknown place 'harbour'",
        ),
        ({"day": 3, "time": "10:00", "villagers": {"Lina": {"at": [0, 0]}}}, "not a walkable cell"),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"carrying": "gold"}}},
            "unknown goods 'gold'",
        ),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"at": "site"}}},
            "no project, so no building site",
        ),
        (
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"mood": "happy"}}},
            "unknown key 'mood' for Lina",
        ),
        ({"day": 3, "time": "10:00", "project": {"key": "castle"}}, "unknown project 'castle'"),
    ],
)
def test_bad_fixtures_say_what_is_wrong(fixture: dict[str, Any], error: str) -> None:
    with pytest.raises(FixtureError, match=error):
        build_world(fixture)


def test_a_fixture_villager_may_be_set_on_something() -> None:
    world = build_world(
        {
            "day": 67,
            "time": "13:00",
            "project": {"key": "trees_square", "site": {"saplings": 2}},
            "villagers": {
                "Greta": {
                    "at": "site",
                    "intention": {"action": "build", "until": "15:00", "purpose": "trees"},
                },
                "Lina": {"intention": {"action": "find", "villager": "Greta", "say": "Hi"}},
            },
        }
    )
    greta, lina = world["villagers"][2], world["villagers"][3]
    assert (greta["intention"]["kind"], greta["intention"]["until"]) == ("build", 900)
    assert greta["intention"]["purpose"] == "trees"
    assert (lina["intention"]["kind"], lina["intention"]["say"]) == ("see", "Hi")
    with pytest.raises(FixtureError, match="unknown intention 'dance'"):
        build_world(
            {"day": 3, "time": "10:00", "villagers": {"Lina": {"intention": {"action": "dance"}}}}
        )


def test_a_fixture_memory_may_have_its_own_day_and_kind() -> None:
    world = build_world(
        {
            "day": 66,
            "time": "05:30",
            "villagers": {
                "Greta": {
                    "memories": [
                        "Talked with Lina.",
                        {"day": 49, "kind": "festival", "text": "The harvest festival."},
                    ]
                }
            },
        }
    )
    today, festival = world["villagers"][2]["memories"]
    assert today["kind"] == "conversation" and today["tick"] == world["tick"] - 1
    assert (festival["kind"], festival["importance"]) == ("festival", 5)
    assert festival["tick"] == 48 * 144 + (18 * 60 - 270) // 10  # day 49, 18:00
    with pytest.raises(FixtureError, match="unknown memory kind 'dream'"):
        build_world(
            {
                "day": 66,
                "time": "05:30",
                "villagers": {"Greta": {"memories": [{"day": 1, "kind": "dream", "text": "x"}]}},
            }
        )


@pytest.mark.parametrize(
    ("answer", "passed", "why"),
    [
        (A_PLAN_ANSWER, True, None),
        (A_PLAN_ANSWER.replace("Weed", "Ready for the Festival"), False, "it names: festival"),
        ('{"plan": "none"}', False, "not valid"),
    ],
)
def test_an_answer_must_not_name_some_words(answer: str, passed: bool, why: str | None) -> None:
    check = a_check({"excludes": ["festival", "stalls"]}, agent="planner", **{"as": "Greta"})
    check["situation"]["prompt"] = "plan"
    ok, reason = judge(check, answer, prompt_of(check)[1])
    assert ok is passed and (reason is None if why is None else why in (reason or ""))


@pytest.mark.parametrize(
    ("answer", "passed"),
    [
        ('{"action": "give"}', True),
        ('{"action": "bring"}', True),
        ('{"action": "build"}', True),  # at the site: work there, setting the load down first
        ('{"action": "move", "place": "market"}', False),
    ],
)
def test_any_of_several_answers(answer: str, passed: bool) -> None:
    expect = {
        "any_of": [
            {"action": {"action": "give", "to": None}},
            {"action": {"action": "bring"}},
            {"action": {"action": "work", "place": "site"}},
        ]
    }
    check = a_check(expect)
    ok, why = judge(check, answer, prompt_of(check)[1])
    assert ok is passed and (why is None) is passed


def test_a_fixture_may_have_happenings() -> None:
    world = build_world(
        {
            "day": 30,
            "time": "10:00",
            "villagers": {"Jonas": {"at": "market"}, "Greta": {"at": "fields"}},
            "happenings": [
                {"kind": "animal", "place": "market", "concerns": "Greta"},
                {"kind": "letter", "concerns": "Lina", "details": {"text": "News."}},
                {"kind": "repair", "place": "pier", "details": {"text": "the boards of the pier"}},
            ],
        }
    )
    goat, letter, boards = world["happenings"]
    assert goat["state"] == "here" and goat["cell"] in [list(c) for c in place_cells("market")]
    assert goat["details"] == {"text": "Greta's goat", "own": "your goat"}
    assert goat["seen_by"] == ["Jonas", "Greta"]  # the fixture's villagers know of it
    assert letter["cell"] == list(door("Lina")) and letter["details"]["text"] == "News."
    assert boards["place"] == "pier"
    with pytest.raises(FixtureError, match="unknown happening 'fair'"):
        build_world({"day": 3, "time": "10:00", "happenings": [{"kind": "fair"}]})


def test_a_cell_fixture_and_a_place_fixture_agree() -> None:
    cell = place_cells("pier")[0]
    world = build_world({"day": 2, "time": "06:00", "villagers": {"Jonas": {"at": list(cell)}}})
    assert place_at(villager(world, "Jonas")["x"], villager(world, "Jonas")["y"]) == "pier"


# --- results: ranges, comparisons, storage ---


def test_wilson_ranges() -> None:
    low, high = wilson(7, 10)
    assert (round(low, 2), round(high, 2)) == (0.4, 0.89)
    assert wilson(0, 10)[0] == 0 and round(wilson(0, 10)[1], 2) == 0.28
    assert round(wilson(10, 10)[0], 2) == 0.72 and wilson(10, 10)[1] == 1
    assert wilson(0, 0) == (0.0, 1.0)


def a_result(
    result_id: str, rates: dict[str, tuple[int, int]], repeats: int = 10, model: str = "local/qwen"
) -> dict[str, Any]:
    checks = [
        {
            "name": n,
            "kind": "fixture",
            "passes": p,
            "attempts": a,
            "interval": list(wilson(p, a)),
            "failures": [],
        }
        for n, (p, a) in rates.items()
    ]
    return {
        "result_id": result_id,
        "kind": "checks",
        "created_at": 1.0,
        "model": model,
        "settings": {},
        "repeats": repeats,
        "data": {"checks": checks},
    }


def test_compare_marks_only_changes_beyond_chance() -> None:
    before = a_result("a", {"x": (2, 20), "y": (12, 20), "z": (19, 20)})
    after = a_result("b", {"x": (17, 20), "y": (14, 20), "z": (5, 20)})
    lines, notes = compare(before, after)
    assert [(line["name"], line["verdict"]) for line in lines] == [
        ("x", "better"),
        ("y", "no clear change"),
        ("z", "worse"),
    ]
    assert notes == []
    _, notes = compare(before, a_result("c", {"x": (1, 5)}, repeats=5, model="openai/gpt"))
    assert notes == ["the models differ: local/qwen and openai/gpt", "the repeats differ: 10 and 5"]


def test_results_are_kept(tmp_path: Path) -> None:
    results = Results(tmp_path / "evals.db")
    first = a_result("r1", {"x": (3, 10)})
    results.save(first)
    results.save(a_result("r2", {"x": (4, 10)}) | {"created_at": 2.0})
    assert results.load("r1") == first
    assert [r["result_id"] for r in results.list("checks")] == ["r2", "r1"]
    assert results.load("nope") is None


def test_the_tables() -> None:
    result = a_result("r1", {"load-at-site": (7, 10)})
    result["data"]["checks"][0]["failures"] = [
        {"run_id": "abc", "answer": "{}", "why": "answered wait: nobody"}
    ]
    table = checks_table(result)
    assert "load-at-site" in table and "7/10" in table and "[40% to 89%]" in table
    assert "answered wait: nobody (run abc)" in table
    lines, notes = compare(result, a_result("r2", {"load-at-site": (10, 10)}))
    assert "load-at-site" in compare_table(lines, notes) and "7/10 → 10/10" in compare_table(
        lines, notes
    )


# --- turn checks ---

AT_THE_SITE = {
    "day": 67,
    "time": "10:00",
    "project": {"key": "trees_square"},
    "villagers": {"Lina": {"at": "site", "carrying": "saplings"}},
}


def a_check(expect: dict[str, Any], **changes: Any) -> dict[str, Any]:
    check: dict[str, Any] = {
        "name": "load-at-site",
        "agent": "villager",
        "as": "Lina",
        "situation": {"fixture": AT_THE_SITE, "prompt": "decide"},
        "expect": expect,
    }
    return check | changes


def test_a_fixture_check_builds_its_prompt_with_todays_code() -> None:
    prompt, world = prompt_of(a_check({"action": {"action": "give"}}))
    assert world is not None and prompt == observation(world, "Lina")
    assert '{"action": "give"}: set down your load of saplings at the building site' in prompt
    frozen = a_check(
        {"valid": True},
        agent="meeting",
        situation={"frozen": "PROMPT AS RECORDED", "prompt": "propose"},
    )
    assert prompt_of(frozen) == ("PROMPT AS RECORDED", None)


@pytest.mark.parametrize(
    ("expect", "answer", "passed", "why"),
    [
        ({"action": {"action": "give", "to": None}}, '{"action": "give"}', True, None),
        (
            {"action": {"action": "give"}},
            '{"action": "give", "to": "Hilde"}',
            False,
            "answered wait: Hilde is asleep",
        ),
        (
            {"action": {"action": "move", "place": "site"}},
            '{"action": "move", "place": "market"}',
            False,
            "place was 'market', not 'site'",
        ),
        (
            {"action": {"action": "give"}},
            "not json",
            False,
            "answered wait: the answer is not JSON",
        ),
        ({"not": [{"action": "give", "to": "Hilde"}]}, '{"action": "give"}', True, None),
        (
            {"not": [{"action": "give"}]},
            '{"action": "give"}',
            False,
            "an answer that is not wanted: {'action': 'give'}",
        ),
    ],
)
def test_judging_a_villagers_answer(
    expect: dict[str, Any], answer: str, passed: bool, why: str | None
) -> None:
    check = a_check(expect)
    _, world = prompt_of(check)
    verdict, reason = judge(check, answer, world)
    assert verdict is passed
    if why:
        assert reason is not None and reason.startswith(why)


def test_judging_planner_and_meeting_answers() -> None:
    plan = a_check(
        {"valid": True}, agent="planner", situation={"fixture": AT_THE_SITE, "prompt": "plan"}
    )
    good_plan = (
        '{"plan": [{"time": "08:00", "place": "market", "purpose": "a"}, '
        '{"time": "12:00", "place": "pier", "purpose": "b"}]}'
    )
    assert judge(plan, good_plan, prompt_of(plan)[1]) == (True, None)
    assert judge(plan, '{"plan": []}', prompt_of(plan)[1])[0] is False
    tasks = a_check(
        {"tasks_include": {"task": "buy", "goods": "saplings"}},
        agent="meeting",
        situation={"fixture": AT_THE_SITE, "prompt": "work_plan"},
    )
    _, world = prompt_of(tasks)
    buys = '{"tasks": [{"task": "buy", "goods": "saplings", "villagers": ["Lina"]}]}'
    builds = '{"tasks": [{"task": "build", "villagers": ["Lina"]}]}'
    assert judge(tasks, buys, world) == (True, None)
    assert judge(tasks, builds, world) == (False, "no such task in the work plan")
    frozen = a_check(
        {"valid": True}, agent="meeting", situation={"frozen": "x", "prompt": "propose"}
    )
    proposals = '{"proposals": [{"project": "A market stand", "reason": "r"}]}'
    assert judge(frozen, proposals, None) == (True, None)
    broken = proposals[:-1]
    verdict, why = judge(frozen, broken, None)
    assert verdict is False and why == "not valid: the answer is not JSON"


def owner_db(tmp_path: Path) -> Path:
    """An owner's database with its village and agents, as `make dev` leaves it."""
    path = tmp_path / "owner.db"
    village = Village(store=Store(path), models=fake_models(FakeLLM([])), bus=Bus())
    village.ensure_agents()
    return path


@pytest.mark.anyio
async def test_running_checks_counts_and_keeps_the_owner_untouched(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    before = owner.read_bytes()
    answers = iter(
        ['{"action": "give"}', '{"action": "give", "to": "Hilde"}', '{"action": "give"}']
    )
    llm = FakeLLM([lambda _: answer(next(answers))] * 3)
    check = a_check({"action": {"action": "give", "to": None}})
    result = await run_checks([check], fake_models(llm), owner, tmp_path / "evals.db", repeats=3)
    [row] = result["data"]["checks"]
    assert (row["name"], row["kind"], row["passes"], row["attempts"]) == (
        "load-at-site",
        "fixture",
        2,
        3,
    )
    assert row["failures"][0]["why"] == "answered wait: Hilde is asleep"
    assert owner.read_bytes() == before  # only read
    evals = Store(tmp_path / "evals.db")
    run = evals.get_run(row["failures"][0]["run_id"])
    assert run is not None and run.eval_id == result["result_id"] and run.villager == "Lina"
    assert evals.list_turns("Lina") == []  # check runs stay out of the turns
    assert Results(tmp_path / "evals.db").load(result["result_id"]) is not None
    assert result["data"]["overall"]["passes"] == 2


@pytest.mark.anyio
async def test_a_failed_run_is_a_failed_attempt(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    llm = FakeLLM([RuntimeError("model down")])
    check = a_check({"action": {"action": "give"}})
    result = await run_checks([check], fake_models(llm), owner, tmp_path / "evals.db", repeats=1)
    assert result["data"]["checks"][0]["failures"][0]["why"] == "the run failed"


def test_a_check_from_a_recorded_turn(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    store = Store(owner)
    world = store.load_village()
    assert world is not None
    lina = next(v["agent_id"] for v in world["villagers"] if v["name"] == "Lina")
    store.create_run(
        Run(
            run_id="t1",
            agent_id=lina,
            config_version="v",
            prompt="WHAT LINA SAW",
            status="completed",
            graph=build_graph([]),
            config={},
            started_at=1.0,
            village_tick=40,
            villager="Lina",
        )
    )
    store.set_village_action("t1", {"action": "wait", "reason": "Hilde's hands are full"})
    path = add_check(
        owner, "t1", "not-to-hilde", {"not": [{"action": "give", "to": "Hilde"}]}, tmp_path
    )
    [check] = load_checks(tmp_path)
    assert path.name == "not-to-hilde.json"
    assert check["agent"] == "villager" and check["as"] == "Lina"
    assert check["situation"] == {"frozen": "WHAT LINA SAW", "from_run": "t1", "prompt": "decide"}
    assert prompt_of(check) == ("WHAT LINA SAW", None)


def test_bad_check_files_are_named(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text('{"name": "x", "agent": "cat", "situation": {}}')
    with pytest.raises(ValueError, match=r"broken\.json: bad agent"):
        load_checks(tmp_path)


# --- the command line ---


def test_the_command_line_parses_every_command() -> None:
    args = parser().parse_args(["checks", "--repeats", "20", "--only", "a", "b"])
    assert (args.command, args.repeats, args.only, args.db) == (
        "checks",
        20,
        ["a", "b"],
        "data/agent_lab.db",
    )
    assert parser().parse_args(["scenarios"]).repeats == 5
    add = parser().parse_args(["add-check", "--run", "r1", "--name", "n", "--expect", "{}"])
    assert (add.run, add.name, add.expect) == ("r1", "n", "{}")
    assert parser().parse_args(["compare", "a", "b"]).results == ["a", "b"]
    assert parser().parse_args(["results", "--kind", "checks"]).kind == "checks"
    assert parser().parse_args(["health", "--days", "3"]).days == 3


def test_health_on_the_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    owner = owner_db(tmp_path)
    store = Store(owner)
    world = store.load_village()
    assert world is not None
    store.create_run(
        Run(
            run_id="t1",
            agent_id="a",
            config_version="v",
            prompt="p",
            status="completed",
            graph=build_graph([]),
            config={},
            started_at=world["born"] + 1,
            village_tick=0,
            villager="Lina",
        )
    )
    store.set_village_action("t1", {"action": "wait", "reason": "Hilde is not next to you"})
    assert main(["health", "--db", str(owner)]) == 0
    out = capsys.readouterr().out
    assert "Day 1 (so far)" in out and "Waits 100%" in out
    assert "1x <villager> is not next to you" in out


def test_results_and_compare_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = Results(tmp_path / "evals.db")
    results.save(a_result("r1", {"x": (2, 20)}))
    results.save(a_result("r2", {"x": (18, 20)}) | {"created_at": 2.0})
    evals = str(tmp_path / "evals.db")
    assert main(["results", "--evals", evals]) == 0
    assert main(["compare", "r1", "r2", "--evals", evals]) == 0
    out = capsys.readouterr().out
    assert "r2" in out and "x" in out and "better" in out
    assert main(["compare", "r1", "nope", "--evals", evals]) == 1


SHIPPED_CHECKS = Path(__file__).parent.parent / "evals" / "checks"
IDEAL = {  # an answer each shipped check must accept: the checks can be passed
    "take-the-boat": '{"action": "row", "with": null}',
    "animal-lead": '{"action": "lead"}',
    "repair-mend": '{"action": "work"}',
    "peddler-curiosity": '{"action": "buy", "goods": "lantern"}',
    "letter-pass-on": '{"action": "say", "text": "Roses sell for double in town!"}',
    "visitor-host": '{"action": "move", "place": "home"}',
    "load-at-site-m14": '{"action": "bring"}',
    "load-away-m14": '{"action": "bring"}',
    "summer-plan-without-festival": A_PLAN_ANSWER,
    "intention-keeps-building": '{"action": "say", "to": "Lina", "text": "Help me plant!"}',
    "say-to-someone-in-sight": '{"action": "say", "to": "Greta", "text": "Any vegetables?"}',
    "leave-talk-for-intention": '{"action": "work", "place": "flower garden", "until": "13:00"}',
    "load-at-site": '{"action": "give"}',
    "load-away": '{"action": "move", "place": "building site"}',
    "meeting-call-talking": '{"action": "goodbye", "place": "town hall"}',
    "meeting-call-far": '{"action": "move", "place": "town hall"}',
    "answer-when-spoken-to": '{"action": "say", "text": "A good catch!", "to": "Greta"}',
    "buy-saplings": '{"action": "buy", "goods": "saplings"}',
    "build-with-loads": '{"action": "work"}',
    "stalls-in-autumn": '{"action": "give"}',
    "find-the-one-to-see": '{"action": "find", "villager": "Greta"}',
    "not-to-hilde": '{"action": "move", "place": "building site"}',
    "work-at-own-place": '{"action": "work"}',
    "plan-valid": '{"plan": [{"time": "06:00", "place": "pier", "purpose": "Fish"}, '
    '{"time": "17:00", "place": "town hall", "purpose": "The meeting"}]}',
    "work-plan-buys": '{"tasks": [{"task": "buy", "goods": "saplings", "villagers": ["Lina"]}]}',
    "proposals-valid": '{"proposals": [{"project": "A market stand", "reason": "r"}]}',
}


def test_the_shipped_checks_load_and_can_be_passed() -> None:
    checks = load_checks(SHIPPED_CHECKS)
    assert len(checks) >= 12 and {c["name"] for c in checks} == set(IDEAL)
    for check in checks:
        prompt, world = prompt_of(check)
        assert judge(check, IDEAL[check["name"]], world) == (True, None), check["name"]
        assert prompt
    by_name = {c["name"]: prompt_of(c)[0] for c in checks}
    assert "set down your load of saplings at the building site" in by_name["load-at-site"]
    assert '{"action": "bring"}: the building site still needs' in by_name["load-away"]
    assert "The town hall meeting starts at 17:00" in by_name["meeting-call-talking"]
    assert (
        "You are set on: build at the building site until 15:00 (to plant the trees)."
        in by_name["intention-keeps-building"]
    )
    assert "In sight: Greta (3 steps away)." in by_name["say-to-someone-in-sight"]
    assert "Happening: Greta's goat wandered to the market." in by_name["animal-lead"]
    assert '{"action": "lead"}' in by_name["animal-lead"]
    assert "mend the boards of the pier" in by_name["repair-mend"]
    assert '"goods": "a lantern"' in by_name["peddler-curiosity"]
    assert "roses sell for twice the price" in by_name["letter-pass-on"]
    assert "Anna, your sister, is visiting you." in by_name["visitor-host"]
    assert "The boat lies at the pier." in by_name["take-the-boat"]
    assert '{"action": "row"}: take the boat out on the lake' in by_name["take-the-boat"]
    assert "You are talking with Jonas (4 lines so far)." in by_name["leave-talk-for-intention"]
    assert "festival" not in by_name["summer-plan-without-festival"].lower()  # out of season
    assert "A trader is at the market until 14:00" in by_name["buy-saplings"]
    assert "Hand out the work" in by_name["work-plan-buys"]
    frozen = next(c for c in checks if c["name"] == "proposals-valid")
    assert "frozen" in frozen["situation"] and frozen["situation"]["from_run"]


# --- scenarios ---

MEETING_START = {
    "day": 66,
    "time": "16:50",
    "meeting": {"kind": "vote", "proposals": [{"key": "market_stand", "reason": "r"}]},
    "villagers": {
        "Hilde": {"at": "town_hall"},
        "Greta": {"at": [3, 3]},
        "Lina": {"at": [4, 3]},
        "Jonas": {"at": "pier"},
    },
}


def a_scenario(condition: dict[str, Any], **changes: Any) -> dict[str, Any]:
    scenario: dict[str, Any] = {
        "name": "meeting-attendance",
        "start": MEETING_START,
        "horizon": {"until": "17:50"},
        "condition": condition,
    }
    return scenario | changes


def fake_village_models() -> Models:
    """The test responder: villagers wait, meetings take the defaults."""
    return fake_models(FakeLLM([responder({})] * 400))


@pytest.mark.anyio
async def test_a_scenario_runs_on_fresh_copies_and_leaves_the_owner_alone(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    before = owner.read_bytes()
    scenario = a_scenario({"kind": "meeting_attendance", "at_least": 3})
    result = await run_scenarios(
        [scenario],
        fake_village_models(),
        owner,
        tmp_path / "copies",
        tmp_path / "evals.db",
        repeats=2,
    )
    assert owner.read_bytes() == before
    [s] = result["data"]["scenarios"]
    assert (s["name"], s["attempts"], s["finished"], s["held"]) == ("meeting-attendance", 2, 2, 2)
    run = s["runs"][0]
    assert run["held"] is True and run["why"] == "3 came: Hilde, Greta, Lina"
    assert Path(run["db"]).exists() and Path(run["db"]).parent == tmp_path / "copies"
    copy = Store(run["db"]).load_village()
    assert copy is not None and clock(copy["tick"])[:2] == (66, "17:50")  # stopped at the horizon
    assert run["health"] and run["health"][0]["day"] == 66
    assert Results(tmp_path / "evals.db").load(result["result_id"]) is not None


@pytest.mark.anyio
async def test_a_scenario_whose_village_gives_up_is_unfinished(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    down = fake_models(FakeLLM([RuntimeError("model down")] * 400))
    scenario = a_scenario(
        {"kind": "meeting_attendance", "at_least": 3},
        start=MEETING_START | {"time": "10:00"},
        horizon={"hours": 2},
    )
    for v in scenario["start"]["villagers"].values():
        v["at"] = "market"
    result = await run_scenarios(
        [scenario], down, owner, tmp_path / "copies", tmp_path / "evals.db", repeats=1
    )
    [s] = result["data"]["scenarios"]
    assert (s["finished"], s["held"]) == (0, 0) and s["runs"][0]["finished"] is False


def test_the_conditions() -> None:
    world = build_world(MEETING_START)
    world["meeting"]["present"] = ["Hilde", "Greta"]
    store = Store(":memory:")
    held, why = CONDITIONS["meeting_attendance"](store, world, 0, {"at_least": 3})
    assert (held, why) == (False, "2 came: Hilde, Greta")
    world["built"] = [{"key": "boat", "day": 66}]
    assert CONDITIONS["built"](store, world, 0, {"key": "boat", "by_day": 66})[0] is True
    assert CONDITIONS["built"](store, world, 0, {"key": "barn", "by_day": 66}) == (
        False,
        "barn was not built by day 66",
    )


def test_talk_then_go_reads_the_notes_and_the_trail() -> None:
    world = build_world(MEETING_START | {"time": "10:00"})
    store = Store(":memory:")
    talk: dict[str, Any] = {
        "tick": world["tick"] + 2,
        "text": "Jonas and Greta talked; what they said (their claims): a / b / c",
    }
    world["day_record"]["items"].append(talk)
    params = {"pair": ["Greta", "Jonas"], "max_lines": 6, "within_hours": 1}
    assert CONDITIONS["talk_then_go"](store, world, world["tick"], params) == (
        False,
        "after their talk of 3 lines, Greta did not move on within 1 hour",
    )
    for i, (greta, jonas) in enumerate([("idle", "walking"), ("working", "idle")]):
        store.add_trail(
            talk["tick"] + 1 + i,
            {"v": [["Greta", 0, 0, None, greta, None], ["Jonas", 0, 0, None, jonas, None]]},
        )
    assert CONDITIONS["talk_then_go"](store, world, world["tick"], params) == (
        True,
        "they talked 3 lines and both moved on",
    )
    world["day_record"]["items"][-1]["text"] = talk["text"] + " / d / e / f / g"
    assert CONDITIONS["talk_then_go"](store, world, world["tick"], params) == (
        False,
        "they talked 7 lines, more than 6",
    )


def test_load_at_site_reads_the_deliveries(tmp_path: Path) -> None:
    store = Store(tmp_path / "copy.db")
    world = build_world(MEETING_START | {"time": "10:00"})
    store.create_run(
        Run(
            run_id="g",
            agent_id="a",
            config_version="v",
            prompt="p",
            status="completed",
            graph=build_graph([]),
            config={},
            started_at=world["born"] + 1,
            village_tick=world["tick"] + 8,
            villager="Lina",
        )
    )
    store.set_village_action("g", {"action": "give", "to": None, "goods": "saplings"})
    held, why = CONDITIONS["load_at_site"](
        store, world, world["tick"], {"goods": "saplings", "by": "12:00"}
    )
    assert (held, why) == (True, "Lina set down saplings at 11:20")
    late = CONDITIONS["load_at_site"](
        store, world, world["tick"], {"goods": "saplings", "by": "11:00"}
    )
    assert late == (False, "no saplings set down at the site by 11:00")


def test_load_at_site_reads_a_set_down_by_an_intention(tmp_path: Path) -> None:
    """M14: a bring sets the load down on arrival, without a give answer: the note says so."""
    store = Store(tmp_path / "copy.db")
    world = build_world(MEETING_START | {"time": "10:00"})
    world["day_record"]["items"].append(
        {
            "tick": world["tick"] + 5,
            "text": "Lina set down a load of saplings at the building site.",
        }
    )
    params = {"goods": "saplings", "by": "12:00"}
    assert CONDITIONS["load_at_site"](store, world, world["tick"], params) == (
        True,
        "Lina set down saplings at 10:50",
    )
    params["by"] = "10:40"
    assert CONDITIONS["load_at_site"](store, world, world["tick"], params)[0] is False


def test_a_fixture_can_give_a_reason_to_decide() -> None:
    world = build_world(
        {"day": 67, "time": "10:00", "villagers": {"Jonas": {"at": [10, 5], "triggers": ["met"]}}}
    )
    assert villager(world, "Jonas")["triggers"] == ["met"]


def test_the_shipped_scenarios_load_and_start() -> None:
    from agent_lab.village.evals.scenarios import load_scenarios

    scenarios = load_scenarios(Path(__file__).parent.parent / "evals" / "scenarios")
    assert {s["name"] for s in scenarios} == {
        "meeting-attendance",
        "load-reaches-site",
        "talk-then-go",
        "boat-trip",
    }
    for s in scenarios:
        assert build_world(s["start"])["day_record"] is not None  # notes kept from the start


@pytest.mark.anyio
async def test_a_scenario_copy_holds_every_village_agent(tmp_path: Path) -> None:
    owner = owner_db(tmp_path)
    world, ids = read_owner(owner)
    shared = ("reflection_agent_id", "chronicler_agent_id", "planner_agent_id", "meeting_agent_id")
    assert all(world[k] in ids for k in shared)
    scenario = a_scenario({"kind": "meeting_attendance", "at_least": 1}, horizon={"hours": 1})
    result = await run_scenarios(
        [scenario],
        fake_village_models(),
        owner,
        tmp_path / "copies",
        tmp_path / "evals.db",
        repeats=1,
    )
    copy = Store(result["data"]["scenarios"][0]["runs"][0]["db"])
    assert {a.agent_id for a in copy.list_agents()} == set(ids)
    models = result["settings"]["models"]
    assert set(models) == {a.name for a in copy.list_agents()}
    assert all(m.startswith("local/") for m in models.values())


def test_compare_names_agents_on_other_models() -> None:
    before = a_result("a", {"x": (5, 10)}) | {"settings": {"models": {"Jonas": "local/qwen"}}}
    after = a_result("b", {"x": (5, 10)}) | {"settings": {"models": {"Jonas": "openai/gpt"}}}
    _, notes = compare(before, after)
    assert notes == ["Jonas ran on local/qwen, then on openai/gpt"]


def test_boat_trip_reads_the_notes(tmp_path: Path) -> None:
    """M15 (FR-013): a trip by the time given, alone or together."""
    store = Store(tmp_path / "copy.db")
    world = build_world(MEETING_START | {"time": "14:00"})
    params = {"by": "16:00"}
    assert CONDITIONS["boat_trip"](store, world, world["tick"], params) == (
        False,
        "nobody took the boat out by 16:00",
    )
    world["day_record"]["items"].append(
        {"tick": world["tick"] + 2, "text": "Jonas and Greta rowed out on the lake."}
    )
    assert CONDITIONS["boat_trip"](store, world, world["tick"], params) == (
        True,
        "Jonas and Greta rowed out at 14:20, together",
    )
    world["day_record"]["items"][-1]["text"] = "Jonas rowed out on the lake."
    assert CONDITIONS["boat_trip"](store, world, world["tick"], params) == (
        True,
        "Jonas rowed out at 14:20, alone",
    )
