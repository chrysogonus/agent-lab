"""Steps, sleep, staggered moves, decisions on triggers, meetings, conversations, searching,
beliefs, storage and controls (US1 to US4)."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from helpers import answer, fake_models

from agent_lab.bus import Bus
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.store import Store
from agent_lab.village import runner
from agent_lab.village.runner import CHANNEL, FRESH_START, StepConflict, Village
from agent_lab.village.turn import villager_agent
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
MORNING = 30  # tick of 09:30: everyone is awake


def move(place: str) -> str:
    return json.dumps({"action": "move", "place": place})


def say(text: str, to: str | None = None) -> str:
    return json.dumps({"action": "say", "text": text, "to": to})


def find(name: str) -> str:
    return json.dumps({"action": "find", "villager": name})


def speaker(messages: list[Message]) -> str:
    system = messages[0]["content"] or ""
    return next(n for n in VILLAGERS if f"You are {n}," in system)


def responder(
    plan: dict[str, list[str | Exception]],
) -> Callable[[list[Message]], ChatResponse | Exception]:
    """Answers each villager from its own list (then waits), whatever order decisions run in."""
    queues = {n: list(a) for n, a in plan.items()}

    def respond(messages: list[Message]) -> ChatResponse | Exception:
        queue = queues.get(speaker(messages)) or []
        item = queue.pop(0) if queue else WAIT
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
    return [c[1]["content"] or "" for c in llm.calls if speaker(c) == name]


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
    assert kinds(v, "Jonas")[-1] == "slept" and calls_of(llm, "Jonas") == []


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
    assert v.world["version"] == 2 and v.world["tick"] == 0
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
    for _ in range(distance - 1):
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
            moved_in_order += changed
            before = now
        assert sorted(moved_in_order) == ["Greta", "Hilde", "Jonas"]
        first_movers.append(moved_in_order[0])
    assert len(set(first_movers)) > 1  # the order rotates


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
            assert walkable(x["x"], x["y"]) and abs(x["x"] - bx) + abs(x["y"] - by) <= 1
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
        {"a": "Hilde", "b": "Jonas", "lines": 1, "last_tick": MORNING + 1}
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

    v2, _ = village_for(":memory:", {"Hilde": [say("Hi")], "Jonas": [move("pier")]})
    neighbours_at_market(v2)
    villager(v2, "Hilde")["triggers"] = ["met"]
    for _ in range(3):
        await v2.step()
    assert v2.world["conversations"] == []
    assert any("Jonas walked away" in e["text"] for e in villager(v2, "Hilde")["events"])


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
    assert "- Lina: at the square (heard from Hilde at 09:40)" in calls_of(llm, "Jonas")[0]


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
