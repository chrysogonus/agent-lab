"""Steps, sleep, staggered moves, decisions on triggers, meetings, conversations, searching,
beliefs, storage and controls (US1 to US4)."""

import asyncio
import json
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from helpers import answer, fake_models

from agent_lab.bus import Bus
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store
from agent_lab.village import runner
from agent_lab.village.build import new_project
from agent_lab.village.intention import start
from agent_lab.village.memory import remember
from agent_lab.village.plan import plan_prompt
from agent_lab.village.runner import CELLS_PER_STEP, CHANNEL, FRESH_START, StepConflict, Village
from agent_lab.village.seasons import weather
from agent_lab.village.turn import SPEECH_SHOWN, observation, parse_action, villager_agent
from agent_lab.village.world import (
    PLACES,
    VILLAGERS,
    awake_at,
    door,
    label_cell,
    minute_of_day,
    place_at,
    place_cells,
    steps_to,
    walkable,
)

WAIT = '{"action": "wait"}'
NOTHING_LEARNED = '{"learnings": [], "views": {}}'
QUIET_DAY = '{"title": "A quiet day", "text": "Nothing much happened."}'
A_PLAN = json.dumps(
    {
        "plan": [
            {"time": "08:00", "place": "market", "purpose": "See who is about"},
            {"time": "17:00", "place": "home", "purpose": "Rest"},
        ]
    }
)
MORNING = 30  # tick of 09:30: everyone is awake
PROPOSE = json.dumps(
    {
        "proposals": [
            {"project": "Paint the town hall", "reason": "It looks shabby."},
            {"project": "A market stand", "reason": "Greta needs a place to sell."},
        ]
    }
)
DECIDE = json.dumps({"decision": "Paint the town hall", "reason": "It is quick."})
ASSIGN = json.dumps({"tasks": [{"task": "build", "villagers": ["Greta"]}]})


def move(place: str) -> str:
    return json.dumps({"action": "move", "place": place})


def say(text: str, to: str | None = None) -> str:
    return json.dumps({"action": "say", "text": text, "to": to})


def find(name: str) -> str:
    return json.dumps({"action": "find", "villager": name})


def is_reflection(messages: list[Message]) -> bool:
    return '"learnings"' in (messages[0]["content"] or "")


def is_chronicle(messages: list[Message]) -> bool:
    return "the chronicle of a small village" in (messages[0]["content"] or "")


def is_plan(messages: list[Message]) -> bool:
    return "plan its day" in (messages[0]["content"] or "")


def is_meeting(messages: list[Message]) -> bool:
    return "their town hall meeting" in (messages[0]["content"] or "")


def meeting_kind(messages: list[Message]) -> str:
    """proposals, vote, decision or tasks: the JSON shape the prompt ends by asking for."""
    last = (messages[1]["content"] or "").splitlines()[-1]
    return next(k for k in ("proposals", "vote", "decision", "tasks") if f'{{"{k}"' in last)


def vote_for(project: str, reason: str = "I like it.") -> str:
    return json.dumps({"vote": project, "reason": reason})


def speaker(messages: list[Message]) -> str:
    """The villager a call is for: its persona opens the system prompt of a decision and the
    prompt of a reflection, a plan or a meeting run."""
    own_prompt = is_reflection(messages) or is_plan(messages) or is_meeting(messages)
    text = messages[1 if own_prompt else 0]["content"] or ""
    return next(n for n in VILLAGERS if f"You are {n}," in text)


def responder(
    plan: dict[str, list[str | Exception]],
) -> Callable[[list[Message]], ChatResponse | Exception]:
    """Answers each villager from its own list (then waits), whatever order decisions run in;
    reflections come from the list "<name>:reflect" (then an empty reflection), plans from
    "<name>:plan" (then A_PLAN), chronicles from "chronicle" (then a quiet day); meeting runs
    from "meeting:proposals", "<name>:vote", "meeting:decision" and "meeting:tasks" (then
    PROPOSE, a vote for the town hall, DECIDE and ASSIGN)."""
    queues = {n: list(a) for n, a in plan.items()}

    def respond(messages: list[Message]) -> ChatResponse | Exception:
        if is_chronicle(messages):
            queue = queues.get("chronicle") or []
            item = queue.pop(0) if queue else QUIET_DAY
            return item if isinstance(item, Exception) else answer(item)
        if is_meeting(messages):
            kind = meeting_kind(messages)
            defaults = {
                "proposals": PROPOSE,
                "vote": vote_for("Paint the town hall"),
                "decision": DECIDE,
                "tasks": ASSIGN,
            }
            who = speaker(messages) if kind == "vote" else "meeting"
            key, default = f"{who}:{kind}", defaults[kind]
        elif is_plan(messages):
            key, default = f"{speaker(messages)}:plan", A_PLAN
        elif is_reflection(messages):
            key, default = f"{speaker(messages)}:reflect", NOTHING_LEARNED
        else:
            key, default = speaker(messages), WAIT
        queue = queues.get(key) or []
        item = queue.pop(0) if queue else default
        return item if isinstance(item, Exception) else answer(item)

    return respond


def village_for(
    db: Path | str,
    plan: dict[str, list[str | Exception]] | None = None,
    calls: int = 400,
    delay: float = 0,
    respond: Callable[[list[Message]], ChatResponse | Exception] | None = None,
    **kw: Any,
) -> tuple[Village, FakeLLM]:
    script: list[ScriptItem] = [respond or responder(plan or {})] * calls
    llm = FakeLLM(script, delay=delay)
    store = Store(db if db == ":memory:" else Path(db) / "lab.db")
    kw.setdefault("move_gap", 0)
    village = Village(store=store, models=fake_models(llm), bus=Bus(), **kw)
    village.ensure_agents()
    return village, llm


def villager(v: Village, name: str) -> dict[str, Any]:
    return next(x for x in v.world["villagers"] if x["name"] == name)


def morning(v: Village, tick: int = MORNING) -> None:
    """Everyone awake at its door, nothing to decide yet."""
    v.world["tick"] = tick
    for x in v.world["villagers"]:
        x |= {"asleep": False, "last_decided": tick, "triggers": []}


def put(v: Village, name: str, x: int, y: int, **changes: Any) -> dict[str, Any]:
    found = villager(v, name)
    found |= {"x": x, "y": y, **changes}
    return found


def calls_of(llm: FakeLLM, name: str) -> list[str]:
    """The prompts of a villager's decisions."""
    return [
        c[1]["content"] or ""
        for c in llm.calls
        if not (is_chronicle(c) or is_reflection(c) or is_plan(c) or is_meeting(c))
        and speaker(c) == name
    ]


def reflections_of(llm: FakeLLM, name: str) -> list[str]:
    return [c[1]["content"] or "" for c in llm.calls if is_reflection(c) and speaker(c) == name]


def plans_of(llm: FakeLLM, name: str) -> list[str]:
    return [c[1]["content"] or "" for c in llm.calls if is_plan(c) and speaker(c) == name]


def chronicles_of(llm: FakeLLM) -> list[str]:
    return [c[1]["content"] or "" for c in llm.calls if is_chronicle(c)]


def drain(queue: "asyncio.Queue[dict[str, Any]]") -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def kinds(v: Village, name: str) -> list[str]:
    return [e["kind"] for e in villager(v, name)["events"]]


# --- US1: a day and a night ---


@pytest.mark.anyio
async def test_a_scripted_day() -> None:
    plan: dict[str, list[str | Exception]] = {n: [move(c.work)] for n, c in VILLAGERS.items()}
    v, _ = village_for(":memory:", plan, calls=600)
    woke: dict[str, int] = {}
    left: dict[str, int] = {}
    slept: dict[str, int] = {}
    while v.world["tick"] < 150:  # 04:30 on day 1 to 05:30 on day 2
        await v.step()
        tick = v.world["tick"]
        for x in v.world["villagers"]:
            name = x["name"]
            if not x["asleep"]:
                woke.setdefault(name, tick)
                if (x["x"], x["y"]) != door(name):
                    left.setdefault(name, tick)
            elif name in woke:
                slept.setdefault(name, tick)
    for name, c in VILLAGERS.items():
        wake_tick = (c.wake - 270) // 10
        assert woke[name] == wake_tick, name
        assert left[name] <= wake_tick + 1, name  # decides on waking, walks the next step
        walk_home = steps_to(*label_cell(c.work), [door(name)])
        assert (c.bed - 270) // 10 <= slept[name] <= (c.bed - 270) // 10 + walk_home + 1, name
    jonas = villager(v, "Jonas")
    assert not jonas["asleep"] and v.world["tick"] == 150  # he is up again at 05:00 on day 2
    for name in VILLAGERS:  # never a decision while asleep
        for turn in v.store.list_turns(name):
            assert turn.village_tick is not None
            assert awake_at(name, minute_of_day(turn.village_tick)), (name, turn.village_tick)


@pytest.mark.anyio
async def test_bedtime_walks_home_without_decisions_and_ends_conversations(
    tmp_path: Path,
) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick=(21 * 60 - 270) // 10 - 1)  # 20:50: Jonas goes to bed at 21:00
    mx, my = label_cell("market")
    put(v, "Jonas", mx, my)
    put(v, "Greta", mx + 1, my)
    tick = v.world["tick"]
    v.world["conversations"] = [{"a": "Jonas", "b": "Greta", "lines": 2, "last_tick": tick}]
    await v.step()
    jonas = villager(v, "Jonas")
    assert jonas["bedtime"] and jonas["goal"] == {"kind": "home"}
    assert v.world["conversations"] == []
    assert any("Jonas went home to bed" in e["text"] for e in villager(v, "Greta")["events"])
    for _ in range(steps_to(mx, my, [door("Jonas")])):
        await v.step()
    assert jonas["asleep"] and (jonas["x"], jonas["y"]) == door("Jonas")
    assert kinds(v, "Jonas")[-2:] == ["slept", "reflected"]  # he talked today, so he reflects
    assert calls_of(llm, "Jonas") == [] and len(reflections_of(llm, "Jonas")) == 1


@pytest.mark.anyio
async def test_the_night_passes_without_waiting_the_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert runner.NIGHT_STEP * 40 < 15  # a whole night in under 15 s (SC-004)
    monkeypatch.setattr(runner, "NIGHT_STEP", 0.001)
    v, _ = village_for(tmp_path)
    v.world["tick"] = (23 * 60 + 30 - 270) // 10  # 23:30, everyone asleep
    v.viewer_joined()
    v.start()  # interval 5 s
    for _ in range(200):
        await asyncio.sleep(0.01)
        if not villager(v, "Jonas")["asleep"]:
            break
    v.pause()
    assert not villager(v, "Jonas")["asleep"]  # 05:00 on day 2, within about 2 s
    assert v.state()["time"] in ("05:00", "05:10")


@pytest.mark.anyio
async def test_reload_is_paused_and_reset_starts_over(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [move("market")]})
    morning(v)
    villager(v, "Greta")["triggers"] = ["woke"]
    await v.step()
    await v.step()
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert reloaded.world["tick"] == MORNING + 2 and reloaded.world["running"] is False
    assert reloaded.world["villagers"] == v.world["villagers"]
    await reloaded.reset()
    greta = villager(reloaded, "Greta")
    assert reloaded.world["tick"] == 0 and greta["asleep"]
    assert (greta["x"], greta["y"]) == door("Greta")
    assert greta["agent_id"] == villager(v, "Greta")["agent_id"]


@pytest.mark.anyio
async def test_an_m6_world_starts_fresh_with_its_agents_updated(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="blocks",
        name="Mayor Hilde",
        description="old",
        sample_prompt="x",
        config={"model": {"provider": "local", "model": "m"}, "blocks": []},
    )
    store.save_village(
        {"tick": 40, "villagers": [{"name": "Hilde", "agent_id": agent.agent_id, "x": 1, "y": 1}]}
    )
    v = Village(store=store, models=fake_models(FakeLLM([])), bus=Bus())
    assert v.world["version"] == 8 and v.world["tick"] == 0
    assert v.world["paused_reason"] == FRESH_START
    assert villager(v, "Hilde")["agent_id"] == agent.agent_id
    updated = store.get_agent(agent.agent_id)
    assert updated is not None
    assert updated.config["blocks"] == villager_agent("Hilde")["config"]["blocks"]
    assert updated.config["model"] == {"provider": "local", "model": "m"}  # kept
    assert store.load_village() == v.world


# --- US2: their own pace ---


