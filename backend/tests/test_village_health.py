"""Village health per day, counted by hand from scripted runs, notes and trail (FR-001, FR-002,
SC-001)."""

import json
import time
from pathlib import Path
from typing import Any

import pytest

from agent_lab.agents.react import build_graph
from agent_lab.store import Run, Store
from agent_lab.village.health import day_health, reason_template
from agent_lab.village.health_view import day_ticks, days_health
from agent_lab.village.world import door, new_world, place_cells

DAY = 3


def tick(hour: int, minute: int = 0, day: int = DAY) -> int:
    return ((day - 1) * 1440 + hour * 60 + minute - 270) // 10


def run(
    who: str | None,
    at: int,
    action: dict[str, Any] | None,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "run_id": f"{who}-{at}-{id(action)}",
        "villager": who,
        "village_tick": at,
        "status": status,
        "village_action": action,
        "started_at": 1.0,
    }


def wait(reason: str | None = None) -> dict[str, Any]:
    return {"action": "wait", **({"reason": reason} if reason else {})}


def row(
    *villagers: tuple[str, int, int, str | None, str, str | None],
    project: str | None = None,
    used: int = 0,
) -> dict[str, Any]:
    return {"v": [list(v) for v in villagers], "project": project, "used": used}


MARKET = place_cells("market")[0]
PIER = place_cells("pier")[0]


def test_reason_templates() -> None:
    assert reason_template("Hilde is not next to you") == "<villager> is not next to you"
    assert reason_template("unknown villager 'Hilde'") == "unknown villager '<villager>'"
    assert reason_template("Greta's hands are full") == "<villager>'s hands are full"
    assert reason_template("the trader has no paint left") == "the trader has no <goods> left"
    assert reason_template("you are talking with Hilde and Jonas; say goodbye first") == (
        "you are talking with <villager> and <villager>; say goodbye first"
    )


def test_decisions_waits_refusals_and_calls() -> None:
    runs = [
        run("Hilde", tick(9), {"action": "move", "place": "market"}),
        run("Hilde", tick(9, 30), wait()),
        run("Jonas", tick(9), wait("Hilde is not next to you")),
        run("Jonas", tick(10), wait("Greta is not next to you")),
        run("Lina", tick(10), wait("you already said that")),
        run("Lina", tick(11), wait("turn failed: run ended error"), status="error"),
        run("Greta", tick(7), {"action": "plan", "revision": 0, "entries": []}),
        run("Greta", tick(23), {"action": "reflect", "learnings": []}),
        run("Hilde", tick(8), {"action": "propose", "proposals": ["x"]}),
        run(None, tick(1, day=DAY + 1), {"action": "chronicle", "day": DAY, "title": "t"}),
    ]
    health = day_health(DAY, runs, [], [], None, final=True)
    assert health is not None
    assert (health["decisions"], health["waits"], health["failed_calls"]) == (5, 4, 1)
    assert health["refusals"] == [
        {"reason": "<villager> is not next to you", "count": 2},
        {"reason": "you already said that", "count": 1},
    ]
    assert health["repeated_lines"] == 1
    assert health["calls"] == {"decision": 6, "plan": 1, "reflect": 1, "chronicle": 1, "meeting": 1}


def test_conversations_from_the_notes() -> None:
    notes = [
        "Jonas and Lina talked; what they said (their claims): Jonas: Hi / Lina: Hello / "
        "Jonas: Bye",
        "Greta and Hilde talked; what they said (their claims): Greta: Rain?",
        "Lina set off for the market.",
    ]
    health = day_health(DAY, [run("Lina", tick(9), wait())], notes, [], None, final=True)
    assert health is not None
    assert health["conversations"] == {"count": 2, "lines": [3, 1], "median_lines": 2.0}


