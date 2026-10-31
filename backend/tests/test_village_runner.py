"""Ticks, actions applied together, speech, storage, controls and self-pauses (US1, US2)."""

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
from agent_lab.village.runner import StepConflict, Village
from agent_lab.village.world import PLACES, VILLAGERS, label_cell, place_at, steps_between, walkable

WAIT = '{"action": "wait"}'


def move(place: str) -> str:
    return json.dumps({"action": "move", "place": place})


def say(text: str, to: str | None = None) -> str:
    return json.dumps({"action": "say", "text": text, "to": to})


def speaker(messages: list[Message]) -> str:
    system = messages[0]["content"] or ""
    return next(n for n in VILLAGERS if f"You are {n}," in system)


def responder(
    plan: dict[str, list[str | Exception]],
) -> Callable[[list[Message]], ChatResponse | Exception]:
    """Answers each villager from its own list (then waits), whatever order the turns run in."""
    queues = {n: list(a) for n, a in plan.items()}

    def respond(messages: list[Message]) -> ChatResponse | Exception:
        queue = queues.get(speaker(messages)) or []
        item = queue.pop(0) if queue else WAIT
        return item if isinstance(item, Exception) else answer(item)

    return respond


def village_for(
    db: Path | str, plan: dict[str, list[str | Exception]], ticks: int, delay: float = 0, **kw: Any
) -> tuple[Village, FakeLLM]:
    script: list[ScriptItem] = [responder(plan)] * (4 * ticks)
    llm = FakeLLM(script, delay=delay)
    store = Store(db if db == ":memory:" else Path(db) / "lab.db")
    return Village(store=store, models=fake_models(llm), bus=Bus(), **kw), llm


def villager(v: Village, name: str) -> dict[str, Any]:
    return next(x for x in v.world["villagers"] if x["name"] == name)


def place_villager(v: Village, name: str, place: str, dx: int = 0) -> None:
    x, y = label_cell(place)
    villager(v, name).update(x=x + dx, y=y)


def calls_of(llm: FakeLLM, name: str) -> list[str]:
    return [c[1]["content"] or "" for c in llm.calls if speaker(c) == name]


@pytest.mark.anyio
async def test_three_ticks_move_talk_and_store(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [move("square")] * 3, "Lina": [say("Good morning!")]}, 3)
    v.ensure_agents()
    start = (villager(v, "Hilde")["x"], villager(v, "Hilde")["y"])
    for _ in range(3):
        await v.tick()
    hilde = villager(v, "Hilde")
    assert v.world["tick"] == 3 and v.state()["time"] == "06:30"
    assert abs(hilde["x"] - start[0]) + abs(hilde["y"] - start[1]) == 3
    assert hilde["destination"] == "square"  # still on the way
    assert villager(v, "Lina")["speech"] is None  # speech shows for its own tick only
    assert any(e["kind"] == "said" for e in villager(v, "Lina")["events"])
    # Setting off is remembered once, not on every step of the walk.
    assert [e["text"] for e in hilde["events"]] == ["You set off for the square."]
    stored = v.store.load_village()
    assert stored is not None and stored["tick"] == 3


@pytest.mark.anyio
async def test_actions_apply_together(tmp_path: Path) -> None:
    v, llm = village_for(tmp_path, {"Hilde": [say("Hello Jonas", "Jonas")]}, 2)
    v.ensure_agents()
    place_villager(v, "Hilde", "market")
    place_villager(v, "Jonas", "market", dx=1)
    await v.tick()
    assert "Hello Jonas" not in calls_of(llm, "Jonas")[0]  # same tick: not heard yet
    await v.tick()
    assert '- Hilde to you: "Hello Jonas"' in calls_of(llm, "Jonas")[1]


@pytest.mark.anyio
async def test_speech_reaches_nearby_villagers_only(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [say("Fish for the festival?", "Jonas")]}, 1)
    v.ensure_agents()
    place_villager(v, "Hilde", "market")
    place_villager(v, "Jonas", "market", dx=1)
    place_villager(v, "Lina", "market", dx=2)
    await v.tick()
    assert villager(v, "Hilde")["speech"] == {"text": "Fish for the festival?", "to": "Jonas"}
    assert villager(v, "Jonas")["inbox"] == [
        {"from": "Hilde", "to": "Jonas", "text": "Fish for the festival?", "tick": 0}
    ]
    assert villager(v, "Lina")["inbox"][0]["to"] == "Jonas"  # overheard, marked for Jonas
    assert villager(v, "Greta")["inbox"] == []  # in the fields
    assert villager(v, "Jonas")["events"][-1]["text"] == 'Hilde to you: "Fish for the festival?"'


@pytest.mark.anyio
async def test_long_speech_is_cut(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [say("x" * 500)]}, 1)
    v.ensure_agents()
    await v.tick()
    assert len(villager(v, "Hilde")["speech"]["text"]) == 200


@pytest.mark.anyio
async def test_reload_is_paused_and_reset_starts_over(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [move("market")]}, 1)
    v.ensure_agents()
    v.world["running"] = True
    await v.tick()
    reloaded = Village(store=v.store, models=v.models, bus=Bus())
    assert reloaded.world["tick"] == 1 and reloaded.world["running"] is False
    assert reloaded.world["villagers"] == v.world["villagers"]
    await reloaded.reset()
    assert reloaded.world["tick"] == 0
    assert place_at(villager(reloaded, "Greta")["x"], villager(reloaded, "Greta")["y"]) == "fields"
    assert villager(reloaded, "Greta")["agent_id"] == villager(v, "Greta")["agent_id"]