@pytest.mark.anyio
async def test_walking_costs_no_model_call(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v)
    greta = villager(v, "Greta")
    greta["goal"] = {"kind": "place", "place": "square"}
    distance = steps_to(greta["x"], greta["y"], place_cells("square"))
    steps = -(-distance // CELLS_PER_STEP)  # three cells a step
    for _ in range(steps - 1):
        await v.step()
        assert calls_of(llm, "Greta") == []
    await v.step()
    assert place_at(greta["x"], greta["y"]) == "square" and greta["goal"] is None
    assert len(calls_of(llm, "Greta")) == 1  # it decides on arriving
    assert "You arrived at the square." in calls_of(llm, "Greta")[0]


@pytest.mark.anyio
async def test_an_idle_villager_decides_again_after_three_steps(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v)
    for _ in range(6):
        await v.step()
    assert len(calls_of(llm, "Lina")) == 2  # at +3 and +6


@pytest.mark.anyio
async def test_moves_are_staggered_within_a_step(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    for name, place in (("Hilde", "square"), ("Jonas", "market"), ("Greta", "square")):
        villager(v, name)["goal"] = {"kind": "place", "place": place}
    queue = v.bus.subscribe(CHANNEL)
    first_movers: list[str] = []
    for _ in range(3):
        before = {x["name"]: (x["x"], x["y"]) for x in v.world["villagers"]}
        await v.step()
        moved_in_order: list[str] = []
        while not queue.empty():
            event = queue.get_nowait()
            if event["type"] != "state":
                continue
            now = {x["name"]: (x["x"], x["y"]) for x in event["state"]["villagers"]}
            changed = [n for n in now if now[n] != before[n]]
            assert len(changed) <= 1  # one move per published state
            for n in changed:
                bx, by = before[n]
                assert abs(now[n][0] - bx) + abs(now[n][1] - by) == 1  # one cell at a time
            moved_in_order += changed
            before = now
        assert set(moved_in_order) == {"Greta", "Hilde", "Jonas"}
        assert all(moved_in_order.count(n) <= CELLS_PER_STEP for n in moved_in_order)
        assert moved_in_order[:3] != [moved_in_order[0]] * 3  # rounds: they take turns
        first_movers.append(moved_in_order[0])
    assert len(set(first_movers)) == 1  # a fixed order keeps each walker's rhythm even


@pytest.mark.anyio
async def test_hundred_steps_stay_on_walkable_cells() -> None:
    places = list(PLACES)
    plan: dict[str, list[str | Exception]] = {
        n: [move(places[(i + k) % len(places)]) for i in range(60)] for k, n in enumerate(VILLAGERS)
    }
    v, _ = village_for(":memory:", plan, calls=600)
    morning(v)
    for x in v.world["villagers"]:
        x["triggers"] = ["woke"]
    for _ in range(100):
        before = {x["name"]: (x["x"], x["y"]) for x in v.world["villagers"]}
        await v.step()
        for x in v.world["villagers"]:
            bx, by = before[x["name"]]
            moved = abs(x["x"] - bx) + abs(x["y"] - by)
            assert walkable(x["x"], x["y"]) and moved <= CELLS_PER_STEP
    assert v.world["tick"] == MORNING + 100


@pytest.mark.anyio
async def test_a_slow_decision_only_holds_up_its_own_villager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    v, llm = village_for(tmp_path, {"Hilde": [move("market")]})
    morning(v)
    v.world["interval"] = 0.01
    hilde = villager(v, "Hilde")
    hilde["triggers"] = ["woke"]
    greta = villager(v, "Greta")
    greta["goal"] = {"kind": "place", "place": "square"}
    gate = asyncio.Event()
    turn = v._turn  # pyright: ignore[reportPrivateUsage]

    async def slow_for_hilde(
        x: dict[str, Any], prompt: str, tick: int
    ) -> tuple[str | None, dict[str, Any], str | None]:
        if x["name"] == "Hilde":
            await gate.wait()
        return await turn(x, prompt, tick)

    monkeypatch.setattr(v, "_turn", slow_for_hilde)
    v.viewer_joined()
    hilde_at = (hilde["x"], hilde["y"])
    v.start()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if place_at(greta["x"], greta["y"]) == "square":
            break
    assert place_at(greta["x"], greta["y"]) == "square"  # Greta walked all the way
    assert (hilde["x"], hilde["y"]) == hilde_at and v.state()["villagers"][0]["state"] == "deciding"
    gate.set()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if hilde["goal"]:
            break
    v.pause()
    assert hilde["goal"] == {"kind": "place", "place": "market"}
    assert len(calls_of(llm, "Greta")) >= 1


@pytest.mark.anyio
async def test_steps_never_overlap(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, delay=0.05)
    morning(v)
    villager(v, "Hilde")["triggers"] = ["woke"]
    results = await asyncio.gather(v.step(), v.step(), return_exceptions=True)
    assert sum(isinstance(r, StepConflict) for r in results) == 1
    assert v.world["tick"] == MORNING + 1


@pytest.mark.anyio
async def test_reset_discards_a_decision_in_flight(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [move("square")]}, delay=0.05)
    morning(v)
    villager(v, "Hilde")["triggers"] = ["woke"]
    step = asyncio.create_task(v.step())
    await asyncio.sleep(0.01)
    assert "Hilde" in v.decisions
    await v.reset()
    await step
    hilde = villager(v, "Hilde")
    assert v.world["tick"] == 0 and hilde["goal"] is None and hilde["asleep"]


# --- US3: meeting and talking ---


def neighbours_at_market(v: Village) -> tuple[int, int]:
    morning(v)
    mx, my = label_cell("market")
    put(v, "Hilde", mx, my)
    put(v, "Jonas", mx + 1, my, neighbours=["Hilde"])
    villager(v, "Hilde")["neighbours"] = ["Jonas"]
    return mx, my


@pytest.mark.anyio
async def test_a_line_reaches_the_addressee_only(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Hilde": [say("Fish for the festival?", "Jonas")]})
    mx, my = neighbours_at_market(v)
    put(v, "Greta", mx + 3, my)  # two cells beyond Jonas: in sight, not next to Hilde
    villager(v, "Hilde")["triggers"] = ["met"]
    await v.step()
    jonas, greta = villager(v, "Jonas"), villager(v, "Greta")
    assert jonas["inbox"] == [
        {"from": "Hilde", "to": "Jonas", "text": "Fish for the festival?", "tick": MORNING + 1}
    ]
    assert greta["inbox"] == [] and "heard" not in kinds(v, "Greta")
    assert jonas["triggers"] == ["spoken to"]  # decides on the next step (paused: not now)
    assert calls_of(llm, "Jonas") == []
    assert v.world["conversations"] == [
        {
            "a": "Hilde",
            "b": "Jonas",
            "lines": 1,
            "last_tick": MORNING + 1,
            "transcript": ["Hilde: Fish for the festival?"],
        }
    ]
    assert v.state()["log"][-1] == {
        "tick": MORNING + 1,
        "time": "09:40",
        "from": "Hilde",
        "to": "Jonas",
        "text": "Fish for the festival?",
    }
    await v.step()
    assert '- Hilde to you: "Fish for the festival?"' in calls_of(llm, "Jonas")[0]


@pytest.mark.anyio
async def test_speech_without_addressee_reaches_every_awake_neighbour(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [say("Good morning!")]})
    morning(v, tick=15)  # 07:00: Hilde sleeps until 07:30
    mx, my = label_cell("market")
    put(v, "Greta", mx, my, triggers=["met"])
    put(v, "Jonas", mx + 1, my)
    put(v, "Lina", mx - 1, my + 1)
    put(v, "Hilde", mx, my + 1, asleep=True)
    await v.step()
    for name in ("Jonas", "Lina"):
        heard = [e.get("from") for e in villager(v, name)["events"] if e["kind"] == "heard"]
        assert heard == ["Greta"], name
    assert villager(v, "Hilde")["asleep"] and "heard" not in kinds(v, "Hilde")


@pytest.mark.anyio
async def test_speech_with_nobody_next_to_you_is_waiting(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [say("Anyone?")]})
    morning(v)
    villager(v, "Hilde")["triggers"] = ["woke"]
    await v.step()
    assert villager(v, "Hilde")["last_action"] == {
        "action": "wait",
        "reason": "nobody is next to you",
    }
    [turn] = v.store.list_turns("Hilde")
    assert turn.village_action == {"action": "wait", "reason": "nobody is next to you"}


@pytest.mark.anyio
async def test_a_chance_meeting_tells_both(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v)
    mx, my = label_cell("market")
    put(v, "Jonas", mx, my)
    put(v, "Greta", mx - 3, my, goal={"kind": "place", "place": "market"})
    for _ in range(3):
        await v.step()
    assert "met" in kinds(v, "Greta") and "met" in kinds(v, "Jonas")
    assert any("Greta the farmer is next to you." in c for c in calls_of(llm, "Jonas"))


@pytest.mark.anyio
async def test_a_conversation_holds_both_and_ends_after_ten_lines(tmp_path: Path) -> None:
    lines: list[str | Exception] = [say(f"Line {i}") for i in range(6)]
    v, _ = village_for(tmp_path, {"Hilde": lines, "Jonas": lines})
    neighbours_at_market(v)
    villager(v, "Hilde")["triggers"] = ["met"]
    await v.step()  # the first line
    villager(v, "Jonas")["goal"] = {"kind": "place", "place": "pier"}  # talking keeps him here
    jonas_at = (villager(v, "Jonas")["x"], villager(v, "Jonas")["y"])
    for _ in range(8):
        await v.step()
        assert (villager(v, "Jonas")["x"], villager(v, "Jonas")["y"]) == jonas_at
    assert v.world["conversations"][0]["lines"] == 9
    await v.step()
    assert v.world["conversations"] == [] and v.world["talked_out"] == [["Hilde", "Jonas"]]
    assert any("you talked a long time" in e["text"] for e in villager(v, "Hilde")["events"])
    await v.step()  # Hilde tries an 11th line
    assert villager(v, "Hilde")["last_action"]["reason"].startswith(
        "you have talked a long time with Jonas"
    )


@pytest.mark.anyio
async def test_goodbye_and_walking_away_end_a_conversation(tmp_path: Path) -> None:
    goodbye = json.dumps({"action": "goodbye", "text": "See you!"})
    v, _ = village_for(tmp_path, {"Hilde": [say("Hi"), goodbye], "Jonas": [say("Hello")]})
    neighbours_at_market(v)
    villager(v, "Hilde")["triggers"] = ["met"]
    for _ in range(3):
        await v.step()
    assert v.world["conversations"] == []
    assert any("Hilde said goodbye" in e["text"] for e in villager(v, "Jonas")["events"])
    assert v.world["log"][-1]["text"] == "See you!"

    leave = json.dumps({"action": "goodbye", "text": "Off to the pier!", "place": "pier"})
    v2, _ = village_for(":memory:", {"Hilde": [say("Hi")], "Jonas": [move("pier"), leave]})
    neighbours_at_market(v2)
    villager(v2, "Hilde")["triggers"] = ["met"]
    jonas = villager(v2, "Jonas")
    jonas_at = (jonas["x"], jonas["y"])
    await v2.step()  # Hilde says hi
    assert (jonas["x"], jonas["y"]) == jonas_at and len(v2.world["conversations"]) == 1
    await v2.step()  # Jonas walks off: M14 turns it into a goodbye and leaving
    assert jonas["last_action"]["action"] == "goodbye"
    assert v2.world["conversations"] == []
    assert any("Jonas said goodbye" in e["text"] for e in villager(v2, "Hilde")["events"])
    assert jonas["goal"] == {"kind": "place", "place": "pier"}
    # Leaving is no reason for Jonas to decide again; Hilde, left behind, will.
    assert "conversation ended" not in jonas["triggers"]
    assert "conversation ended" in villager(v2, "Hilde")["triggers"]


@pytest.mark.anyio
async def test_finding_someone_where_they_were_heard_of(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Hilde": [find("Lina")]})
    morning(v)
    lx, ly = label_cell("square")
    put(v, "Lina", lx + 4, ly + 3)
    hilde = villager(v, "Hilde")
    hilde["beliefs"]["Lina"] = {
        "where": "square",
        "cell": [lx, ly],
        "tick": MORNING,
        "source": "heard",
        "from": "Jonas",
    }
    hilde["triggers"] = ["woke"]
    for _ in range(25):
        await v.step()
        if "found" in kinds(v, "Hilde"):
            break
    assert "found" in kinds(v, "Hilde") and hilde["goal"] is None
    assert any("You found Lina." in c for c in calls_of(llm, "Hilde"))


@pytest.mark.anyio
async def test_finding_someone_who_is_not_where_expected(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [find("Lina")]})
    morning(v)  # 09:30: Lina's routine says the flower garden
    put(v, "Lina", 2, 15)  # she is at the fields instead
    villager(v, "Hilde")["triggers"] = ["woke"]
    for _ in range(25):
        await v.step()
        if "missed" in kinds(v, "Hilde"):
            break
    hilde = villager(v, "Hilde")
    assert place_at(hilde["x"], hilde["y"]) == "flower_garden"
    missed = [e["text"] for e in hilde["events"] if e["kind"] == "missed"]
    assert missed == ["You did not find Lina: Lina is not here."]


# --- US4: knowing where the others are ---