def test_plan_adherence_needs_the_trail() -> None:
    plan = {
        "action": "plan",
        "revision": 0,
        "entries": ["09:00 market: sell", "11:00 see Greta: talk", "12:00 pier: fish"],
    }
    runs = [run("Lina", tick(6, 30), plan), run("Lina", tick(9), wait())]
    trail = [
        (tick(9, 20), row(("Lina", *MARKET, "market", "idle", None))),  # kept: at the market
        (
            tick(11, 30),
            row(("Lina", 5, 5, None, "walking", None), ("Greta", 6, 6, None, "idle", None)),
        ),  # kept: next to Greta
        (tick(13, 30), row(("Lina", *PIER, "pier", "idle", None))),  # too late for 12:00
    ]
    health = day_health(DAY, runs, [], trail, None, final=True)
    assert health is not None and health["plan_adherence"] == {"kept": 2, "entries": 3}
    no_trail = day_health(DAY, runs, [], [], None, final=True)
    assert no_trail is not None and no_trail["plan_adherence"] is None
    assert no_trail["stuck_hours"] is None and no_trail["loads_worked_in"] is None


def test_a_revised_plan_replaces_the_entries_still_to_come() -> None:
    first = {"action": "plan", "revision": 0, "entries": ["09:00 market: a", "15:00 pier: b"]}
    revised = {"action": "plan", "revision": 1, "entries": ["09:00 market: a", "16:00 home: c"]}
    runs = [run("Lina", tick(6, 30), first), run("Lina", tick(12), revised)]
    trail = [
        (tick(9), row(("Lina", *MARKET, "market", "idle", None))),
        (tick(16), row(("Lina", *door("Lina"), None, "idle", None))),
        (tick(18), row(("Lina", *door("Lina"), None, "idle", None))),  # 16:00's hour is over
    ]
    health = day_health(DAY, runs, [], trail, None, final=True)
    # the 09:00 entry from the first plan, the 16:00 one from the revision; 15:00 was replaced
    assert health is not None and health["plan_adherence"] == {"kept": 2, "entries": 2}


def test_the_meeting_the_trades_and_the_loads() -> None:
    runs = [
        run("Hilde", tick(8), {"action": "propose", "proposals": ["x", "y"]}),
        run("Greta", tick(17), {"action": "vote", "project": "A market stand", "reason": "r"}),
        run("Lina", tick(17), {"action": "vote", "reason": "not valid"}),
        run(
            "Hilde",
            tick(17, 40),
            {
                "action": "decide",
                "project": "A market stand",
                "reason": "r",
                "against": False,
                "by": "hilde",
            },
        ),
        run("Lina", tick(10), {"action": "buy", "goods": "wood", "paid": "flowers"}),
        run("Lina", tick(10, 40), {"action": "give", "to": None, "goods": "wood"}),
        run("Greta", tick(11), {"action": "buy", "goods": "paint", "paid": "fish"}),
        run("Greta", tick(11, 20), {"action": "give", "to": None, "goods": "paint"}),
        run("Greta", tick(12), wait("the trader has no wood left")),
    ]
    notes = ["Hilde came to the town hall meeting.", "Greta came to the town hall meeting."]
    trail = [
        (tick(12), row(project="market_stand", used=0)),
        (tick(13), row(project="market_stand", used=1)),
        (tick(14), row(project="market_stand", used=3)),
        (tick(15), row(project=None, used=0)),  # the last load worked in: finished
    ]
    health = day_health(DAY, runs, notes, trail, None, final=True)
    assert health is not None
    assert health["meeting"] == {
        "present": ["Hilde", "Greta"],
        "votes": 1,
        "outcome": "decided: A market stand",
    }
    assert (health["trades"], health["loads_set_down"], health["loads_worked_in"]) == (2, 2, 4)
    assert health["load_minutes"] == 30  # 40 and 20 minutes


def test_baskets_given_straight_back() -> None:
    runs = [
        run("Hilde", tick(9), {"action": "give", "to": "Greta", "goods": "fish"}),
        run("Greta", tick(9, 10), {"action": "give", "to": "Hilde", "goods": "fish"}),
        run("Lina", tick(9), {"action": "give", "to": "Jonas", "goods": "flowers"}),
        run("Jonas", tick(10), wait("Lina just gave you this basket; set it out …")),
    ]
    health = day_health(DAY, runs, [], [], None, final=True)
    assert health is not None and health["given_back"] == 2