@pytest.mark.anyio
async def test_hundred_ticks_stay_on_walkable_cells() -> None:
    places = list(PLACES)  # each villager heads somewhere new every 7 ticks, often mid-walk
    plan: dict[str, list[str | Exception]] = {
        n: [move(places[(i // 7 + k) % len(places)]) for i in range(100)]
        for k, n in enumerate(VILLAGERS)
    }
    v, _ = village_for(":memory:", plan, 100)  # 400 runs: no disk writes
    v.ensure_agents()
    for _ in range(100):
        before = {x["name"]: (x["x"], x["y"]) for x in v.world["villagers"]}
        await v.tick()
        for x in v.world["villagers"]:
            bx, by = before[x["name"]]
            assert walkable(x["x"], x["y"]) and abs(x["x"] - bx) + abs(x["y"] - by) <= 1
    assert v.world["tick"] == 100


@pytest.mark.anyio
async def test_pauses_after_three_failed_ticks(tmp_path: Path) -> None:
    down = RuntimeError("model down")
    v, _ = village_for(tmp_path, {n: [down] * 3 for n in VILLAGERS}, 3)
    v.world["interval"] = 0
    v.viewer_joined()
    v.start()
    assert v.task is not None
    await asyncio.wait_for(v.task, 5)
    assert (v.world["running"], v.world["tick"]) == (False, 3)
    assert v.world["paused_reason"] == "every turn failed 3 ticks in a row"
    assert villager(v, "Hilde")["last_action"]["reason"].startswith("turn failed")


@pytest.mark.anyio
async def test_pauses_without_a_viewer(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {}, 50, idle_pause=0.1)
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
async def test_steps_never_overlap(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {}, 2, delay=0.05)
    v.ensure_agents()
    results = await asyncio.gather(v.step(), v.step(), return_exceptions=True)
    assert sum(isinstance(r, StepConflict) for r in results) == 1
    assert v.world["tick"] == 1


@pytest.mark.anyio
async def test_reset_waits_for_the_tick(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Hilde": [move("square")]}, 1, delay=0.05)
    v.ensure_agents()
    step = asyncio.create_task(v.step())
    await asyncio.sleep(0.01)
    assert v.state()["ticking"]
    await v.reset()
    await step
    assert v.world["tick"] == 0  # the reset came after the tick, not in the middle of it
    assert villager(v, "Hilde")["destination"] is None


@pytest.mark.anyio
async def test_a_long_walk_ends_with_one_arrival(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {"Greta": [move("square")]}, 12)
    v.ensure_agents()
    greta = villager(v, "Greta")
    steps = steps_between(greta["x"], greta["y"], "square")
    for _ in range(steps):
        await v.tick()
    assert place_at(greta["x"], greta["y"]) == "square" and greta["destination"] is None
    kinds = [e["kind"] for e in greta["events"]]
    assert kinds.count("set_off") == 1 and kinds.count("arrived") == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("no json here", "turn failed"),  # the agent's JSON check fails the run
        ('{"action": "dance"}', "not a valid action"),
        ('{"action": "move", "place": "harbour"}', "unknown place 'harbour'"),
        ('{"action": "say", "text": " "}', "nothing to say"),
        ('{"action": "say", "text": "Hi", "to": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "move", "place": "pier"}', "already at the pier"),
        (RuntimeError("model down"), "turn failed"),
    ],
)
async def test_invalid_answers_wait_with_the_reason_recorded(
    tmp_path: Path, answer: str | Exception, reason: str
) -> None:
    v, _ = village_for(tmp_path, {"Jonas": [answer]}, 1)
    v.ensure_agents()
    jonas = villager(v, "Jonas")
    before = (jonas["x"], jonas["y"])
    await v.tick()
    assert (jonas["x"], jonas["y"]) == before
    assert jonas["last_action"]["action"] == "wait" and jonas["last_action"]["reason"].startswith(
        reason
    )
    assert jonas["events"][-1]["kind"] == "waited" and reason in jonas["events"][-1]["text"]
    [turn] = v.store.list_turns("Jonas")
    assert turn.village_action is not None and turn.village_action["reason"].startswith(reason)


API_KEY = "sk-village-0123456789abcdefghij"


@pytest.mark.anyio
async def test_escaped_secret_is_redacted_after_decoding(tmp_path: Path) -> None:
    escaped = "\\u0073" + API_KEY[1:]  # survives redaction of the raw answer, decodes to the secret
    answer = '{"action": "say", "text": "my key is ' + escaped + '"}'
    v, _ = village_for(tmp_path, {"Hilde": [answer]}, 1, secrets=(API_KEY,))
    v.ensure_agents()
    await v.tick()
    hilde = villager(v, "Hilde")
    assert hilde["speech"] is not None and "[REDACTED]" in hilde["speech"]["text"]
    stored = json.dumps(v.store.load_village())
    [turn] = v.store.list_turns("Hilde")
    assert API_KEY not in stored and API_KEY not in json.dumps(turn.village_action)


@pytest.mark.anyio
async def test_agent_names_beyond_the_first_fallback(tmp_path: Path) -> None:
    v, _ = village_for(tmp_path, {}, 1)
    for name in ("Mayor Hilde", "Mayor Hilde (village)"):
        v.store.create_agent(
            template_id="blocks", name=name, description="", sample_prompt="x", config={}
        )
    v.ensure_agents()
    hilde = villager(v, "Hilde")
    agent = v.store.get_agent(hilde["agent_id"])
    assert agent is not None and agent.name == "Mayor Hilde (village 2)"