@pytest.mark.anyio
async def test_beliefs_from_sight_go_stale_out_of_sight(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    mx, my = label_cell("market")
    put(v, "Jonas", mx, my)
    put(v, "Greta", mx - 4, my, goal={"kind": "place", "place": "fields"})
    await v.step()
    seen = villager(v, "Jonas")["beliefs"]["Greta"]
    assert seen["source"] == "seen"
    for _ in range(12):
        await v.step()
    stale = villager(v, "Jonas")["beliefs"]["Greta"]
    greta = villager(v, "Greta")
    assert stale["cell"] != [greta["x"], greta["y"]]  # she walked out of sight


@pytest.mark.anyio
async def test_hearing_where_someone_is(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Hilde": [say("Lina is at the square today.", "Jonas")]})
    neighbours_at_market(v)
    put(v, "Lina", 4, 19)  # far out of sight
    villager(v, "Hilde")["triggers"] = ["met"]
    await v.step()
    belief = villager(v, "Jonas")["beliefs"]["Lina"]
    assert (belief["where"], belief["source"], belief["from"]) == ("square", "heard", "Hilde")
    await v.step()
    assert "- Lina: at the square (Hilde said at 09:40)" in calls_of(llm, "Jonas")[0]


@pytest.mark.anyio
async def test_waking_clears_yesterdays_beliefs(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    jonas = villager(v, "Jonas")
    jonas["beliefs"]["Lina"] = {"where": "square", "cell": [1, 1], "tick": 0, "source": "seen"}
    for _ in range(3):  # 05:00
        await v.step()
    assert not jonas["asleep"] and "Lina" not in jonas["beliefs"]


# --- controls and failures (M6 carried over) ---


@pytest.mark.anyio
async def test_pauses_after_three_failed_steps(tmp_path: Path) -> None:
    down = RuntimeError("model down")
    v, _ = village_for(tmp_path, {n: [down] * 20 for n in VILLAGERS})
    morning(v)
    for x in v.world["villagers"]:
        x["triggers"] = ["woke"]
    v.world["interval"] = 0
    v.viewer_joined()
    v.start()
    assert v.task is not None
    await asyncio.wait_for(v.task, 5)
    assert v.world["running"] is False
    assert v.world["paused_reason"] == "every decision failed 3 steps in a row"
    assert villager(v, "Hilde")["last_action"]["reason"].startswith("turn failed")


@pytest.mark.anyio
async def test_pauses_without_a_viewer(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, idle_pause=0.1)
    v.world["interval"] = 0.02
    v.viewer_joined()
    v.start()
    await asyncio.sleep(0.1)
    assert v.world["running"]  # someone is watching
    v.viewer_left()
    assert v.task is not None
    await asyncio.wait_for(v.task, 5)
    assert v.world["paused_reason"] == "no viewer for 0.1 s"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("no json here", "turn failed"),  # the agent's JSON check fails the run
        ('{"action": "dance"}', "not a valid action"),
        ('{"action": "move", "place": "harbour"}', "unknown place 'harbour'"),
        ('{"action": "say", "text": "Hi", "to": "Bob"}', "unknown villager 'Bob'"),
        (RuntimeError("model down"), "turn failed"),
    ],
)
async def test_invalid_answers_wait_with_the_reason_recorded(
    tmp_path: Path, answer: str | Exception, reason: str
) -> None:
    v, _ = village_for(tmp_path, {"Jonas": [answer]})
    morning(v)
    jonas = villager(v, "Jonas")
    jonas["triggers"] = ["woke"]
    before = (jonas["x"], jonas["y"])
    await v.step()
    assert (jonas["x"], jonas["y"]) == before
    assert jonas["last_action"]["action"] == "wait"
    assert jonas["last_action"]["reason"].startswith(reason)
    assert jonas["events"][-1]["kind"] == "waited" and reason in jonas["events"][-1]["text"]
    [turn] = v.store.list_turns("Jonas")
    assert turn.village_action is not None and turn.village_action["reason"].startswith(reason)
    assert turn.village_tick == MORNING + 1


API_KEY = "sk-village-0123456789abcdefghij"


@pytest.mark.anyio
async def test_escaped_secret_is_redacted_after_decoding(tmp_path: Path) -> None:
    escaped = "\\u0073" + API_KEY[1:]  # survives redaction of the raw answer, decodes to the secret
    answer_text = '{"action": "say", "text": "my key is ' + escaped + '"}'
    v, _ = village_for(tmp_path, {"Hilde": [answer_text]}, secrets=(API_KEY,))
    neighbours_at_market(v)
    villager(v, "Hilde")["triggers"] = ["met"]
    await v.step()
    hilde = villager(v, "Hilde")
    assert hilde["speech"] is not None and "[REDACTED]" in hilde["speech"]["text"]
    stored = json.dumps(v.store.load_village())
    [turn] = v.store.list_turns("Hilde")
    assert API_KEY not in stored and API_KEY not in json.dumps(turn.village_action)


@pytest.mark.anyio
async def test_agent_names_beyond_the_first_fallback(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    for name in ("Mayor Hilde", "Mayor Hilde (village)"):
        store.create_agent(
            template_id="blocks", name=name, description="", sample_prompt="x", config={}
        )
    v = Village(store=store, models=fake_models(FakeLLM([])), bus=Bus())
    v.ensure_agents()
    agent = store.get_agent(villager(v, "Hilde")["agent_id"])
    assert agent is not None and agent.name == "Mayor Hilde (village 2)"


# --- M8: memory and reflection ---


def bedtime_tick(name: str, minutes_before: int = 10) -> int:
    return (VILLAGERS[name].bed - minutes_before - 270) // 10


@pytest.mark.anyio
async def test_a_conversation_becomes_a_memory_of_both(tmp_path: Path) -> None:
    goodbye = json.dumps({"action": "goodbye", "text": "Bye!"})
    v, _ = village_for(
        tmp_path, {"Hilde": [say("Fish?", "Jonas"), goodbye], "Jonas": [say("Yes!")]}
    )
    neighbours_at_market(v)
    villager(v, "Hilde")["triggers"] = ["met"]
    for _ in range(3):
        await v.step()
    for me, other in (("Hilde", "Jonas"), ("Jonas", "Hilde")):
        [memory] = [m for m in villager(v, me)["memories"] if m["kind"] == "conversation"]
        assert memory["about"] == [other] and memory["place"] == "market"
        assert memory["text"] == f"Talked with {other}: Hilde: Fish? / Jonas: Yes! / Hilde: Bye!"
    assert v.state()["villagers"][0]["memories"][0]["kind"] == "conversation"


@pytest.mark.anyio
async def test_found_missed_and_one_meeting_memory_a_day(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [find("Lina")]})
    morning(v)
    put(v, "Lina", 2, 15)  # not where her routine says
    villager(v, "Hilde")["triggers"] = ["woke"]
    for _ in range(25):
        await v.step()
        if "missed" in kinds(v, "Hilde"):
            break
    [missed] = [m for m in villager(v, "Hilde")["memories"] if m["kind"] == "missed"]
    assert missed["about"] == ["Lina"] and missed["importance"] == 2

    v2, _ = village_for(":memory:")
    morning(v2)
    mx, my = label_cell("market")
    put(v2, "Jonas", mx, my)
    put(v2, "Greta", mx + 1, my)
    await v2.step()
    put(v2, "Greta", mx + 5, my)  # apart
    await v2.step()
    put(v2, "Greta", mx + 1, my)  # together again, same day
    await v2.step()
    met = [m for m in villager(v2, "Jonas")["memories"] if m["kind"] == "met"]
    assert [m["about"] for m in met] == [["Greta"]]


@pytest.mark.anyio
async def test_a_morning_talk_is_recalled_in_the_afternoon(tmp_path: Path) -> None:
    goodbye = json.dumps({"action": "goodbye", "text": "See you!"})
    plan: dict[str, list[str | Exception]] = {
        "Hilde": [say("Sunflowers for the festival?", "Lina"), goodbye],
        "Lina": [say("I will bring some!")],
    }
    v, llm = village_for(tmp_path, plan)
    morning(v)
    mx, my = label_cell("square")
    put(v, "Hilde", mx, my, triggers=["met"])
    put(v, "Lina", mx + 1, my)
    for _ in range(3):
        await v.step()
    for name, (x, y) in (("Hilde", (2, 15)), ("Lina", (26, 4))):  # apart for hours
        put(v, name, x, y)
    for _ in range(3):
        await v.step()
    for x in v.world["villagers"]:  # 20 short-term events later, in the afternoon
        x["events"] = [{"tick": 50, "kind": "waited", "text": "You waited."}] * 10
    morning(v, tick=60)
    put(v, "Hilde", mx, my, triggers=["met"])
    put(v, "Lina", mx + 1, my, triggers=["met"])
    await v.step()
    for name in ("Hilde", "Lina"):
        prompt = calls_of(llm, name)[-1]
        remembered = prompt.split("What you remember:")[1]
        assert "I will bring some!" in remembered, name


@pytest.mark.anyio
async def test_reflection_on_falling_asleep_after_an_eventful_day(tmp_path: Path) -> None:
    reflection = json.dumps(
        {
            "learnings": ["Hilde needs fish for the festival."],
            "views": {"Hilde": "Pushy, but kind."},
        }
    )
    v, llm = village_for(tmp_path, {"Jonas:reflect": [reflection]})
    morning(v, tick=bedtime_tick("Jonas"))
    jonas = villager(v, "Jonas")  # at his door, so he sleeps as soon as it is bedtime
    jonas["memories"] = [
        {
            "tick": 30,
            "kind": "conversation",
            "about": ["Hilde"],
            "place": "market",
            "text": "Talked with Hilde: Hilde: Fish? / Jonas: Yes!",
            "importance": 3,
        }
    ]
    await v.step()
    assert jonas["asleep"]
    [prompt] = reflections_of(llm, "Jonas")
    assert "- Day 1 09:30 Talked with Hilde: Hilde: Fish? / Jonas: Yes!" in prompt
    assert jonas["learnings"] == [
        {"tick": v.world["tick"], "text": "Hilde needs fish for the festival."}
    ]
    assert jonas["views"] == {"Hilde": {"tick": v.world["tick"], "text": "Pushy, but kind."}}
    assert jonas["memories"][-1]["kind"] == "reflection"
    assert reflections_of(llm, "Greta") == []  # uneventful day: no reflection
    turn = v.store.list_turns("Jonas")[0]
    assert turn.village_action == {
        "action": "reflect",
        "learnings": ["Hilde needs fish for the festival."],
        "views": {"Hilde": "Pushy, but kind."},
    }
    state = v.state()["villagers"][1]
    assert state["learnings"] == [{"day": 1, "text": "Hilde needs fish for the festival."}]
    assert state["beliefs"][0]["view"] == "Pushy, but kind."

    for _ in range((VILLAGERS["Jonas"].wake + 1440 - VILLAGERS["Jonas"].bed) // 10):
        await v.step()  # through the night to 05:00
    prompt = calls_of(llm, "Jonas")[-1]
    assert "What you have learned:\n- Hilde needs fish for the festival." in prompt
    assert "; you think: Pushy, but kind." in prompt


@pytest.mark.anyio
async def test_an_invalid_reflection_changes_nothing(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina:reflect": ['{"views": {"Bob": "who?"}}']})
    morning(v, tick=bedtime_tick("Lina"))
    lina = villager(v, "Lina")
    lina["memories"] = [
        {
            "tick": 30,
            "kind": "met",
            "about": ["Greta"],
            "place": None,
            "text": "Met.",
            "importance": 1,
        }
    ]
    await v.step()
    assert lina["learnings"] == [] and lina["views"] == {} and len(lina["memories"]) == 1
    assert v.store.list_turns("Lina")[0].village_action == {
        "action": "reflect",
        "reason": "unknown villager 'Bob'",
    }


@pytest.mark.anyio
async def test_reflections_of_one_villager_never_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    v, _ = village_for(tmp_path)
    active, most = 0, 0
    run = v._run  # pyright: ignore[reportPrivateUsage]

    async def counting(*args: Any) -> tuple[str | None, str | None, str | None]:
        nonlocal active, most
        active += 1
        most = max(most, active)
        await asyncio.sleep(0.02)
        try:
            return await run(*args)
        finally:
            active -= 1

    monkeypatch.setattr(v, "_run", counting)
    v._start_reflection("Hilde")  # pyright: ignore[reportPrivateUsage]
    v._start_reflection("Hilde")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert most == 1 and v.reflections == {}


@pytest.mark.anyio
async def test_failing_reflections_do_not_pause_the_village(tmp_path: Path) -> None:
    down = RuntimeError("model down")
    v, _ = village_for(tmp_path, {n: [down] for n in (f"{x}:reflect" for x in VILLAGERS)})
    morning(v, tick=bedtime_tick("Jonas"))
    villager(v, "Jonas")["memories"] = [
        {
            "tick": 30,
            "kind": "met",
            "about": ["Greta"],
            "place": None,
            "text": "Met.",
            "importance": 1,
        }
    ]
    await v.step()
    await v.step()
    assert v.world["failed_ticks"] == 0
    assert v.store.list_turns("Jonas")[0].village_action == {
        "action": "reflect",
        "reason": "turn failed: run ended error",
    }


@pytest.mark.anyio
async def test_reset_clears_memory_and_keeps_the_reflection_agent(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    reflection_agent_id = v.world["reflection_agent_id"]
    assert v.store.get_agent(reflection_agent_id) is not None
    hilde = villager(v, "Hilde")
    hilde |= {"learnings": [{"tick": 1, "text": "x"}], "views": {"Lina": {"tick": 1, "text": "y"}}}
    await v.reset()
    hilde = villager(v, "Hilde")
    assert hilde["learnings"] == [] and hilde["views"] == {} and hilde["memories"] == []
    assert v.world["reflection_agent_id"] == reflection_agent_id


@pytest.mark.anyio
async def test_an_m7_world_keeps_going_with_empty_memory(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for x in world["villagers"]:
        for key in ("memories", "learnings", "views"):
            del x[key]
    del world["reflection_agent_id"]
    world |= {"version": 2, "tick": 40}
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 40)
    assert reloaded.world["paused_reason"] is None
    assert all(x["memories"] == [] for x in reloaded.world["villagers"])
    reloaded.ensure_agents()
    assert reloaded.world["reflection_agent_id"]


# --- M9: faster walks, goodbye to leave ---


@pytest.mark.anyio
async def test_walkers_go_three_cells_a_step_and_stop_on_arrival(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    fields = place_cells("fields")
    greta = put(v, "Greta", 11, 12, goal={"kind": "place", "place": "pier"})  # on the path
    start = (greta["x"], greta["y"])
    await v.step()
    assert abs(greta["x"] - start[0]) + abs(greta["y"] - start[1]) == CELLS_PER_STEP
    put(v, "Greta", 7, 14, goal={"kind": "place", "place": "fields"})  # just east of the fields
    distance = steps_to(greta["x"], greta["y"], fields)
    assert 0 < distance < CELLS_PER_STEP
    await v.step()  # arrives after one or two cells and stops there
    assert place_at(greta["x"], greta["y"]) == "fields" and greta["goal"] is None
    assert kinds(v, "Greta").count("arrived") == 1


@pytest.mark.anyio
async def test_crossing_the_village_takes_a_third_of_the_steps(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    fx, fy = label_cell("fields")
    greta = put(v, "Greta", fx, fy, goal={"kind": "place", "place": "pier"})
    distance = steps_to(fx, fy, place_cells("pier"))  # the steps it took in M8
    steps = 0
    while greta["goal"]:
        await v.step()
        steps += 1
    assert place_at(greta["x"], greta["y"]) == "pier" and steps <= -(-distance // 3)


@pytest.mark.anyio
async def test_a_walker_meets_someone_mid_step_and_walks_on(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    put(v, "Jonas", 12, 11)  # standing on the road
    greta = put(v, "Greta", 9, 11, goal={"kind": "place", "place": "pier"})
    await v.step()
    assert "met" in kinds(v, "Greta") and "met" in kinds(v, "Jonas")
    assert greta["x"] == 9 + CELLS_PER_STEP  # met Jonas on the way and kept walking


@pytest.mark.anyio
async def test_goodbye_to_find_someone_and_an_ignored_destination(tmp_path: Path) -> None:
    to_find = json.dumps({"action": "goodbye", "text": "Bye!", "villager": "Greta"})
    v, _ = village_for(tmp_path, {"Hilde": [to_find]})
    neighbours_at_market(v)
    v.world["conversations"] = [
        {"a": "Hilde", "b": "Jonas", "lines": 2, "last_tick": MORNING, "transcript": []}
    ]
    villager(v, "Hilde")["triggers"] = ["spoken to"]
    await v.step()
    hilde = villager(v, "Hilde")
    assert v.world["conversations"] == [] and hilde["goal"]["villager"] == "Greta"

    nowhere = json.dumps({"action": "goodbye", "place": "harbour"})
    v2, _ = village_for(":memory:", {"Hilde": [nowhere]})
    neighbours_at_market(v2)
    v2.world["conversations"] = [
        {"a": "Hilde", "b": "Jonas", "lines": 2, "last_tick": MORNING, "transcript": []}
    ]
    villager(v2, "Hilde")["triggers"] = ["spoken to"]
    await v2.step()
    hilde = villager(v2, "Hilde")
    assert v2.world["conversations"] == [] and hilde["goal"] is None
    assert "You said goodbye but stayed: unknown place 'harbour'." in [
        e["text"] for e in hilde["events"]
    ]


def set_system(v: Village, name: str, system: str) -> None:
    """The villager's stored agent with `system` as its whole system text."""
    agent = v.store.get_agent(villager(v, name)["agent_id"])
    assert agent is not None
    blocks = agent.config["blocks"]
    v.store.update_agent(
        agent.agent_id,
        name=agent.name,
        description=agent.description,
        sample_prompt=agent.sample_prompt,
        config={**agent.config, "blocks": [{**blocks[0], "system": system}, *blocks[1:]]},
    )


def set_rules(v: Village, name: str, text: str) -> None:
    """The villager's stored agent with `text` in place of the current rules."""
    from agent_lab.village.turn import RULES

    agent = v.store.get_agent(villager(v, name)["agent_id"])
    assert agent is not None
    blocks = agent.config["blocks"]
    system = blocks[0]["system"].replace(RULES, text)
    v.store.update_agent(
        agent.agent_id,
        name=agent.name,
        description=agent.description,
        sample_prompt=agent.sample_prompt,
        config={**agent.config, "blocks": [{**blocks[0], "system": system}, *blocks[1:]]},
    )


def system_of(v: Village, name: str) -> str:
    agent = v.store.get_agent(villager(v, name)["agent_id"])
    assert agent is not None
    return agent.config["blocks"][0]["system"]


@pytest.mark.anyio
@pytest.mark.parametrize("old", range(7))
async def test_stored_agents_get_the_new_rules_unless_edited(tmp_path: Path, old: int) -> None:
    from agent_lab.village.turn import OLD_RULES, RULES

    v, _ = village_for(tmp_path)
    set_rules(v, "Hilde", OLD_RULES[old])  # M7, M9, M11 plans, M11, M12 buy, meeting, site
    set_rules(v, "Jonas", "MY OWN RULES")
    Village(store=v.store, models=v.models, bus=Bus())  # loading refreshes the rules
    hilde = system_of(v, "Hilde")
    assert hilde.endswith(RULES) and hilde.count(RULES) == 1
    assert all(text not in hilde for text in OLD_RULES)
    assert system_of(v, "Jonas").endswith("MY OWN RULES")  # the owner's edit stays


def test_the_rules_history() -> None:
    from agent_lab.village.turn import OLD_RULES, RULES

    _m7, _m9, m11_plans, m11, m12_buy, m12_meeting, m12_site = OLD_RULES
    assert "Trust what you see over what you hear" in RULES and "Trust what you see" in m11_plans
    assert "Follow your plan for the day" in RULES
    assert '{"action": "work", "place": "fields", "until": "12:00"}' in RULES
    assert '{"action": "work"}' in m11
    assert '{"action": "buy", "goods": "wood"}' in RULES and "buy" not in m11
    assert '{"action": "buy", "goods": "wood"}' in m12_buy and "town hall meeting" not in m12_buy
    assert "Hilde holds a town hall meeting every third day at 17:00" in RULES
    assert "Hilde holds a town hall meeting" in m12_meeting and "building site" not in m12_meeting
    assert '{"action": "move", "place": "building site"}' in m12_site
    assert '{"action": "build", "until": "15:00"}' in RULES and '{"action": "bring"}' in RULES
    assert '"say": "Any flowers?"' in RULES and '{"action": "build"' not in m12_site
    assert "you keep doing it until it is done" in RULES
    assert "Each turn lists what you can do where you are" in RULES
    assert len(set(OLD_RULES)) == 7 and RULES not in OLD_RULES


@pytest.mark.anyio
async def test_each_walker_keeps_its_rhythm_across_steps_as_others_join(tmp_path: Path) -> None:
    interval = 1.2  # a move every 0.4 s per walker
    v, _ = village_for(tmp_path, move_gap=None)
    morning(v)
    v.world |= {"interval": interval, "running": True}  # timing as in the loop, without it
    greta = villager(v, "Greta")
    greta["goal"] = {"kind": "place", "place": "pier"}
    queue = v.bus.subscribe(CHANNEL)
    loop = asyncio.get_running_loop()
    started = loop.time()
    moves: list[float] = []

    async def collect(step: asyncio.Task[None]) -> None:
        last = (greta["x"], greta["y"])
        while not step.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), 0.02)
            except TimeoutError:
                continue
            if event["type"] != "state":
                continue
            now = next(x for x in event["state"]["villagers"] if x["name"] == "Greta")
            if (now["x"], now["y"]) != last:
                moves.append(loop.time() - started)
                last = (now["x"], now["y"])

    for n in range(3):
        if n == 1:  # Hilde, before Greta in the villager order, starts walking too
            villager(v, "Hilde")["goal"] = {"kind": "place", "place": "pier"}
        begun = loop.time()
        await collect(asyncio.create_task(v._step()))  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(max(0.0, interval - (loop.time() - begun)))
    spacing = [b - a for a, b in pairwise(moves)]
    assert len(moves) == 3 * CELLS_PER_STEP
    assert all(abs(s - interval / CELLS_PER_STEP) < 0.1 for s in spacing), spacing


@pytest.mark.anyio
async def test_moves_are_spread_evenly_over_the_step(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, move_gap=None)
    morning(v)
    v.world["interval"] = 1.2
    v.world["running"] = True  # timing as in the loop, without starting it
    for name in ("Hilde", "Greta"):
        villager(v, name)["goal"] = {"kind": "place", "place": "pier"}
    queue = v.bus.subscribe(CHANNEL)
    times: dict[str, list[float]] = {"Hilde": [], "Greta": []}
    before = {x["name"]: (x["x"], x["y"]) for x in v.world["villagers"]}
    step = asyncio.create_task(v._step())  # pyright: ignore[reportPrivateUsage]
    loop = asyncio.get_running_loop()
    started = loop.time()
    while not step.done() or not queue.empty():
        try:
            event = await asyncio.wait_for(queue.get(), 0.05)
        except TimeoutError:
            continue
        if event["type"] != "state":
            continue
        now = {x["name"]: (x["x"], x["y"]) for x in event["state"]["villagers"]}
        for name in times:
            if now[name] != before[name]:
                times[name].append(loop.time() - started)
        before = now
    for name, at in times.items():
        assert len(at) == CELLS_PER_STEP, name
        spacing = [b - a for a, b in pairwise(at)]
        assert all(abs(s - 1.2 / CELLS_PER_STEP) < 0.08 for s in spacing), (name, spacing)


# --- M10: seasons ---


@pytest.mark.anyio
async def test_an_m9_world_keeps_going_with_the_seasons(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for key in ("growth", "tended", "day_record", "festival", "chronicle", "chronicler_agent_id"):
        del world[key]
    world |= {"version": 3, "tick": 144 * 9 + 30}  # day 10: summer
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 144 * 9 + 30)
    assert reloaded.world["paused_reason"] is None
    assert reloaded.world["growth"]["fields"]["stage"] == "growing"
    assert reloaded.world["growth"]["flower_garden"]["stage"] == "blooming"
    assert reloaded.world["chronicle"] == [] and reloaded.world["day_record"] is None
    assert reloaded.state()["calendar"]["season"] == "summer"


@pytest.mark.anyio
async def test_steps_follow_the_pace_while_anyone_is_awake(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    v.world["interval"] = 0.4  # the pace, scaled down (SC-001)
    v.viewer_joined()
    started = v.world["tick"]
    v.start()
    await asyncio.sleep(1.0)  # steps at 0, 0.4 and 0.8 s; NIGHT_STEP would give 5
    v.pause()
    assert v.world["tick"] - started == 3


@pytest.mark.anyio
async def test_one_chronicle_a_night_for_the_day_it_began(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "IDLE_STEPS", 10**6)  # decisions only on triggers: a fast week
    v, llm = village_for(tmp_path, {"Greta": [move("market")]}, calls=2000)
    for _ in range(7 * 144):  # day 1, 04:30, to day 8, 04:30 (SC-004)
        await v.step()
    chronicle = v.world["chronicle"]
    assert [e["day"] for e in chronicle] == [1, 2, 3, 4, 5, 6, 7]
    assert len(chronicles_of(llm)) == 7
    first = chronicle[0]
    assert (first["year"], first["season"], first["day_of_season"]) == (1, "spring", 1)
    assert (first["weather"], first["title"]) == (weather(1), "A quiet day")
    assert "Greta set out to go to the market." in chronicles_of(llm)[0]
    run = v.store.get_run(first["run_id"])
    assert run is not None and run.villager is None and run.village_tick is not None
    assert run.village_action == {"action": "chronicle", "day": 1, **json.loads(QUIET_DAY)}
    assert v.state()["chronicle"][0]["day"] == 7  # newest first


@pytest.mark.anyio
async def test_a_chronicle_after_midnight_belongs_to_the_day_before(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    v.world["tick"] = 20 * 144 + (23 * 60 + 50 - 270) // 10  # day 21, 23:50: festival night
    for x in v.world["villagers"]:
        x["asleep"] = x["name"] != "Hilde"
    put(v, "Hilde", 30, 12, bedtime=True, goal={"kind": "home"})  # far from her door
    v.world["day_record"] = {"day": 21, "items": []}
    await v.step()
    assert v.state()["calendar"]["season"] == "winter"  # day 22 now
    v._note("Hilde was still walking home.")  # pyright: ignore[reportPrivateUsage]
    while not villager(v, "Hilde")["asleep"]:
        await v.step()
    [entry] = v.world["chronicle"]
    assert (entry["day"], entry["season"], entry["day_of_season"]) == (21, "autumn", 7)
    assert entry["weather"] == weather(21)
    assert "Hilde was still walking home." in chronicles_of(llm)[0]
    assert chronicles_of(llm)[0].startswith("Day 21 (day 7 of autumn, year 1).")


async def _night(v: Village) -> str | None:
    """Hilde, the last one up, goes to bed at her door with a day behind her; the id of the
    chronicle run that follows."""
    morning(v, tick=bedtime_tick("Hilde"))
    for x in v.world["villagers"]:
        x["asleep"] = x["name"] != "Hilde"
    v.world["day_record"] = {"day": 1, "items": [{"tick": 30, "text": "Lina met Greta."}]}
    queue = v.bus.subscribe(CHANNEL)
    await v.step()
    assert villager(v, "Hilde")["asleep"] and v.world["day_record"] is None
    started = [e for e in drain(queue) if e["type"] == "decision_started"]
    return next((e["run_id"] for e in started if e["villager"] is None), None)


@pytest.mark.anyio
async def test_an_invalid_chronicle_adds_nothing(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"chronicle": ['{"title": "A lovely day"}']})
    run_id = await _night(v)
    assert v.world["chronicle"] == []
    assert "- 09:30 Lina met Greta." in chronicles_of(llm)[0]
    run = v.store.get_run(run_id or "")
    assert run is not None
    assert run.village_action == {
        "action": "chronicle",
        "day": 1,
        "reason": "not a valid entry: Field required",
    }


@pytest.mark.anyio
async def test_a_chronicle_naming_other_weather_is_asked_again_once(tmp_path: Path) -> None:
    stormy = json.dumps({"title": "Storm coming", "text": "They hurried before the storm arrived."})
    v, llm = village_for(tmp_path, {"chronicle": [stormy, QUIET_DAY]})
    assert weather(1) == "sun"
    run_id = await _night(v)
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    first, again = chronicles_of(llm)
    assert "They hurried before the storm arrived." in again and again.startswith(first)
    assert [e["title"] for e in v.world["chronicle"]] == ["A quiet day"]
    run = v.store.get_run(run_id or "")
    assert run is not None and run.village_action == {
        "action": "chronicle",
        "day": 1,
        "reason": "it named weather other than the day's (storm); asked again",
    }


@pytest.mark.anyio
async def test_a_chronicle_slipping_twice_keeps_the_second_entry(tmp_path: Path) -> None:
    stormy = json.dumps({"title": "Storm coming", "text": "They hurried before the storm arrived."})
    v, llm = village_for(tmp_path, {"chronicle": [stormy, stormy]})
    await _night(v)
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert len(chronicles_of(llm)) == 2  # asked again once, not more
    assert [e["title"] for e in v.world["chronicle"]] == ["Storm coming"]


@pytest.mark.anyio
async def test_a_failing_chronicle_does_not_pause_the_village(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"chronicle": [RuntimeError("model down")]})
    await _night(v)
    await v.step()
    assert v.world["chronicle"] == [] and v.world["failed_ticks"] == 0


@pytest.mark.anyio
async def test_the_chronicle_keeps_one_year(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    old = {"day": 0, "title": "old", "text": "x"}
    v.world["chronicle"] = [old] * 28
    await _night(v)
    assert len(v.world["chronicle"]) == 28 and v.world["chronicle"][-1]["title"] == "A quiet day"


@pytest.mark.anyio
async def test_reset_clears_the_chronicle_and_keeps_the_chronicler(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    chronicler = v.world["chronicler_agent_id"]
    agent = v.store.get_agent(chronicler)
    assert agent is not None and agent.name == "Village chronicler"
    await _night(v)
    assert v.world["chronicle"]
    await v.reset()
    assert v.world["chronicle"] == [] and v.world["chronicler_agent_id"] == chronicler


@pytest.mark.anyio
async def test_only_working_villagers_tend(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v, tick=6)  # 05:30: Lina sleeps until 06:30
    fx, fy = place_cells("fields")[0]
    gx, gy = place_cells("flower_garden")[0]
    put(v, "Greta", fx, fy)  # standing: no help
    put(v, "Jonas", fx + 1, fy, working={"place": "fields", "steps": 0})
    put(v, "Lina", gx, gy, asleep=True)
    await v.step()
    await v.step()
    assert v.world["tended"] == {"fields": 2, "flower_garden": 0}
    villager(v, "Greta")["working"] = {"place": "fields", "steps": 0}
    await v.step()
    assert v.world["tended"] == {"fields": 4, "flower_garden": 0}


@pytest.mark.anyio
async def test_yesterdays_work_shows_when_the_first_villager_wakes(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.world["tick"] = 144 + 2  # day 2, 04:50: everyone asleep, Jonas wakes at 05:00
    v.world["tended"] = {"fields": 8, "flower_garden": 0}
    await v.step()
    await v.step()
    assert not villager(v, "Jonas")["asleep"]
    assert v.world["growth"]["fields"]["stage"] == "tilled"
    assert v.world["tended"] == {"fields": 0, "flower_garden": 0}
    record = v.world["day_record"]
    assert record["day"] == 2
    assert "Overnight: The fields were tilled." in [i["text"] for i in record["items"]]
    assert v.state()["growth"]["fields"] == {"stage": "tilled", "neglected": False}


async def _festival_evening(v: Village, day: int) -> None:
    """Jonas and Lina on the square from 20:40 until Jonas's bedtime at 21:00; Greta elsewhere."""
    morning(v, tick=(day - 1) * 144 + (20 * 60 + 40 - 270) // 10)
    sx, sy = label_cell("square")
    put(v, "Jonas", sx, sy)
    put(v, "Lina", sx + 2, sy + 2)
    put(v, "Greta", *door("Greta"))
    v.world["day_record"] = {"day": day, "items": []}
    await v.step()  # 20:50
    await v.step()  # 21:00: Jonas's bedtime


@pytest.mark.anyio
async def test_festival_guests_remember_who_else_was_there(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    await _festival_evening(v, 21)
    assert v.world["festival"] == {"day": 21, "present": ["Jonas", "Lina"]}
    memory = villager(v, "Jonas")["memories"][-1]
    assert (memory["kind"], memory["importance"]) == ("festival", 5)
    assert memory["text"] == "The harvest festival on the square with Lina. The stalls stood empty."
    assert memory["about"] == ["Lina"]
    assert not any(m["kind"] == "festival" for m in villager(v, "Greta")["memories"])
    greta_events = [e for e in villager(v, "Greta")["events"] if e["kind"] == "festival"]
    assert [e["text"] for e in greta_events] == [f"{runner.FESTIVAL_BEGINS}."]  # once, to all
    assert len(calls_of(llm, "Greta")) >= 1  # and she decided on it
    notes = [i["text"] for i in v.world["day_record"]["items"]]
    assert "Jonas joined the harvest festival on the square." in notes


@pytest.mark.anyio
async def test_no_festival_on_other_days(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    await _festival_evening(v, 20)
    assert v.world["festival"] is None
    assert not any(m["kind"] == "festival" for m in villager(v, "Jonas")["memories"])


# --- M11: plans and purpose ---


@pytest.mark.anyio
async def test_an_m10_world_keeps_going_with_empty_hands(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for x in world["villagers"]:
        for key in ("plan", "basket", "working", "said"):
            del x[key]
    for key in ("stalls", "harvest", "planner_agent_id"):
        del world[key]
    world |= {"version": 4, "tick": 144 * 20 + 30, "chronicle": [{"day": 20, "title": "t"}]}
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 144 * 20 + 30)
    assert reloaded.world["paused_reason"] is None
    assert reloaded.world["chronicle"] == [{"day": 20, "title": "t"}]  # M10 history is kept
    assert all(x["basket"] is None and x["plan"] is None for x in reloaded.world["villagers"])
    assert reloaded.world["stalls"] == {"fish": 0, "vegetables": 0, "flowers": 0}


@pytest.mark.anyio
async def test_reset_clears_plans_baskets_and_stalls_and_keeps_the_shared_agents(
    tmp_path: Path,
) -> None:
    v, _ = village_for(tmp_path)
    ids = {k: v.world[k] for k in ("reflection_agent_id", "chronicler_agent_id")}
    ids["planner_agent_id"] = v.world["planner_agent_id"]
    assert ids["planner_agent_id"]
    put(v, "Jonas", 1, 1, basket="fish", working={"place": "pier", "steps": 3}, said=["Hi"])
    v.world["stalls"]["fish"] = 2
    await v.reset()
    jonas = villager(v, "Jonas")
    assert jonas["basket"] is jonas["working"] is None and jonas["said"] == []
    assert v.world["stalls"] == {"fish": 0, "vegetables": 0, "flowers": 0}
    assert {k: v.world[k] for k in ids} == ids


@pytest.mark.anyio
async def test_an_m11_world_keeps_going_with_nothing_built(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for key in ("trader", "meeting", "project", "built", "meeting_agent_id"):
        del world[key]
    world["villagers"][1]["basket"] = "fish"
    world |= {"version": 5, "tick": 144 * 20 + 30}
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 144 * 20 + 30)
    assert reloaded.world["paused_reason"] is None
    assert villager(reloaded, "Jonas")["basket"] == "fish"  # M11 state is kept
    assert reloaded.world["project"] is None and reloaded.world["built"] == []
    reloaded.world["running"] = False
    await reloaded.step()  # and it keeps going


@pytest.mark.anyio
async def test_reset_clears_what_was_built_and_keeps_the_meeting_agent(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    kept = v.world["meeting_agent_id"]
    assert kept
    v.world["built"] = [{"key": "boat", "day": 3}]
    await v.reset()
    assert v.world["built"] == [] and v.world["meeting_agent_id"] == kept
    assert "meeting_agent_id" not in v.state()


@pytest.mark.anyio
async def test_a_version_6_world_keeps_going_with_intentions(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for x in world["villagers"]:
        del x["intention"], x["requests"]
    world["built"] = [{"key": "boat", "day": 3}]
    world |= {"version": 6, "tick": 144 * 20 + 30}
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 144 * 20 + 30)
    assert reloaded.world["built"] == [{"key": "boat", "day": 3}]
    assert all(x["intention"] is None for x in reloaded.world["villagers"])
    reloaded.world["running"] = False
    await reloaded.step()  # and it keeps going


@pytest.mark.anyio
async def test_reset_clears_intentions_and_requests(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    greta = villager(v, "Greta")
    greta["intention"] = {"kind": "go", "place": "market", "villager": None, "until": None}
    greta["requests"] = [{"from": "Hilde", "goods": "vegetables", "tick": 0}]
    await v.reset()
    assert villager(v, "Greta")["intention"] is None and villager(v, "Greta")["requests"] == []


def test_the_state_gives_the_intention_with_times_and_leaves_out_requests() -> None:
    v, _ = village_for(":memory:")
    v.world["tick"] = MORNING
    villager(v, "Greta")["intention"] = {
        "kind": "build",
        "place": "site",
        "villager": None,
        "until": 15 * 60,
        "purpose": "plant the trees",
        "since": MORNING,
        "say": None,
    }
    state = {x["name"]: x for x in v.state()["villagers"]}
    assert state["Greta"]["intention"] == {
        "kind": "build",
        "place": "site",
        "villager": None,
        "until": "15:00",
        "purpose": "plant the trees",
        "since": "09:30",
    }
    assert state["Jonas"]["intention"] is None
    assert all("requests" not in x for x in state.values())


def test_the_state_leaves_out_said_harvest_and_the_planner() -> None:
    v, _ = village_for(":memory:")
    state = v.state()
    assert not {"harvest", "planner_agent_id"} & set(state)
    assert all("said" not in x for x in state["villagers"])


JONAS_WAKES = 3  # tick of 05:00


def plan_json(*entries: tuple[str, str, str]) -> str:
    return json.dumps({"plan": [{"time": t, "place": p, "purpose": why} for t, p, why in entries]})


def talk(v: Village, a: str, b: str, lines: int) -> dict[str, Any]:
    c = {"a": a, "b": b, "lines": lines, "last_tick": v.world["tick"]}
    c["transcript"] = [f"{(a, b)[i % 2]}: line {i}" for i in range(lines)]
    v.world["conversations"].append(c)
    return c


def plan_turn(v: Village, name: str) -> dict[str, Any] | None:
    """What the villager's latest plan run did."""
    actions = [t.village_action for t in v.store.list_turns(name)]
    return next((a for a in actions if a and a["action"] == "plan"), None)


def today_plan(v: Village, name: str, revisions: int = 0) -> None:
    day = runner.clock(v.world["tick"])[0]
    entries = [
        {"minute": 480, "place": "market", "villager": None, "purpose": "trade"},
        {"minute": 1020, "place": "home", "villager": None, "purpose": "rest"},
    ]
    villager(v, name)["plan"] = {"day": day, "entries": entries, "revisions": revisions}


@pytest.mark.anyio
async def test_a_villager_plans_its_day_on_waking(tmp_path: Path) -> None:
    fishing = plan_json(("05:00", "pier", "Catch fish"), ("11:00", "market", "Sell the catch"))
    v, llm = village_for(tmp_path, {"Jonas:plan": [fishing]})
    v.world["tick"] = JONAS_WAKES - 1
    await v.step()
    jonas = villager(v, "Jonas")
    assert jonas["plan"] == {
        "day": 1,
        "entries": [
            {"minute": 300, "place": "pier", "villager": None, "purpose": "Catch fish"},
            {"minute": 660, "place": "market", "villager": None, "purpose": "Sell the catch"},
        ],
        "revisions": 0,
    }
    assert len(plans_of(llm, "Jonas")) == 1 and plans_of(llm, "Hilde") == []  # still asleep
    assert "planned" in kinds(v, "Jonas")
    assert "Jonas planned the day (intentions, not events): 05:00 pier: Catch fish" in json.dumps(
        v.world["day_record"]
    )
    assert plan_turn(v, "Jonas") == {
        "action": "plan",
        "revision": 0,
        "entries": ["05:00 pier: Catch fish", "11:00 market: Sell the catch"],
    }
    await v.step()  # his decision on waking sees the plan, the current entry marked
    assert (
        "- 05:00 pier: Catch fish (now)\n- 11:00 market: Sell the catch (next)"
        in (calls_of(llm, "Jonas")[-1])
    )
    state = next(x for x in v.state()["villagers"] if x["name"] == "Jonas")
    assert state["plan"] == {
        "entries": [
            {"time": "05:00", "place": "pier", "villager": None, "purpose": "Catch fish"},
            {"time": "11:00", "place": "market", "villager": None, "purpose": "Sell the catch"},
        ],
        "current": 0,
        "next": 1,
        "revisions": 0,
    }


@pytest.mark.anyio
async def test_an_invalid_plan_keeps_the_previous_one(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Jonas:plan": ['{"plan": []}']})
    v.world["tick"] = JONAS_WAKES - 1
    await v.step()
    assert villager(v, "Jonas")["plan"] is None
    assert plan_turn(v, "Jonas") == {
        "action": "plan",
        "revision": 0,
        "reason": "a plan needs at least 2 entries",
    }
    assert next(x for x in v.state()["villagers"] if x["name"] == "Jonas")["plan"] is None


@pytest.mark.anyio
async def test_a_long_talk_revises_both_plans_twice_a_day_at_most(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v)
    today_plan(v, "Greta")
    today_plan(v, "Lina", revisions=2)
    v._end_conversation(talk(v, "Greta", "Lina", 4), "test")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    revisions = plans_of(llm, "Greta")
    assert len(revisions) == 1 and plans_of(llm, "Lina") == []  # Lina used both revisions
    assert "Your plan so far:\n- 08:00 market: trade" in revisions[0]
    assert "The conversation you just had:\nGreta: line 0 / Lina: line 1" in revisions[0]
    greta = villager(v, "Greta")
    assert greta["plan"]["revisions"] == 1 and greta["plan"]["entries"][1]["place"] == "home"
    assert (plan_turn(v, "Greta") or {}).get("revision") == 1
    v._end_conversation(talk(v, "Greta", "Lina", 3), "test")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert len(plans_of(llm, "Greta")) == 1  # 3 lines are not a long talk
    for _ in range(2):
        v._end_conversation(talk(v, "Greta", "Lina", 5), "test")  # pyright: ignore[reportPrivateUsage]
        await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert len(plans_of(llm, "Greta")) == 2 and villager(v, "Greta")["plan"]["revisions"] == 2


@pytest.mark.anyio
async def test_revisions_started_back_to_back_still_count_two(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, delay=0.05)
    morning(v)
    today_plan(v, "Greta")
    v._end_conversation(talk(v, "Greta", "Lina", 4), "test")  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(0.01)  # the first revision is running
    v._end_conversation(talk(v, "Greta", "Jonas", 4), "test")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert len(plans_of(llm, "Greta")) == 2
    assert villager(v, "Greta")["plan"]["revisions"] == 2
    revisions = [(t.village_action or {}).get("revision") for t in v.store.list_turns("Greta")]
    assert sorted(r for r in revisions if r is not None) == [1, 2]
    v._end_conversation(talk(v, "Greta", "Lina", 4), "test")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert len(plans_of(llm, "Greta")) == 2  # no third revision


@pytest.mark.anyio
async def test_a_plan_finishing_on_another_day_is_dropped(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, delay=0.05)
    morning(v)
    v._start_plan("Jonas")  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(0.01)
    v.world["tick"] += 144  # the next day began meanwhile
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert villager(v, "Jonas")["plan"] is None
    assert plan_turn(v, "Jonas") == {
        "action": "plan",
        "revision": 0,
        "reason": "the day it was for is over",
    }


@pytest.mark.anyio
async def test_failing_plans_do_not_pause_the_village(tmp_path: Path) -> None:
    down = RuntimeError("model down")
    v, _ = village_for(tmp_path, {f"{n}:plan": [down] for n in VILLAGERS})
    v.world["tick"] = JONAS_WAKES - 1
    await v.step()
    await v.step()
    assert v.world["failed_ticks"] == 0
    turns = [t.village_action for t in v.store.list_turns("Jonas")]
    assert {"action": "plan", "revision": 0, "reason": "turn failed: run ended error"} in turns


@pytest.mark.anyio
async def test_step_and_reset_wait_for_plans(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, delay=0.02)
    v.world["tick"] = JONAS_WAKES - 1
    await v.step()
    assert v.plans == {} and villager(v, "Jonas")["plan"] is not None
    morning(v)
    v._start_plan("Hilde")  # pyright: ignore[reportPrivateUsage]
    await v.reset()
    assert v.plans == {} and villager(v, "Hilde")["plan"] is None


def test_the_planner_agent_is_created_once_and_listed() -> None:
    v, _ = village_for(":memory:")
    v.ensure_agents()
    planners = [a for a in v.store.list_agents() if a.name.startswith("Village planner")]
    assert [a.agent_id for a in planners] == [v.world["planner_agent_id"]]


@pytest.mark.anyio
async def test_the_day_record_marks_what_villagers_said_as_claims(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    record: dict[str, Any] = {"day": 1, "items": []}
    v.world["day_record"] = record
    v._end_conversation(talk(v, "Greta", "Lina", 2), "test")  # pyright: ignore[reportPrivateUsage]
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    notes = [i["text"] for i in record["items"]]
    assert "Greta and Lina talked; what they said (their claims): Greta: line 0 / Lina: line 1" in (
        notes
    )


@pytest.mark.anyio
async def test_a_repeated_line_is_refused_and_never_heard(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [say("where are the fish", "Jonas")]})
    neighbours_at_market(v)
    villager(v, "Hilde").update(triggers=["met"], said=["Where are the fish?"])
    await v.step()
    assert villager(v, "Hilde")["last_action"] == {
        "action": "wait",
        "reason": "you already said that",
    }
    assert villager(v, "Jonas")["inbox"] == [] and "heard" not in kinds(v, "Jonas")
    [turn] = v.store.list_turns("Hilde")
    assert turn.village_action == {"action": "wait", "reason": "you already said that"}


@pytest.mark.anyio
async def test_a_villager_keeps_its_last_three_lines_as_spoken(tmp_path: Path) -> None:
    long = "Fish " * 50
    lines: list[str | Exception] = [say(t, "Jonas") for t in ("One.", "Two.", "Three.", long)]
    v, _ = village_for(tmp_path, {"Hilde": lines})
    neighbours_at_market(v)
    for _ in lines:
        villager(v, "Hilde")["triggers"] = ["met"]
        await v.step()
    assert villager(v, "Hilde")["said"] == ["Two.", "Three.", long[:SPEECH_SHOWN]]


# --- US4: work and festival deliveries ---

WORK = '{"action": "work"}'


def give(to: str | None = None) -> str:
    return json.dumps({"action": "give", "to": to})


def notes(v: Village) -> list[str]:
    return [i["text"] for i in v.world["day_record"]["items"]]


def texts(v: Village, name: str, kind: str) -> list[str]:
    return [e["text"] for e in villager(v, name)["events"] if e["kind"] == kind]


@pytest.mark.anyio
async def test_work_starts_and_goes_on_where_the_villager_stands(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [WORK, WORK]})
    morning(v)
    fx, fy = place_cells("fields")[0]
    put(v, "Greta", fx, fy, triggers=["arrived"])
    await v.step()
    greta = villager(v, "Greta")
    assert greta["working"] == {"place": "fields", "steps": 0}
    assert texts(v, "Greta", "worked") == ["You started working at the fields."]
    [turn] = v.store.list_turns("Greta")
    assert turn.village_action == {
        "action": "work",
        "place": "fields",
        "intention": {
            "kind": "work",
            "place": "fields",
            "villager": None,
            "purpose": None,
            "until": None,
            "since": "09:40",
        },
    }
    state = next(x for x in v.state()["villagers"] if x["name"] == "Greta")
    assert (state["working"], state["state"], state["basket"]) == ("fields", "working", None)
    assert v.state()["stalls"] == {"fish": 0, "vegetables": 0, "flowers": 0}
    greta["triggers"] = ["spoken to"]
    await v.step()
    assert greta["working"] == {"place": "fields", "steps": 1}  # kept, not restarted


@pytest.mark.anyio
async def test_working_together_fills_a_basket_in_half_a_village_hour(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v)
    v.world["growth"]["fields"]["stage"] = "ripe"
    v.world["day_record"] = {"day": 1, "items": []}
    fx, fy = place_cells("fields")[0]
    put(v, "Greta", fx, fy, working={"place": "fields", "steps": 0})
    put(v, "Lina", fx + 1, fy, working={"place": "fields", "steps": 0})
    for _ in range(3):
        await v.step()
    assert v.world["tended"]["fields"] == 6
    assert (villager(v, "Greta")["basket"], villager(v, "Lina")["basket"]) == ("vegetables", None)
    assert texts(v, "Greta", "basket") == ["You filled a basket of vegetables."]
    assert "Greta filled a basket of vegetables." in notes(v)
    assert "You carry a basket of vegetables." in calls_of(llm, "Greta")[-1]  # it decided


@pytest.mark.anyio
async def test_fishing_needs_jonas_to_start_but_not_to_go_on(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [WORK, WORK], "Jonas": [move("market")]})
    morning(v)
    pier = place_cells("pier")
    put(v, "Hilde", *pier[0], triggers=["arrived"], neighbours=["Jonas"])
    put(v, "Jonas", *pier[1], neighbours=["Hilde"])
    await v.step()
    assert villager(v, "Hilde")["last_action"] == {
        "action": "wait",
        "reason": "only Jonas fishes here; work with him while he fishes",
    }
    villager(v, "Jonas")["working"] = {"place": "pier", "steps": 0}
    villager(v, "Hilde")["triggers"] = ["spoken to"]
    await v.step()
    assert villager(v, "Hilde")["working"] == {"place": "pier", "steps": 0}
    villager(v, "Jonas")["triggers"] = ["spoken to"]
    await v.step()
    assert villager(v, "Jonas")["working"] is None
    await v.step()  # Jonas walks off; Hilde fishes on
    assert villager(v, "Hilde")["working"] == {"place": "pier", "steps": 2}


@pytest.mark.anyio
async def test_walking_off_and_bedtime_end_work_and_talking_does_not(tmp_path: Path) -> None:
    leave = json.dumps({"action": "goodbye", "place": "market"})
    v, _ = village_for(tmp_path, {"Greta": [say("Hard work!"), leave]})
    morning(v)
    fx, fy = place_cells("fields")[0]
    put(v, "Greta", fx, fy, triggers=["met"], working={"place": "fields", "steps": 0})
    put(v, "Lina", fx + 1, fy, working={"place": "fields", "steps": 0}, basket="flowers")
    await v.step()
    assert villager(v, "Greta")["working"] is not None  # talking while working
    villager(v, "Greta")["triggers"] = ["spoken to"]
    await v.step()
    assert villager(v, "Greta")["working"] is None
    v.world["tick"] = bedtime_tick("Lina", minutes_before=0) - 1
    await v.step()
    lina = villager(v, "Lina")
    assert lina["bedtime"] and lina["working"] is None and lina["basket"] == "flowers"


@pytest.mark.anyio
async def test_give_a_basket_to_a_villager_and_onto_the_stalls(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [give("Jonas")], "Jonas": [give()]})
    morning(v)
    v.world["day_record"] = {"day": 1, "items": []}
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, basket="fish", triggers=["met"], neighbours=["Jonas"])
    put(v, "Jonas", sx + 1, sy, neighbours=["Hilde"])  # already met: only Hilde decides
    villager(v, "Hilde")["requests"] = [{"from": "Jonas", "goods": "fish", "tick": MORNING}]
    await v.step()
    assert villager(v, "Hilde")["basket"] is None
    assert villager(v, "Jonas")["basket"] == "fish"
    assert texts(v, "Hilde", "gave") == ["You gave your basket of fish to Jonas."]
    assert texts(v, "Jonas", "received") == ["Hilde gave you a basket of fish."]
    assert villager(v, "Jonas")["triggers"] == ["given"]
    await v.step()  # Jonas decides on it
    assert villager(v, "Jonas")["basket"] is None
    assert v.world["stalls"] == {"fish": 1, "vegetables": 0, "flowers": 0}
    assert texts(v, "Jonas", "gave") == ["You set out your fish on the festival stalls."]
    assert notes(v)[-2:] == [
        "Hilde gave a basket of fish to Jonas.",
        "Jonas set out fish on the festival stalls.",
    ]
    [turn] = v.store.list_turns("Jonas")
    assert turn.village_action == {"action": "give", "to": None, "goods": "fish"}
    assert next(x for x in v.state()["villagers"] if x["name"] == "Jonas")["basket"] is None


def delivering(work_only: bool = False) -> Callable[[list[Message]], ChatResponse | Exception]:
    """Villagers work where they stand, carry a basket to the square and set it out there."""
    others = responder({})

    def respond(messages: list[Message]) -> ChatResponse | Exception:
        if is_plan(messages) or is_reflection(messages) or is_chronicle(messages):
            return others(messages)
        seen = messages[1]["content"] or ""
        if "You carry a basket" in seen and not work_only:
            return answer(give() if "You are at the square." in seen else move("square"))
        return answer(WAIT if "You are working here." in seen else WORK)

    return respond


@pytest.mark.parametrize(("work_only", "stalls"), [(False, 1), (True, 0)])
@pytest.mark.anyio
async def test_a_scripted_autumn_day_fills_the_stalls_only_with_deliveries(
    tmp_path: Path, work_only: bool, stalls: int
) -> None:
    v, _ = village_for(tmp_path, respond=delivering(work_only), calls=600)
    morning(v, tick=20 * 144 + 30)  # day 21, the festival, 09:30
    v.world["growth"]["fields"]["stage"] = "harvested"
    v.world["growth"]["flower_garden"]["stage"] = "blooming"
    for name, place in (("Jonas", "pier"), ("Greta", "fields"), ("Lina", "flower_garden")):
        put(v, name, *place_cells(place)[0], triggers=["arrived"])
    for _ in range(20):
        await v.step()
    assert v.world["stalls"] == {"fish": stalls, "vegetables": stalls, "flowers": stalls}


@pytest.mark.anyio
async def test_the_festival_memory_names_the_goods_on_the_stalls(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.world["stalls"] = {"fish": 2, "vegetables": 0, "flowers": 1}
    await _festival_evening(v, 21)
    assert villager(v, "Jonas")["memories"][-1]["text"] == (
        "The harvest festival on the square with Lina. The stalls held fish and flowers."
    )


@pytest.mark.anyio
async def test_work_on_the_way_stops_the_walk(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [WORK]})
    morning(v)
    fx, fy = place_cells("fields")[0]
    put(v, "Greta", fx, fy, triggers=["met"], goal={"kind": "place", "place": "market"})
    await v.step()
    greta = villager(v, "Greta")
    assert greta["goal"] is None and greta["working"] == {"place": "fields", "steps": 0}


@pytest.mark.anyio
async def test_a_basket_that_came_while_deciding_is_not_given_on(tmp_path: Path) -> None:
    plan: dict[str, list[str | Exception]] = {"Hilde": [give("Greta")], "Greta": [give("Lina")]}
    v, _ = village_for(tmp_path, plan, delay=0.01)  # both prompts are written before either answer
    morning(v)
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, basket="fish", triggers=["met"], neighbours=["Greta"])
    put(v, "Greta", sx + 1, sy, triggers=["met"], neighbours=["Hilde", "Lina"])
    put(v, "Lina", sx + 2, sy, neighbours=["Greta"])
    villager(v, "Hilde")["requests"] = [{"from": "Greta", "goods": "fish", "tick": MORNING}]
    villager(v, "Greta")["requests"] = [{"from": "Lina", "goods": "fish", "tick": MORNING}]
    await v.step()  # both decide at once; Greta's empty hands are in her prompt
    assert villager(v, "Greta")["basket"] == "fish" and villager(v, "Lina")["basket"] is None
    assert villager(v, "Greta")["last_action"] == {
        "action": "wait",
        "reason": "the basket came to you after you decided; decide again what to do with it",
    }
    assert villager(v, "Greta")["triggers"] == ["given"]  # so she decides again


# --- M12 US1: the daily trader ---

MARKET_CELLS = place_cells("market")


def buy(goods: str) -> str:
    return json.dumps({"action": "buy", "goods": goods})


def tick_at(hour: int, minute: int = 0, day: int = 1) -> int:
    return ((day - 1) * 1440 + hour * 60 + minute - 270) // 10


@pytest.mark.anyio
async def test_the_trader_is_at_the_market_from_nine_to_two(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v, tick_at(8, 30))
    v.world["day_record"] = {"day": 1, "items": []}
    present: list[str] = []
    for _ in range(36):  # 08:40 to 14:30
        await v.step()
        if v.world["trader"]:
            present.append(v.state()["time"])
            assert v.state()["trader"]["leaves"] == "14:00"
        else:
            assert v.state()["trader"] is None
    assert present[0] == "09:00" and present[-1] == "13:50" and len(present) == 30
    [came] = [n for n in notes(v) if n.startswith("A trader came")]
    assert came.startswith("A trader came to the market with wood (")
    assert "The trader left the market (sold 0 loads)." in notes(v)


@pytest.mark.anyio
async def test_a_basket_buys_a_load(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina": [buy("wood")]})
    morning(v, tick_at(10))
    v.world["day_record"] = {"day": 1, "items": []}
    trader: dict[str, Any] = {"day": 1, "stock": {"wood": 2, "paint": 1, "saplings": 0}}
    v.world["trader"] = trader
    put(v, "Lina", *MARKET_CELLS[0], basket="flowers", triggers=["arrived"])
    await v.step()
    assert villager(v, "Lina")["basket"] == "wood"
    assert trader["stock"]["wood"] == 1
    assert texts(v, "Lina", "traded") == ["You traded your basket of flowers for a load of wood."]
    assert "Lina traded a basket of flowers for a load of wood." in notes(v)
    [turn] = v.store.list_turns("Lina")
    assert turn.village_action == {"action": "buy", "goods": "wood", "paid": "flowers"}
    assert v.state()["trader"] == {
        "stock": {"wood": 1, "paint": 1, "saplings": 0},
        "leaves": "14:00",
    }


@pytest.mark.anyio
async def test_no_buying_after_the_trader_left(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina": [buy("wood")]})
    morning(v, tick_at(15))
    put(v, "Lina", *MARKET_CELLS[0], basket="flowers", triggers=["arrived"])
    await v.step()
    assert villager(v, "Lina")["basket"] == "flowers"
    assert villager(v, "Lina")["last_action"] == {
        "action": "wait",
        "reason": "no trader is at the market now; one comes every day from 09:00 to 14:00",
    }


@pytest.mark.anyio
async def test_two_villagers_after_the_last_paint(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina": [buy("paint")], "Greta": [buy("paint")]})
    morning(v, tick_at(10))
    v.world["trader"] = {"day": 1, "stock": {"wood": 0, "paint": 1, "saplings": 0}}
    put(v, "Lina", *MARKET_CELLS[0], basket="flowers", triggers=["arrived"])
    put(v, "Greta", *MARKET_CELLS[1], basket="vegetables", triggers=["arrived"])
    await v.step()
    carried = sorted([villager(v, "Lina")["basket"], villager(v, "Greta")["basket"]])
    assert carried in (["paint", "vegetables"], ["flowers", "paint"])
    reasons = [villager(v, n)["last_action"].get("reason") for n in ("Lina", "Greta")]
    assert sorted(reasons, key=str) == sorted([None, "the trader has no paint left"], key=str)


@pytest.mark.anyio
async def test_a_basket_given_while_deciding_does_not_pay_the_trader(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina": [buy("wood")]}, delay=0.01)
    morning(v, tick_at(10))
    trader: dict[str, Any] = {"day": 1, "stock": {"wood": 2, "paint": 0, "saplings": 0}}
    v.world["trader"] = trader
    lina = put(v, "Lina", *MARKET_CELLS[0], basket="flowers", triggers=["arrived"])
    v._start_decisions(force=True)  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(0)  # Lina's prompt is written
    lina["basket"] = "fish"  # handed over while Lina decides
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert lina["basket"] == "fish" and trader["stock"]["wood"] == 2
    assert lina["last_action"]["action"] == "wait"


# --- M12 US2: the town hall meeting ---

TOWN_HALL = place_cells("town_hall")


def meeting_now(v: Village) -> dict[str, Any]:
    meeting = v.world["meeting"]
    assert meeting is not None
    return meeting


def actions(v: Village, name: str, kind: str) -> list[dict[str, Any]]:
    """The village actions of a villager's runs of one kind (propose, vote, decide, …)."""
    found = [t.village_action for t in v.store.list_turns(name)]
    return [a for a in found if a is not None and a["action"] == kind]


def meetings_of(llm: FakeLLM, kind: str) -> list[str]:
    """The prompts of the meeting runs of one kind, in order."""
    return [c[1]["content"] or "" for c in llm.calls if is_meeting(c) and meeting_kind(c) == kind]


def voters(llm: FakeLLM) -> list[str]:
    return [speaker(c) for c in llm.calls if is_meeting(c) and meeting_kind(c) == "vote"]


def proposed_meeting(v: Village, day: int = 3) -> dict[str, Any]:
    """Today's meeting with Hilde's two default proposals, before 17:00."""
    meeting: dict[str, Any] = {
        "day": day,
        "kind": "vote",
        "proposals": [
            {"key": "paint_town_hall", "reason": "It looks shabby.", "run_id": None},
            {"key": "market_stand", "reason": "Greta needs it.", "run_id": None},
        ],
        "votes": {},
        "present": [],
        "decision": None,
        "outcome": None,
    }
    v.world["meeting"] = meeting
    return meeting


async def steps(v: Village, n: int) -> None:
    for _ in range(n):
        await v.step()


@pytest.mark.anyio
async def test_hilde_proposes_on_a_meeting_day_only(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(9, day=2))
    await v.step()
    assert v.world["meeting"] is None and meetings_of(llm, "proposals") == []
    morning(v, tick_at(9, day=3))
    v.world["day_record"] = {"day": 3, "items": []}
    await v.step()
    meeting = meeting_now(v)
    assert meeting["day"] == 3 and meeting["kind"] == "vote" and meeting["outcome"] is None
    assert [p["key"] for p in meeting["proposals"]] == ["paint_town_hall", "market_stand"]
    assert len(meetings_of(llm, "proposals")) == 1
    proposed = texts(v, "Hilde", "proposed")
    assert proposed == [
        "You proposed for the town hall meeting: Paint the town hall (It looks shabby.); "
        "A market stand (Greta needs a place to sell.)."
    ]
    assert any(n.startswith("Hilde proposed for the town hall meeting") for n in notes(v))
    [turn] = actions(v, "Hilde", "propose")
    assert turn["proposals"][0] == "Paint the town hall: It looks shabby."
    villager(v, "Greta")["triggers"] = ["arrived"]
    await v.step()
    assert len(meetings_of(llm, "proposals")) == 1  # once a day
    assert "Hilde proposes: Paint the town hall" in calls_of(llm, "Greta")[-1]
    assert v.state()["next_meeting"] == 3


@pytest.mark.anyio
async def test_everyone_at_the_town_hall_but_hilde_votes_once(tmp_path: Path) -> None:
    v, llm = village_for(
        tmp_path,
        {
            "Greta:vote": [vote_for("a market stand", "I sell there.")],
            "Jonas:vote": [vote_for("market stand")],
        },
    )
    morning(v, tick_at(16, 50, day=3))
    v.world["day_record"] = {"day": 3, "items": []}
    proposed_meeting(v)
    for name, cell in zip(("Hilde", "Greta", "Jonas"), TOWN_HALL, strict=False):
        put(v, name, *cell)
    await steps(v, 2)  # 17:00, 17:10
    assert sorted(voters(llm)) == ["Greta", "Jonas"]
    put(v, "Lina", *TOWN_HALL[3])
    await v.step()  # 17:20: Lina arrives in time
    await v.step()  # 17:30: the decision
    assert sorted(voters(llm)) == ["Greta", "Jonas", "Lina"]
    meeting = v.world["meeting"]
    assert meeting["present"] == ["Hilde", "Jonas", "Greta", "Lina"]  # villager order
    assert meeting["votes"]["Greta"]["key"] == "market_stand"
    assert len(meetings_of(llm, "decision")) == 1
    assert "- Greta: A market stand (I sell there.)" in meetings_of(llm, "decision")[0]
    assert meeting["outcome"] == "decided" and meeting["decision"]["key"] == "paint_town_hall"
    assert v.world["project"]["key"] == "paint_town_hall"
    assert meeting["decision"]["against"] is True  # two wanted the stand
    told = texts(v, "Lina", "meeting")
    assert told[-1] == (
        "At the town hall meeting Hilde chose Paint the town hall: It is quick. She went against "
        "the vote (most wanted A market stand)."
    )
    assert told[-1] in notes(v)
    assert any(m["kind"] == "meeting" for m in villager(v, "Greta")["memories"])
    state = v.state()["meeting"]
    assert state["decision"]["name"] == "Paint the town hall"
    assert {"villager": "Greta", "key": "market_stand", "name": "A market stand"}.items() <= next(
        x for x in state["votes"] if x["villager"] == "Greta"
    ).items()


@pytest.mark.anyio
async def test_coming_after_half_past_five_is_too_late_to_vote(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(17, 20, day=3))
    proposed_meeting(v)
    put(v, "Hilde", *TOWN_HALL[0])
    await v.step()  # 17:30: Hilde decides alone
    put(v, "Lina", *TOWN_HALL[1])
    await v.step()
    assert voters(llm) == [] and v.world["meeting"]["present"] == ["Hilde"]
    assert "- nobody else came to vote" in meetings_of(llm, "decision")[0]
    assert v.world["meeting"]["decision"]["against"] is False


@pytest.mark.anyio
async def test_a_meeting_hilde_does_not_come_to_is_called_off(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(16, 50, day=3))
    v.world["day_record"] = {"day": 3, "items": []}
    proposed_meeting(v)
    put(v, "Greta", *TOWN_HALL[0])
    await steps(v, 4)  # 17:30: Hilde may still be on her way
    assert v.world["meeting"]["outcome"] is None
    put(v, "Hilde", 1, 20)  # far away, not coming
    await steps(v, 6)  # 18:30
    meeting = v.world["meeting"]
    assert meeting["outcome"] == "called off: Hilde did not come"
    assert meeting["votes"]["Greta"]["key"] == "paint_town_hall"  # the vote stays on record
    assert meetings_of(llm, "decision") == [] and v.world["project"] is None
    assert texts(v, "Greta", "meeting")[-1] == (
        "Today's town hall meeting was called off: Hilde did not come."
    )


@pytest.mark.anyio
async def test_invalid_proposals_call_the_meeting_off(tmp_path: Path) -> None:
    castle = '{"proposals": [{"project": "a castle"}]}'
    v, _ = village_for(tmp_path, {"meeting:proposals": [castle, castle]})
    morning(v, tick_at(9, day=3))
    await v.step()
    assert v.world["meeting"]["outcome"] == "called off: Hilde had no proposals"
    reasons = sorted(a["reason"] for a in actions(v, "Hilde", "propose"))
    assert reasons == [
        "no project Hilde proposed can be built",
        "no project Hilde proposed can be built; asked again",
    ]


@pytest.mark.anyio
async def test_unusable_proposals_or_work_plans_are_asked_for_once_more(tmp_path: Path) -> None:
    broken = '{"proposals": [{"project": "A market stand", "reason": "x"}]'  # no closing brace
    v, llm = village_for(
        tmp_path, {"meeting:proposals": [broken], "meeting:tasks": ['{"tasks": []}']}
    )
    morning(v, tick_at(9, day=3))
    await v.step()
    assert len(meetings_of(llm, "proposals")) == 2
    assert [p["key"] for p in meeting_now(v)["proposals"]] == ["paint_town_hall", "market_stand"]
    assert any(
        a["reason"].endswith("; asked again")
        for a in actions(v, "Hilde", "propose")
        if "reason" in a
    )
    await decide_market_stand(v)
    assert len(meetings_of(llm, "tasks")) == 2
    assert v.world["project"]["tasks"] == [{"task": "build", "goods": None, "villagers": ["Greta"]}]


@pytest.mark.anyio
async def test_an_invalid_decision_lets_the_vote_decide(tmp_path: Path) -> None:
    v, _ = village_for(
        tmp_path,
        {
            "meeting:decision": ['{"decision": "a castle"}'],
            "Greta:vote": [vote_for("A market stand")],
        },
    )
    morning(v, tick_at(16, 50, day=3))
    proposed_meeting(v)
    put(v, "Hilde", *TOWN_HALL[0])
    put(v, "Greta", *TOWN_HALL[1])
    await steps(v, 4)
    decision = v.world["meeting"]["decision"]
    assert (decision["key"], decision["by"]) == ("market_stand", "vote")
    [turn] = actions(v, "Hilde", "decide")
    assert turn["by"] == "vote"


@pytest.mark.anyio
async def test_a_meeting_with_a_project_under_way_proposes_nothing(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(9, day=3))
    v.world["project"] = new_project("barn", 2)
    villager(v, "Greta")["triggers"] = ["arrived"]
    await v.step()
    assert meeting_now(v)["kind"] == "review" and meetings_of(llm, "proposals") == []
    assert "to talk about how the building goes" in calls_of(llm, "Greta")[-1]


@pytest.mark.anyio
async def test_no_meeting_on_the_festival_day_but_the_day_after(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(9, day=21))
    await v.step()
    assert v.world["meeting"] is None and meetings_of(llm, "proposals") == []
    morning(v, tick_at(9, day=22))
    await v.step()
    assert meeting_now(v)["day"] == 22


@pytest.mark.anyio
async def test_a_failing_meeting_run_does_not_pause_the_village(tmp_path: Path) -> None:
    down = RuntimeError("model down")
    v, _ = village_for(tmp_path, {"meeting:proposals": [down, down]})
    morning(v, tick_at(9, day=3))
    for _ in range(3):
        await v.step()
    assert v.world["meeting"]["outcome"] == "called off: Hilde had no proposals"
    assert v.world["failed_ticks"] == 0


@pytest.mark.anyio
async def test_reset_waits_for_a_meeting_run(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, delay=0.05)
    morning(v, tick_at(9, day=3))
    v.world["tick"] -= 1
    stepping = asyncio.create_task(v.step())
    await asyncio.sleep(0.01)
    await stepping
    await v.reset()
    assert not v.meetings and v.world["meeting"] is None


def test_the_meeting_agent_is_created_once(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.ensure_agents()
    meeting_agents = [a for a in v.store.list_agents() if a.name == "Village meeting"]
    assert [a.agent_id for a in meeting_agents] == [v.world["meeting_agent_id"]]


# --- M12 US3: Hilde hands out the work ---


async def decide_market_stand(v: Village) -> None:
    """A meeting at 17:30 with Hilde and Greta at the town hall: the market stand is chosen."""
    morning(v, tick_at(17, 20, day=3))
    v.world["day_record"] = {"day": 3, "items": []}
    proposed_meeting(v)
    put(v, "Hilde", *TOWN_HALL[0])
    await v.step()  # 17:30: Hilde decides alone, then hands out the work


@pytest.mark.anyio
async def test_the_work_is_handed_out_after_the_decision(tmp_path: Path) -> None:
    v, llm = village_for(
        tmp_path,
        {
            "meeting:decision": [json.dumps({"decision": "A market stand", "reason": "Quick."})],
            "meeting:tasks": [
                json.dumps(
                    {
                        "tasks": [
                            {"task": "buy", "goods": "wood", "villagers": ["Jonas", "Greta"]},
                            {"task": "build", "villagers": ["Greta"]},
                        ]
                    }
                )
            ],
        },
    )
    await decide_market_stand(v)
    project = v.world["project"]
    assert project["key"] == "market_stand" and len(meetings_of(llm, "tasks")) == 1
    assert project["tasks"] == [
        {"task": "buy", "goods": "wood", "villagers": ["Jonas", "Greta"]},
        {"task": "build", "goods": None, "villagers": ["Greta"]},
    ]
    assert texts(v, "Greta", "task") == [
        "Hilde asked you to buy wood from the trader; build at the building site."
    ]
    assert "task" in villager(v, "Greta")["triggers"] and texts(v, "Lina", "task") == []
    [assign] = actions(v, "Hilde", "assign")
    assert assign["tasks"] == ["buy wood: Jonas, Greta", "build: Greta"]
    assert any(n.startswith("Hilde handed out the work") for n in notes(v))
    await v.step()  # Greta decides on her new task
    prompt = calls_of(llm, "Greta")[-1]
    assert "The village is building: A market stand (the building site is at the market)." in (
        prompt
    )
    assert "Hilde asked you to: buy wood from the trader; build at the building site." in prompt
    lina = observation(v.world, "Lina")
    assert "Nothing is asked of you; you may still help." in lina
    assert "Hilde asked you to: buy wood from the trader." in plan_prompt(v.world, "Jonas")
    state = v.state()["project"]
    assert (state["name"], state["done"], state["total"]) == ("A market stand", 0, 4)
    assert state["needs"] == {"wood": 3, "paint": 1} and state["tasks"] == project["tasks"]


@pytest.mark.anyio
async def test_an_invalid_work_plan_leaves_the_project_without_tasks(tmp_path: Path) -> None:
    dance = '{"tasks": [{"task": "dance"}]}'
    v, _ = village_for(tmp_path, {"meeting:tasks": [dance, dance]})
    await decide_market_stand(v)
    assert v.world["project"]["tasks"] == []
    assert sorted(a["reason"] for a in actions(v, "Hilde", "assign")) == [
        "no usable task in the work plan",
        "no usable task in the work plan; asked again",
    ]


@pytest.mark.anyio
async def test_a_review_meeting_hands_out_the_work_again(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(17, 20, day=6))
    project = {
        "key": "barn",
        "site": {"wood": 0, "paint": 0, "saplings": 0},
        "used": {"wood": 4, "paint": 0, "saplings": 0},
        "work": 0,
        "tasks": [{"task": "buy", "goods": "wood", "villagers": ["Lina"]}],
        "day": 3,
    }
    v.world["project"] = project
    v.world["meeting"] = {
        "day": 6,
        "kind": "review",
        "proposals": [],
        "votes": {},
        "present": [],
        "decision": None,
        "outcome": None,
    }
    put(v, "Hilde", *TOWN_HALL[0])
    await v.step()
    assert "4 of 19 loads worked in" in meetings_of(llm, "tasks")[0]
    assert "- buy wood from the trader: Lina" in meetings_of(llm, "tasks")[0]
    assert project["tasks"] == [{"task": "build", "goods": None, "villagers": ["Greta"]}]
    assert meeting_now(v)["outcome"] == "reviewed"


@pytest.mark.anyio
async def test_stored_planners_get_the_new_plan_text_unless_edited(tmp_path: Path) -> None:
    from agent_lab.village.plan import OLD_PLANS, PLAN

    v, _ = village_for(tmp_path)
    agent = v.store.get_agent(v.world["planner_agent_id"])
    assert agent is not None and "what Hilde asked of the villager" in PLAN

    def store(system: str) -> None:
        blocks = agent.config["blocks"]
        v.store.update_agent(
            agent.agent_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config={**agent.config, "blocks": [{**blocks[0], "system": system}, *blocks[1:]]},
        )

    def system() -> str:
        found = v.store.get_agent(agent.agent_id)
        assert found is not None
        return found.config["blocks"][0]["system"]

    store(OLD_PLANS[0])
    Village(store=v.store, models=v.models, bus=Bus())
    assert system() == PLAN
    store("MY OWN PLANNER")
    Village(store=v.store, models=v.models, bus=Bus())
    assert system() == "MY OWN PLANNER"


# --- M12 US4: building and seeing it stay ---


@pytest.mark.anyio
async def test_from_meeting_to_a_finished_project_that_stays(tmp_path: Path) -> None:
    """SC-002: decided, handed out, bought, brought, built, and still there the next day."""
    v, _ = village_for(
        tmp_path,
        {
            "Lina:vote": [vote_for("Paint the town hall")],
            "Lina": [buy("paint"), move("building site"), give(), WORK],
        },
    )
    morning(v, tick_at(17, 20, day=3))
    v.world["day_record"] = {"day": 3, "items": []}
    proposed_meeting(v)
    put(v, "Hilde", *TOWN_HALL[0], neighbours=["Lina"])
    put(v, "Lina", *TOWN_HALL[1], neighbours=["Hilde"])  # no "met": nobody decides yet
    await steps(v, 2)  # 17:30 Lina votes; 17:40 Hilde decides and hands out the work
    project = v.world["project"]
    assert project["key"] == "paint_town_hall" and project["tasks"]
    # the next morning Lina trades fish for paint at the market and paints with Hilde's help
    morning(v, tick_at(10, day=4))
    v.world["day_record"] = {"day": 4, "items": []}
    v.world["trader"] = {"day": 4, "stock": {"wood": 0, "paint": 2, "saplings": 0}}
    lina = put(v, "Lina", *MARKET_CELLS[0], basket="fish", triggers=["arrived"])
    await v.step()
    assert lina["basket"] == "paint"
    lina["triggers"] = ["spoken to"]
    for _ in range(12):  # walk to the town hall
        await v.step()
        if lina["goal"] is None:
            break
    assert place_at(lina["x"], lina["y"]) == "town_hall"
    lina["triggers"] = ["arrived"]
    await v.step()  # sets the paint down
    assert lina["basket"] is None and project["site"]["paint"] == 1
    assert texts(v, "Lina", "gave")[-1] == "You set down a load of paint at the building site."
    project["site"]["paint"] += 1  # a second load from someone else
    lina["triggers"] = ["arrived"]
    await v.step()  # works
    assert lina["working"]["place"] == "site"
    for _ in range(14):
        await v.step()
        if v.world["project"] is None:
            break
    assert v.world["project"] is None
    assert [b["key"] for b in v.world["built"]] == ["paint_town_hall"]
    assert lina["working"] is None
    assert texts(v, "Greta", "built") == ["The town hall has been painted."]
    assert any(m["kind"] == "built" for m in lina["memories"])
    assert "The town hall has been painted." in notes(v)
    v.world["tick"] = tick_at(4, 20, day=5) - 1
    await v.step()  # a new day
    built = v.state()["built"]
    assert built == [
        {"key": "paint_town_hall", "name": "Paint the town hall", "kind": "paint", "day": 4}
    ]


@pytest.mark.anyio
async def test_a_load_the_site_does_not_need_is_kept(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Lina": [give()]})
    morning(v)
    v.world["project"] = new_project("market_stand", 1)
    lina = put(v, "Lina", *MARKET_CELLS[0], basket="saplings", triggers=["arrived"])
    await v.step()
    assert lina["basket"] == "saplings"
    assert lina["last_action"]["reason"] == "the building site does not need saplings"


@pytest.mark.anyio
async def test_the_building_goes_on_the_next_day(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    project = new_project("barn", 1)
    project["site"]["wood"] = 3
    project["used"]["wood"] = 5
    v.world["project"] = project
    v.world["tick"] = tick_at(4, 20, day=2) - 1
    await v.step()
    assert v.world["project"] is project and project["site"]["wood"] == 3
    assert project["used"]["wood"] == 5


def test_the_chronicle_and_the_map_know_what_is_built(tmp_path: Path) -> None:
    from agent_lab.village.chronicle import chronicle_prompt

    v, _ = village_for(tmp_path)
    v.world["built"] = [{"key": "boat", "day": 2}]
    record: dict[str, Any] = {"day": 3, "items": []}
    assert "Built so far: A rowing boat lies at the pier." in chronicle_prompt(v.world, record)
    catalogue = v.state()["map"]["catalogue"]
    boat = next(c for c in catalogue if c["key"] == "boat")
    assert boat == {
        "key": "boat",
        "name": "A rowing boat",
        "kind": "boat",
        "site": [[16, 16], [17, 16], [18, 16]],
        "at": [[20, 17]],
    }


@pytest.mark.anyio
async def test_a_review_meeting_after_the_project_was_finished_ends_quietly(
    tmp_path: Path,
) -> None:
    v, llm = village_for(tmp_path)
    morning(v, tick_at(17, 20, day=6))
    v.world["meeting"] = {
        "day": 6,
        "kind": "review",  # opened in the morning, while the project was still under way
        "proposals": [],
        "votes": {},
        "present": [],
        "decision": None,
        "outcome": None,
    }
    put(v, "Hilde", *TOWN_HALL[0])
    await v.step()  # 17:30, the project finished earlier today
    assert meeting_now(v)["outcome"] == "reviewed" and meetings_of(llm, "tasks") == []


def test_meeting_answers_count_only_on_their_day(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.world["tick"] = tick_at(17, 30, day=3)
    meeting = proposed_meeting(v)
    assert v._still(meeting)  # pyright: ignore[reportPrivateUsage]
    v.world["tick"] = tick_at(5, day=4)  # a slow answer, the next morning
    assert not v._still(meeting)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.anyio
async def test_at_half_past_four_everyone_away_is_called_to_the_meeting_once(
    tmp_path: Path,
) -> None:
    v, _ = village_for(tmp_path)
    morning(v, tick_at(16, 20, day=3))
    proposed_meeting(v)
    put(v, "Jonas", 1, 1)
    put(v, "Lina", *TOWN_HALL[1])  # already there
    await steps(v, 2)  # 16:30 and 16:40
    called = (
        "The town hall meeting starts at 17:00: go to the town hall now to vote "
        '({"action": "move", "place": "town hall"}).'  # M14: talking, it says goodbye and goes
    )
    assert texts(v, "Jonas", "meeting") == [called] and texts(v, "Greta", "meeting") == [called]
    assert texts(v, "Hilde", "meeting") == [
        "Your town hall meeting starts at 17:00: go to the town hall now to chair it "
        '({"action": "move", "place": "town hall"}).'
    ]
    assert texts(v, "Lina", "meeting") == []  # already there


@pytest.mark.anyio
async def test_the_meeting_waits_for_hilde_until_half_past_six(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Greta:vote": [vote_for("A market stand")]})
    morning(v, tick_at(17, 20, day=3))
    proposed_meeting(v)
    put(v, "Greta", *TOWN_HALL[1])
    await steps(v, 3)  # 17:50, no Hilde yet
    assert v.world["meeting"]["outcome"] is None and meetings_of(llm, "decision") == []
    put(v, "Hilde", *TOWN_HALL[0])  # she arrives late
    put(v, "Lina", *TOWN_HALL[2])  # and so does Lina, in time to vote
    await steps(v, 2)
    meeting = meeting_now(v)
    assert meeting["outcome"] == "decided" and sorted(meeting["votes"]) == ["Greta", "Lina"]


@pytest.mark.anyio
async def test_no_vote_starts_once_hilde_decides(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, delay=0.05)
    v.world["running"] = True  # decisions run in the background, as in the real loop
    morning(v, tick_at(17, 40, day=3))
    meeting = proposed_meeting(v)
    meeting["present"] = ["Hilde"]
    put(v, "Hilde", *TOWN_HALL[0])
    v._meeting()  # pyright: ignore[reportPrivateUsage]
    assert "decide" in v.meetings
    put(v, "Lina", *TOWN_HALL[1])  # arrives while Hilde decides
    v._meeting()  # pyright: ignore[reportPrivateUsage]
    assert "vote:Lina" not in v.meetings and "Lina" in meeting["present"]
    v.world["running"] = False
    await v._settle()  # pyright: ignore[reportPrivateUsage]
    assert voters(llm) == [] and meeting["outcome"] == "decided"


@pytest.mark.anyio
async def test_talking_does_not_hold_up_the_walk_to_the_meeting(tmp_path: Path) -> None:
    """M14: one rule instead of the meeting's special case. Set on going, she walks on while
    talking; Lina, with a goal but set on nothing, stays."""
    v, _ = village_for(tmp_path)
    morning(v, tick_at(16, 40, day=3))
    proposed_meeting(v)
    sx, sy = place_cells("square")[0]
    hilde = put(v, "Hilde", sx, sy, goal={"kind": "place", "place": "town_hall"})
    hilde["intention"] = start(v.world, "Hilde", {"action": "move", "place": "town_hall"})
    lina = put(v, "Lina", sx + 1, sy, goal={"kind": "place", "place": "market"})
    v.world["conversations"] = [
        {"a": "Hilde", "b": "Lina", "lines": 2, "last_tick": v.world["tick"], "transcript": []}
    ]
    before = steps_to(sx, sy, TOWN_HALL)
    await v.step()
    assert steps_to(hilde["x"], hilde["y"], TOWN_HALL) < before  # on her way
    assert (lina["x"], lina["y"]) == (sx + 1, sy)  # Lina stays
    assert v.world["conversations"] == []  # they walked apart


# --- M13: the day trail ---


@pytest.mark.anyio
async def test_every_step_leaves_a_trail_row(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v, tick_at(10, day=2))
    v.world["project"] = new_project("market_stand", 1)
    v.world["project"]["used"]["wood"] = 2
    put(v, "Lina", *MARKET_CELLS[0], basket="wood", working={"place": "site", "steps": 0})
    await v.step()
    [(tick, row)] = v.store.trail(0, 10**6)
    assert tick == v.world["tick"]
    assert row["project"] == "market_stand" and row["used"] == 2
    lina = next(r for r in row["v"] if r[0] == "Lina")
    assert lina == ["Lina", *MARKET_CELLS[0], "market", "working", "wood"]
    hilde = next(r for r in row["v"] if r[0] == "Hilde")
    assert hilde[4] == "idle" and hilde[5] is None


@pytest.mark.anyio
async def test_the_trail_keeps_28_days_and_reset_clears_it(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.store.add_trail(5, {"v": []})
    v.store.add_trail(30 * 144, {"v": []})
    for x in v.world["villagers"]:
        x["asleep"] = True
    v.world["tick"] = tick_at(4, 50, day=31)
    await v.step()  # 05:00: Jonas wakes, the day record opens
    ticks = [t for t, _ in v.store.trail(0, 10**6)]
    assert 5 not in ticks and 30 * 144 in ticks  # older than 28 days: pruned
    v.world["born"] = 1.0  # long ago: a Reset starts the count again from now
    await v.reset()
    assert v.store.trail(0, 10**6) == [] and v.world["born"] > 1.0
    assert "born" not in v.state()


@pytest.mark.anyio
async def test_a_prompt_that_cannot_be_built_is_a_failed_turn_not_a_hang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(world: dict[str, Any], name: str) -> str:
        raise KeyError("saplings")

    v, _ = village_for(tmp_path)
    morning(v)
    villager(v, "Lina")["triggers"] = ["arrived"]
    monkeypatch.setattr(runner, "observation", broken)
    await asyncio.wait_for(v.step(), timeout=5)  # Step settles: no decision may stay in flight
    assert not v.decisions
    action = villager(v, "Lina")["last_action"]
    assert action["action"] == "wait"
    assert action["reason"] == "turn failed: could not build the prompt: KeyError: 'saplings'"
    await asyncio.wait_for(v.reset(), timeout=5)


# --- M14 US1: intentions (FR-001 to FR-003) ---

BUILD = json.dumps({"action": "build"})


def building_site(v: Village, **site: int) -> None:
    v.world["project"] = new_project("trees_square", 1)
    v.world["project"]["site"] |= site


@pytest.mark.anyio
async def test_one_build_answer_keeps_greta_building_without_more_calls(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Greta": [BUILD]})
    morning(v)
    v.world["day_record"] = {"day": 1, "items": []}
    building_site(v, saplings=2)
    put(v, "Greta", *place_cells("fields")[0], triggers=["woke"])
    await v.step()
    greta = villager(v, "Greta")
    assert greta["intention"]["kind"] == "build" and greta["goal"] == {
        "kind": "place",
        "place": "site",
    }
    [turn] = v.store.list_turns("Greta")
    assert turn.village_action is not None
    assert turn.village_action["intention"]["kind"] == "build"
    assert "Greta set out to build at the building site." in notes(v)
    while not (greta["working"] and greta["working"]["place"] == "site"):
        await v.step()  # walks there and starts building, asked nothing on arrival
    assert len(calls_of(llm, "Greta")) == 1
    while greta["intention"]:
        await v.step()  # builds both saplings in
    assert v.world["project"] is None or v.world["project"]["used"]["saplings"] == 2
    assert texts(v, "Greta", "intention_ended")
    assert len(calls_of(llm, "Greta")) == 2  # asked again only once it ended


@pytest.mark.anyio
async def test_work_until_a_time_ends_then_and_asks_again(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Greta": [json.dumps({"action": "work", "until": "10:00"})]})
    morning(v)
    put(v, "Greta", *place_cells("fields")[0], triggers=["arrived"])
    await v.step()  # 09:40
    greta = villager(v, "Greta")
    assert greta["working"] == {"place": "fields", "steps": 0}
    assert greta["intention"]["until"] == 600
    await v.step()  # 09:50: no idle question while set on work
    assert len(calls_of(llm, "Greta")) == 1
    await v.step()  # 10:00: done, and asked what next
    assert greta["intention"] is None and greta["working"] is None
    assert texts(v, "Greta", "intention_ended") == [
        "You are done with: work at the fields until 10:00: it is 10:00."
    ]
    assert len(calls_of(llm, "Greta")) == 2


@pytest.mark.anyio
async def test_bring_sets_the_load_down_on_arrival(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Jonas": [json.dumps({"action": "bring"})]})
    morning(v)
    building_site(v)
    put(v, "Jonas", *place_cells("market")[0], basket="saplings", triggers=["woke"])
    for _ in range(6):
        await v.step()
    jonas = villager(v, "Jonas")
    assert jonas["basket"] is None and jonas["intention"] is None
    assert v.world["project"]["site"]["saplings"] == 1
    assert texts(v, "Jonas", "intention_ended")[-1].endswith(": you set down the saplings.")


@pytest.mark.anyio
async def test_see_with_a_line_says_it_on_arrival(tmp_path: Path) -> None:
    seek = json.dumps({"action": "find", "villager": "Lina", "say": "Flowers for the hall?"})
    v, _ = village_for(tmp_path, {"Hilde": [seek]})
    morning(v)
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, triggers=["woke"])
    put(v, "Lina", sx + 5, sy + 2)
    for _ in range(3):
        await v.step()
    assert villager(v, "Hilde")["intention"] is None
    assert texts(v, "Lina", "heard") == ['Hilde said to you: "Flowers for the hall?"']


@pytest.mark.anyio
async def test_a_new_intention_replaces_the_old_one(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [WORK, move("market")]})
    morning(v)
    put(v, "Greta", *place_cells("fields")[0], triggers=["arrived"])
    await v.step()
    greta = villager(v, "Greta")
    greta["triggers"] = ["spoken to"]
    await v.step()
    assert greta["intention"]["kind"] == "go" and greta["working"] is None
    assert texts(v, "Greta", "intention_ended") == [
        "You are done with: work at the fields: you chose to go to the market."
    ]


@pytest.mark.anyio
async def test_finishing_the_project_and_bedtime_end_intentions(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    v.world["project"] = new_project("trees_square", 1)
    v.world["project"] |= {"site": {"wood": 0, "paint": 0, "saplings": 1}}
    v.world["project"]["used"]["saplings"] = 2
    v.world["project"]["work"] = 5
    put(v, "Greta", 18, 10, working={"place": "site", "steps": 0})
    villager(v, "Greta")["intention"] = start(v.world, "Greta", {"action": "build"})
    await v.step()
    assert v.world["project"] is None and villager(v, "Greta")["intention"] is None
    assert texts(v, "Greta", "intention_ended")[-1].endswith(": it is finished.")
    lina = put(v, "Lina", *place_cells("square")[0])
    lina["intention"] = start(v.world, "Lina", {"action": "move", "place": "market"})
    v.world["tick"] = bedtime_tick("Lina", minutes_before=0) - 1
    await v.step()
    assert lina["bedtime"] and lina["intention"] is None
    assert texts(v, "Lina", "intention_ended")[-1].endswith(": the day is over.")


# --- M14 US2: reaching each other (FR-005, FR-006) ---


@pytest.mark.anyio
async def test_a_find_follows_someone_walking_on_and_ends_next_to_them(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [find("Lina")]})
    morning(v)
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, triggers=["woke"])
    put(v, "Lina", sx + 5, sy, goal={"kind": "place", "place": "market"})
    for _ in range(8):
        await v.step()
        if villager(v, "Hilde")["intention"] is None:
            break
    hilde, lina = villager(v, "Hilde"), villager(v, "Lina")
    assert hilde["intention"] is None
    assert max(abs(hilde["x"] - lina["x"]), abs(hilde["y"] - lina["y"])) <= 1
    assert texts(v, "Hilde", "intention_ended") == ["You are done with: see Lina: you found Lina."]


@pytest.mark.anyio
async def test_a_find_ends_when_the_one_followed_goes_out_of_sight(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [find("Lina")]})
    morning(v)
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, triggers=["woke"])
    put(v, "Lina", sx + 6, sy)
    await v.step()
    hilde = villager(v, "Hilde")
    assert hilde["intention"]["seen"]
    put(v, "Lina", *place_cells("pier")[0])  # gone out of sight at once
    await v.step()
    assert hilde["intention"] is None
    assert texts(v, "Hilde", "intention_ended")[-1].startswith(
        "You are done with: see Lina: you lost sight of Lina"
    )


@pytest.mark.anyio
async def test_a_line_naming_goods_is_a_request_the_hearer_may_give_to(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [say("Any fish for the hall, Jonas?", "Jonas")]})
    morning(v)
    sx, sy = label_cell("square")
    put(v, "Hilde", sx, sy, triggers=["met"], neighbours=["Jonas"])
    put(v, "Jonas", sx + 1, sy, basket="fish", neighbours=["Hilde"])
    await v.step()
    jonas = villager(v, "Jonas")
    assert jonas["requests"] == [{"from": "Hilde", "goods": "fish", "tick": MORNING + 1}]
    assert parse_action(give("Hilde"), v.world, "Jonas")[1] is None


# --- M14 US3: leaving a talk (FR-009, FR-010) ---


@pytest.mark.anyio
async def test_a_move_while_talking_leaves_with_a_goodbye(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Jonas": [move("pier")]})
    neighbours_at_market(v)
    talk(v, "Hilde", "Jonas", 2)
    villager(v, "Jonas")["triggers"] = ["spoken to"]
    await v.step()
    jonas = villager(v, "Jonas")
    assert jonas["last_action"]["action"] == "goodbye" and "reason" not in jonas["last_action"]
    assert jonas["intention"]["kind"] == "go" and jonas["intention"]["place"] == "pier"
    assert v.world["conversations"] == []
    [turn] = v.store.list_turns("Jonas")
    assert turn.village_action is not None and turn.village_action["intention"]["place"] == "pier"


@pytest.mark.anyio
async def test_two_talkers_going_to_the_same_place_walk_on_together(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v)
    sx, sy = label_cell("square")
    for name, x in (("Hilde", sx), ("Lina", sx + 1)):
        x_ = put(v, name, x, sy)
        x_["intention"] = start(v.world, name, {"action": "move", "place": "market"})
    c = talk(v, "Hilde", "Lina", 2)
    for _ in range(2):
        c["last_tick"] = v.world["tick"]  # they keep talking
        await v.step()
    hilde, lina = villager(v, "Hilde"), villager(v, "Lina")
    assert (hilde["x"], hilde["y"]) != (sx, sy)  # walking
    assert max(abs(hilde["x"] - lina["x"]), abs(hilde["y"] - lina["y"])) <= 1
    assert len(v.world["conversations"]) == 1  # and still talking


# --- M14 US4: summaries (FR-012) ---


@pytest.mark.anyio
async def test_a_night_reflection_folds_older_reflections_into_a_summary(tmp_path: Path) -> None:
    folded = json.dumps({"learnings": ["Jonas fishes early."], "summary": "A busy spring."})
    v, _ = village_for(tmp_path, {"Jonas:reflect": [folded]})
    morning(v, tick=144 * 10 + bedtime_tick("Jonas"))  # day 11, at his door at bedtime
    jonas = villager(v, "Jonas")
    for day in range(1, 7):
        remember(jonas, day * 144, "reflection", f"Looked back on day {day}.", [], None)
    remember(jonas, 144 * 9 + 100, "reflection", "Looked back on day 10.", [], None)
    remember(jonas, v.world["tick"], "conversation", "Talked with Lina.", ["Lina"], None)
    await v.step()
    assert jonas["asleep"]
    kinds_texts = [(m["kind"], m["text"]) for m in jonas["memories"]]
    assert ("summary", "Looking back on earlier days: A busy spring.") in kinds_texts
    assert not any(t.startswith("Looked back on day 1.") for _, t in kinds_texts)
    assert ("reflection", "Looked back on day 10.") in kinds_texts  # recent ones stay
    assert kinds_texts[-1][0] == "reflection"  # tonight's


@pytest.mark.anyio
async def test_stored_reflection_agents_get_the_summary_text_unless_edited(tmp_path: Path) -> None:
    from agent_lab.village.memory import OLD_REFLECT, REFLECT

    v, _ = village_for(tmp_path)
    agent = v.store.get_agent(v.world["reflection_agent_id"])
    assert agent is not None

    def store(system: str) -> None:
        blocks = agent.config["blocks"]
        v.store.update_agent(
            agent.agent_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config={**agent.config, "blocks": [{**blocks[0], "system": system}, *blocks[1:]]},
        )

    def system() -> str:
        found = v.store.get_agent(agent.agent_id)
        assert found is not None
        return found.config["blocks"][0]["system"]

    store(OLD_REFLECT[0])
    Village(store=v.store, models=v.models, bus=Bus())
    assert system() == REFLECT
    store("MY OWN REFLECTION")
    Village(store=v.store, models=v.models, bus=Bus())
    assert system() == "MY OWN REFLECTION"


@pytest.mark.anyio
async def test_stored_villager_agents_get_the_new_persona_unless_edited(tmp_path: Path) -> None:
    from agent_lab.village.world import OLD_PERSONAS

    v, _ = village_for(tmp_path)
    old = system_of(v, "Hilde").replace(VILLAGERS["Hilde"].persona, OLD_PERSONAS["Hilde"][0])
    set_system(v, "Hilde", old)
    set_system(v, "Jonas", "MY OWN JONAS")
    Village(store=v.store, models=v.models, bus=Bus())
    assert system_of(v, "Hilde").startswith(VILLAGERS["Hilde"].persona)
    assert "harvest festival" not in system_of(v, "Hilde")
    assert system_of(v, "Jonas") == "MY OWN JONAS"


# --- M15: world version 8 (FR-015) ---


@pytest.mark.anyio
async def test_a_version_7_world_keeps_going(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    world = v.store.load_village()
    assert world is not None
    for x in world["villagers"]:
        del x["keepsakes"], x["whispers"]
    del world["happenings"], world["boat"], world["harvest"]["lake"]
    world |= {"version": 7, "tick": 144 * 20 + 30}
    v.store.save_village(world)
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert (reloaded.world["version"], reloaded.world["tick"]) == (8, 144 * 20 + 30)
    reloaded.world["running"] = False
    await reloaded.step()


@pytest.mark.anyio
async def test_reset_clears_happenings_the_boat_keepsakes_and_whispers(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    v.world |= {"happenings": [{"kind": "peddler"}], "boat": {"rowers": ["Jonas"]}}
    villager(v, "Lina")["keepsakes"] = [{"name": "a lantern", "day": 1}]
    villager(v, "Lina")["whispers"] = [{"text": "Hi", "tick": 0, "heard": None}]
    await v.reset()
    assert v.world["happenings"] == [] and v.world["boat"] is None
    assert villager(v, "Lina")["keepsakes"] == villager(v, "Lina")["whispers"] == []


def test_the_state_gives_keepsakes_and_leaves_out_whispers() -> None:
    v, _ = village_for(":memory:")
    villager(v, "Lina")["keepsakes"] = [{"name": "a lantern", "day": 1}]
    villager(v, "Lina")["whispers"] = [{"text": "psst", "tick": 0, "heard": 0}]
    state = {x["name"]: x for x in v.state()["villagers"]}
    assert state["Lina"]["keepsakes"] == [{"name": "a lantern", "day": 1}]
    assert all("whispers" not in x for x in state.values())
    assert v.state()["boat"] is None and v.state()["happenings"] == []