def test_weather_slips_and_stuck_hours() -> None:
    entry = {"day": DAY, "title": "A storm", "text": "Thunder rolled over the snow."}
    still = ("Jonas", 9, 9, None, "idle", None)
    trail = [(tick(10) + i, row(still)) for i in range(9)]  # 90 minutes in one place
    trail += [(tick(12) + i, row(("Jonas", 9, 9, None, "working", None))) for i in range(9)]
    health = day_health(DAY, [run("Jonas", tick(10), wait())], [], trail, entry, final=True)
    assert health is not None
    assert health["stuck_hours"] == 1.5  # working for 90 minutes is not stuck
    assert health["weather_slips"] is not None and "storm" in health["weather_slips"]
    unwritten = day_health(DAY, [run("Jonas", tick(10), wait())], [], [], None, final=False)
    assert unwritten is not None and unwritten["weather_slips"] is None
    assert unwritten["final"] is False and unwritten["trail"] is False


def test_a_day_without_runs_has_no_health() -> None:
    assert day_health(DAY, [], ["a note"], [], None, final=True) is None


@pytest.mark.parametrize("kind", ["meeting", "trades"])
def test_numbers_without_a_source_on_a_quiet_day(kind: str) -> None:
    health = day_health(DAY, [run("Lina", tick(9), wait())], [], [], None, final=True)
    assert health is not None
    assert health["meeting"] is None and health["trades"] == 0  # counted from runs: zero is real
    assert kind in health


# --- health of the recent days, from a store and the world ---


def stored(
    store: Store,
    who: str | None,
    at: int,
    action: dict[str, Any],
    *,
    started: float = 5.0,
    prompt: str = "p",
) -> str:
    run_id = f"{who}-{at}-{len(store.village_runs(0, 10**6, 0))}"
    store.create_run(
        Run(
            run_id=run_id,
            agent_id="a",
            config_version="v",
            prompt=prompt,
            status="completed",
            graph=build_graph([]),
            config={},
            started_at=started,
            village_tick=at,
            villager=who,
        )
    )
    store.set_village_action(run_id, action)
    return run_id


def a_world(today: int, **changes: Any) -> dict[str, Any]:
    world: dict[str, Any] = new_world()
    clock_and_birth: dict[str, Any] = {"tick": tick(10, day=today), "born": 1.0, "chronicle": []}
    return world | clock_and_birth | changes


