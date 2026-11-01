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
from agent_lab.village.runner import CELLS_PER_STEP, CHANNEL, FRESH_START, StepConflict, Village
from agent_lab.village.seasons import weather
from agent_lab.village.turn import SPEECH_SHOWN, villager_agent
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


def speaker(messages: list[Message]) -> str:
    """The villager a call is for: its persona opens the system prompt of a decision and the
    prompt of a reflection or a plan."""
    text = messages[1 if is_reflection(messages) or is_plan(messages) else 0]["content"] or ""
    return next(n for n in VILLAGERS if f"You are {n}," in text)


def responder(
    plan: dict[str, list[str | Exception]],
) -> Callable[[list[Message]], ChatResponse | Exception]:
    """Answers each villager from its own list (then waits), whatever order decisions run in;
    reflections come from the list "<name>:reflect" (then an empty reflection), plans from
    "<name>:plan" (then A_PLAN), chronicles from "chronicle" (then a quiet day)."""
    queues = {n: list(a) for n, a in plan.items()}

    def respond(messages: list[Message]) -> ChatResponse | Exception:
        if is_chronicle(messages):
            queue = queues.get("chronicle") or []
            item = queue.pop(0) if queue else QUIET_DAY
            return item if isinstance(item, Exception) else answer(item)
        if is_plan(messages):
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
    **kw: Any,
) -> tuple[Village, FakeLLM]:
    script: list[ScriptItem] = [responder(plan or {})] * calls
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
        if not is_chronicle(c) and not is_reflection(c) and not is_plan(c) and speaker(c) == name
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
    assert v.world["version"] == 5 and v.world["tick"] == 0
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
    for _ in range(2):  # Hilde says hi; Jonas tries to walk off and may not
        await v2.step()
    assert jonas["last_action"] == {
        "action": "wait",
        "reason": "you are talking with Hilde; say goodbye first",
    }
    assert (jonas["x"], jonas["y"]) == jonas_at and len(v2.world["conversations"]) == 1
    jonas["triggers"] = ["spoken to"]
    await v2.step()  # Jonas says goodbye and leaves for the pier
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
    assert (reloaded.world["version"], reloaded.world["tick"]) == (5, 40)
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


@pytest.mark.anyio
async def test_stored_agents_get_the_new_rules_unless_edited(tmp_path: Path) -> None:
    from agent_lab.village.turn import OLD_RULES, RULES

    m7, m9 = OLD_RULES
    v, _ = village_for(tmp_path)
    ids = {x["name"]: x["agent_id"] for x in v.world["villagers"]}
    for name, old in (("Hilde", m7), ("Greta", m9), ("Jonas", "MY OWN RULES")):
        agent = v.store.get_agent(ids[name])
        assert agent is not None
        blocks = agent.config["blocks"]
        system = blocks[0]["system"].replace(RULES, old)
        v.store.update_agent(
            agent.agent_id,
            name=agent.name,
            description=agent.description,
            sample_prompt=agent.sample_prompt,
            config={**agent.config, "blocks": [{**blocks[0], "system": system}, *blocks[1:]]},
        )
    Village(store=v.store, models=v.models, bus=Bus())  # loading refreshes the rules
    systems: dict[str, str] = {}
    for name in ("Hilde", "Greta", "Jonas", "Lina"):
        agent = v.store.get_agent(ids[name])
        assert agent is not None
        systems[name] = agent.config["blocks"][0]["system"]
    for name in ("Hilde", "Greta", "Lina"):  # Lina was created with the new rules
        assert systems[name].endswith(RULES) and systems[name].count(RULES) == 1
        assert all(old not in systems[name] for old in OLD_RULES)
    assert systems["Jonas"].endswith("MY OWN RULES")  # the owner's edit stays
    assert "Trust what you see over what you hear" in RULES
    assert "Follow your plan for the day" in RULES


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
    assert (reloaded.world["version"], reloaded.world["tick"]) == (5, 144 * 9 + 30)
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
    assert "Greta set off for the market." in chronicles_of(llm)[0]
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
async def test_awake_villagers_on_the_fields_and_garden_count_as_tending(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path)
    morning(v, tick=6)  # 05:30: Lina sleeps until 06:30
    fx, fy = place_cells("fields")[0]
    gx, gy = place_cells("flower_garden")[0]
    put(v, "Greta", fx, fy)
    put(v, "Jonas", fx + 1, fy)  # two on the fields still count once per step
    put(v, "Lina", gx, gy, asleep=True)  # asleep: no help
    await v.step()
    await v.step()
    assert v.world["tended"] == {"fields": 2, "flower_garden": 0}


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
    assert memory["text"] == "The harvest festival on the square with Lina."
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
    assert (reloaded.world["version"], reloaded.world["tick"]) == (5, 144 * 20 + 30)
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
    assert "Jonas's plan for the day: 05:00 pier: Catch fish" in json.dumps(v.world["day_record"])
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