def test_days_health_from_runs_notes_and_the_trail(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    stored(store, "Lina", tick(9, day=2), wait("Hilde is not next to you"))
    stored(store, "Lina", tick(9, day=2), wait(), started=0.5)  # before `born`: not counted
    chronicle_prompt = (
        "Day 2 (…). Sunny.\nWhat happened (…):\n"
        "- 09:10 Jonas and Lina talked; what they said (their claims): Jonas: Hi / Lina: Hey\n"
        "- 10:00 Lina set off for the market.\nWrite the chronicle entry for this day."
    )
    stored(
        store,
        None,
        tick(1, day=3),
        {"action": "chronicle", "day": 2, "title": "t"},
        prompt=chronicle_prompt,
    )
    stored(store, "Greta", tick(9, day=3), {"action": "move", "place": "market"})
    store.add_trail(tick(9, day=3), row(("Greta", 1, 1, None, "walking", None)))
    entry = {"day": 2, "title": "Rain", "text": "It rained all day."}  # day 2's weather
    record = {
        "day": 3,
        "items": [
            {
                "tick": tick(9, day=3),
                "text": "Greta and Hilde talked; what they said (their claims): Greta: Hi",
            }
        ],
    }
    world = a_world(3, chronicle=[entry], day_record=record)
    today, yesterday = days_health(store, world, days=14)
    assert (today["day"], today["final"], today["trail"]) == (3, False, True)
    assert today["conversations"]["count"] == 1 and today["calls"]["chronicle"] == 0
    assert (yesterday["day"], yesterday["final"], yesterday["trail"]) == (2, True, False)
    assert yesterday["decisions"] == 1  # the run before `born` is left out
    assert yesterday["conversations"]["lines"] == [2]  # from the chronicle prompt
    assert yesterday["calls"]["chronicle"] == 1  # its chronicle, though written after midnight
    assert yesterday["weather_slips"] == [] and yesterday["plan_adherence"] is None


def test_days_health_is_quick_on_many_runs(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    rows: list[tuple[str, int, str]] = []
    for i in range(3000):
        at = 144 + i * 27 * 144 // 3000  # spread over days 2 to 28
        rows.append((f"r{i}", at, json.dumps(wait("Hilde is not next to you"))))
    with store._lock:  # pyright: ignore[reportPrivateUsage]
        store._db.executemany(  # pyright: ignore[reportPrivateUsage]
            "INSERT INTO runs (run_id, agent_id, config_version, prompt, status, graph, config,"
            " started_at, village_tick, villager, village_action)"
            " VALUES (?, 'a', 'v', 'p', 'completed', '{}', '{}', 5.0, ?, 'Lina', ?)",
            rows,
        )
    world = a_world(28)
    started = time.monotonic()
    found = days_health(store, world, days=28)
    assert time.monotonic() - started < 2.0 and len(found) == 27


def test_a_day_runs_from_midnight_to_midnight(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    stored(store, "Lina", tick(23, 50, day=1), wait("x"))  # day 1, 23:50
    stored(store, "Lina", tick(0, 30, day=2), wait("y"))  # day 2, 00:30: before the clock's 04:30
    store.add_trail(tick(0, 30, day=2), row(("Lina", 1, 1, None, "idle", None)))
    assert day_ticks(1) == (0, 116) and day_ticks(2) == (117, 260)
    today, yesterday = days_health(store, a_world(2), days=2)
    assert [r["reason"] for r in today["refusals"]] == ["y"] and today["trail"] is True
    assert [r["reason"] for r in yesterday["refusals"]] == ["x"] and yesterday["trail"] is False


def test_loads_set_down_by_an_intention_count_from_notes_and_trail() -> None:
    """M14: a bring sets the load down on arrival, without a give answer."""
    runs = [
        run("Lina", tick(10), {"action": "buy", "goods": "saplings", "paid": "flowers"}),
        run("Lina", tick(10, 10), {"action": "bring"}),
    ]
    notes = ["Lina set down a load of saplings at the building site."]
    lina = ("Lina", 18, 10)
    trail = [
        (tick(10, 10), row((*lina, None, "walking", "saplings"))),
        (tick(10, 40), row((*lina, None, "walking", "saplings"))),
        (tick(10, 50), row((*lina, None, "idle", None))),
    ]
    health = day_health(DAY, runs, notes, trail, None, final=True)
    assert health is not None
    assert (health["loads_set_down"], health["load_minutes"]) == (1, 50)
    assert health["decisions"] == 2  # bring is a decision


def test_happenings_boat_trips_and_whispers() -> None:
    """M15 (FR-012, FR-013): counted from the day's notes and the decisions."""
    notes = [
        "A goat wandered to the market.",  # an animal's start is a "wandered to the" note
        "Greta's goat wandered to the market.",
        "Jonas led Greta's goat home.",
        "A peddler came to the square with a kite.",
        "The peddler left the square; nobody traded for a kite.",
        "Jonas and Greta rowed out on the lake.",
        "Jonas and Greta came back to the pier.",
        "A voice whispered to Lina.",
        "A voice whispered to Lina.",
    ]
    runs = [
        run("Lina", tick(10), {"action": "move", "place": "market", "after_whisper": True}),
        run("Lina", tick(11), {"action": "wait", "after_whisper": True}),
    ]
    health = day_health(DAY, runs, notes, [], None, final=True)
    assert health is not None
    assert health["happenings"] == {"count": 3, "dealt": 1}
    assert health["boat_trips"] == 1
    assert health["whispers"] == {"count": 2, "followed": 1}
