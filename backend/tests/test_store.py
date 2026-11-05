import sqlite3
import time
from pathlib import Path

import pytest

from agent_lab.agents.react import build_graph
from agent_lab.store import CustomAgent, NameInUse, Run, RunTotals, Store
from agent_lab.tracing.span import Span, SpanKind


def make_run(run_id: str, started_at: float) -> Run:
    return Run(
        run_id=run_id,
        agent_id="react",
        config_version="v1",
        prompt="hi",
        status="running",
        graph=build_graph(["calculator"]),
        config={"model": "m"},
        started_at=started_at,
    )


def make_span(span_id: str, ended_at: float | None) -> Span:
    return Span(
        trace_id="t",
        span_id=span_id,
        parent_span_id=None,
        run_id="r1",
        agent_id="react",
        node_id="llm",
        config_version="v1",
        kind=SpanKind.LLM,
        name="chat m",
        input=[{"role": "user", "content": "hi"}],
        output={"role": "assistant", "content": "yo"},
        started_at=1.0,
        ended_at=ended_at,
        tokens_in=3,
        tokens_out=1,
        model="m",
        attributes={"gen_ai.request.model": "m"},
    )


def test_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "lab.db"
    store = Store(path)
    run = make_run("r1", time.time())
    store.create_run(run)
    store.save_span(make_span("s1", None))
    store.save_span(make_span("s1", 2.0))  # the end event replaces the start event
    store.finish_run("r1", "completed", "yo", 3.0)
    store.close()

    reopened = Store(path)
    assert reopened.get_spans("r1") == [make_span("s1", 2.0)]
    stored = reopened.get_run("r1")
    assert stored is not None
    assert (stored.status, stored.answer, stored.ended_at) == ("completed", "yo", 3.0)
    assert stored.graph == run.graph
    assert reopened.get_run("nope") is None


def test_list_runs_newest_first(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("old", 1.0))
    store.create_run(make_run("new", 2.0))
    assert [r.run_id for r in store.list_runs()] == ["new", "old"]


def test_totals(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("r1", 1.0))
    store.save_span(make_span("s1", 2.0))
    store.save_span(make_span("s2", 2.0).model_copy(update={"tokens_out": None}))
    tool = make_span("s3", 2.0).model_copy(
        update={"kind": SpanKind.TOOL, "tokens_in": None, "tokens_out": None}
    )
    store.save_span(tool)
    store.save_span(make_span("s4", 2.0).model_copy(update={"kind": SpanKind.STEP}))
    store.finish_run("r1", "completed", "yo", 3.5)

    totals = RunTotals(llm_calls=2, tool_calls=1, tokens_in=9, tokens_out=2, wall_ms=2500)
    stored = store.get_run("r1")
    assert stored is not None and stored.totals == totals
    assert [r.totals for r in store.list_runs()] == [totals]


def test_totals_running_wall_null(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("r1", 1.0))
    stored = store.get_run("r1")
    assert stored is not None
    assert stored.totals == RunTotals(
        llm_calls=0, tool_calls=0, tokens_in=0, tokens_out=0, wall_ms=None
    )


def test_m1_run_still_lists(tmp_path: Path) -> None:
    """A run stored by M1: config without `reasoning`, spans without `lab.came_from`."""
    path = tmp_path / "lab.db"
    store = Store(path)
    m1 = make_run("r1", 1.0).model_copy(
        update={"config": {"model": "m", "tools": ["calculator"], "max_iterations": 6}}
    )
    store.create_run(m1)
    store.save_span(make_span("s1", 2.0))
    store.finish_run("r1", "completed", "yo", 2.0)
    store.close()

    reopened = Store(path)
    [listed] = reopened.list_runs()
    assert (listed.run_id, listed.agent_id, listed.config) == ("r1", "react", m1.config)
    assert listed.totals is not None and listed.totals.llm_calls == 1
    assert reopened.get_spans("r1") == [make_span("s1", 2.0)]


M2_RUNS_TABLE = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, config_version TEXT NOT NULL,
    prompt TEXT NOT NULL, status TEXT NOT NULL, answer TEXT, graph TEXT NOT NULL,
    config TEXT NOT NULL, started_at REAL NOT NULL, ended_at REAL
);
"""


def test_migrates_m2_database(tmp_path: Path) -> None:
    path = tmp_path / "lab.db"
    db = sqlite3.connect(path)
    db.executescript(M2_RUNS_TABLE)
    graph = build_graph(["calculator"]).model_dump_json()
    db.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("r1", "chain", "v1", "hi", "completed", "yo", graph, '{"model": "m"}', 1.0, 2.0),
    )
    db.commit()
    db.close()

    store = Store(path)
    [old] = store.list_runs()
    assert (old.run_id, old.agent_name, old.template_id) == ("r1", None, None)
    assert (old.village_tick, old.villager, old.village_action) == (None, None, None)
    new = make_run("r2", 3.0).model_copy(update={"agent_name": "Mine", "template_id": "react"})
    store.create_run(new)
    stored = store.get_run("r2")
    assert stored is not None and stored.model_copy(update={"totals": None}) == new


def test_agent_crud(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    agent = store.create_agent(
        template_id="routing", name="Mine", description="d", sample_prompt="p", config={"a": 1}
    )
    assert agent.agent_id.startswith("custom-") and len(agent.agent_id) == len("custom-") + 12
    assert store.get_agent(agent.agent_id) == agent
    updated = store.update_agent(
        agent.agent_id, name="Mine 2", description="", sample_prompt="q", config={"a": 2}
    )
    assert updated is not None and store.get_agent(agent.agent_id) == updated
    assert (updated.template_id, updated.created_at) == ("routing", agent.created_at)
    assert (
        store.update_agent("custom-missing", name="x", description="", sample_prompt="p", config={})
        is None
    )
    assert [a.name for a in store.list_agents()] == ["Mine 2"]
    assert store.delete_agent(agent.agent_id) and store.get_agent(agent.agent_id) is None
    assert not store.delete_agent(agent.agent_id)


def test_name_unique_ignoring_case_and_spaces(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")

    def add(name: str) -> CustomAgent:
        return store.create_agent(
            template_id="chain", name=name, description="", sample_prompt="p", config={}
        )

    def rename(agent: CustomAgent, name: str) -> CustomAgent | None:
        return store.update_agent(
            agent.agent_id, name=name, description="", sample_prompt="p", config={}
        )

    first = add("Mine")
    with pytest.raises(NameInUse):
        add("  mINE ")
    other = add("Other")
    with pytest.raises(NameInUse):
        rename(other, "mine")
    assert rename(first, "MINE") is not None  # its own name in another case is fine


def test_village_turns_are_listed_per_villager(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("normal", 1.0))
    turn = make_run("turn", 2.0).model_copy(update={"village_tick": 7, "villager": "Jonas"})
    store.create_run(turn)
    store.set_village_action("turn", {"action": "wait", "reason": "unknown place 'harbour'"})

    assert [r.run_id for r in store.list_runs()] == ["normal"]  # turns stay out of the main list
    [listed] = store.list_turns("Jonas")
    assert (listed.village_tick, listed.villager) == (7, "Jonas")
    assert listed.village_action == {"action": "wait", "reason": "unknown place 'harbour'"}
    assert store.list_turns("Lina") == []
    normal = store.get_run("normal")
    assert normal is not None and normal.village_action is None


def test_village_state_round_trips(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    assert store.load_village() is None
    store.save_village({"tick": 1})
    store.save_village({"tick": 2, "villagers": []})
    assert Store(tmp_path / "lab.db").load_village() == {"tick": 2, "villagers": []}


def test_eval_runs_stay_out_of_the_lists(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("normal", 1.0))
    store.create_run(make_run("check", 2.0).model_copy(update={"eval_id": "r1"}))
    turn = make_run("turn", 3.0).model_copy(update={"village_tick": 7, "villager": "Jonas"})
    store.create_run(turn)
    check_turn = turn.model_copy(update={"run_id": "check-turn", "eval_id": "r1"})
    store.create_run(check_turn)
    assert [r.run_id for r in store.list_runs()] == ["normal"]
    assert [r.run_id for r in store.list_turns("Jonas")] == ["turn"]
    found = store.get_run("check-turn")
    assert found is not None and found.eval_id == "r1"


def test_the_day_trail(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    for tick in (10, 11, 12, 300):
        store.add_trail(tick, {"v": [], "tick": tick})
    store.add_trail(11, {"v": [], "tick": 11, "again": True})  # a restarted tick
    assert [t for t, _ in store.trail(10, 12)] == [10, 11, 12]
    assert store.trail(11, 11)[0][1]["again"] is True
    store.prune_trail(before_tick=12)
    assert [t for t, _ in store.trail(0, 1000)] == [12, 300]
    store.clear_trail()
    assert store.trail(0, 1000) == []


def test_village_runs_reads_the_small_columns(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    for run_id, started, tick, villager, eval_id in [
        ("old", 1.0, 5, "Jonas", None),
        ("a", 10.0, 5, "Jonas", None),
        ("b", 11.0, 9, "Lina", None),
        ("late", 12.0, 50, "Lina", None),
        ("check", 13.0, 6, "Greta", "r1"),
    ]:
        run = make_run(run_id, started).model_copy(
            update={"village_tick": tick, "villager": villager, "eval_id": eval_id}
        )
        store.create_run(run)
    store.set_village_action("a", {"action": "wait", "reason": "x"})
    rows = store.village_runs(0, 10, since=5.0)
    assert [r["run_id"] for r in rows] == ["a", "b"]
    assert rows[0] == {
        "run_id": "a",
        "villager": "Jonas",
        "village_tick": 5,
        "status": "running",
        "village_action": {"action": "wait", "reason": "x"},
        "started_at": 10.0,
    }


def test_the_prompt_of_a_days_chronicle(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    for run_id, started, day, status in [
        ("c1", 1.0, 3, "completed"),
        ("c2", 2.0, 3, "completed"),
        ("c3", 3.0, 4, "error"),
    ]:
        run = make_run(run_id, started).model_copy(
            update={"prompt": f"prompt {run_id}", "status": status, "village_tick": 400}
        )
        store.create_run(run)
        store.set_village_action(run_id, {"action": "chronicle", "day": day, "title": "t"})
    assert store.chronicle_prompt_of(3, since=0) == "prompt c2"  # the newest one counts
    assert store.chronicle_prompt_of(4, since=0) is None  # failed
    assert store.chronicle_prompt_of(3, since=5.0) is None


def test_a_run_keeps_its_reason_and_harness(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    run = make_run("r1", 1.0)
    run.harness = {"budget": None, "ask_first": ["notes/write_note"], "default_budget": False}
    store.create_run(run)
    store.finish_run("r1", "over_budget", "so far", 2.0, stop_reason="model calls: 3 of 3")
    stored = store.get_run("r1")
    assert stored is not None
    assert stored.status == "over_budget"
    assert stored.answer == "so far"
    assert stored.stop_reason == "model calls: 3 of 3"
    assert stored.harness == run.harness


def test_a_status_change_keeps_the_run_open(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("r1", 1.0))
    store.set_run_status("r1", "waiting_approval")
    stored = store.get_run("r1")
    assert stored is not None
    assert stored.status == "waiting_approval"
    assert stored.ended_at is None


def test_an_agent_keeps_its_harness_apart_from_its_config(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    fields = {"template_id": "react", "description": "", "sample_prompt": "hi", "config": {"a": 1}}
    plain = store.create_agent(name="plain", **fields)
    harnessed = store.create_agent(name="limited", harness={"ask_first": ["x/y"]}, **fields)
    assert plain.harness is None
    got = store.get_agent(harnessed.agent_id)
    assert got is not None
    assert got.harness == {"ask_first": ["x/y"]}
    assert got.config == {"a": 1}
    store.update_agent(
        harnessed.agent_id,
        name="limited",
        description="",
        sample_prompt="hi",
        config={"a": 2},
        harness=None,
    )
    updated = store.get_agent(harnessed.agent_id)
    assert updated is not None
    assert updated.harness is None
    assert updated.config == {"a": 2}


def test_a_database_from_before_m17_opens_and_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    Store(path).close()
    db = sqlite3.connect(path)
    db.execute("ALTER TABLE runs DROP COLUMN harness")
    db.execute("ALTER TABLE runs DROP COLUMN stop_reason")
    db.execute("ALTER TABLE agents DROP COLUMN harness")
    db.execute(
        "INSERT INTO runs (run_id, agent_id, config_version, prompt, status, graph, config,"
        " started_at) VALUES ('old', 'react', 'v', 'hi', 'completed', ?, '{}', 1.0)",
        (build_graph([]).model_dump_json(),),
    )
    db.execute(
        "INSERT INTO agents (agent_id, template_id, name, name_key, description, sample_prompt,"
        " config, created_at, updated_at) VALUES ('a', 'react', 'A', 'a', '', 'hi', '{}', 1, 1)"
    )
    db.commit()
    db.close()

    store = Store(path)
    run = store.get_run("old")
    assert run is not None
    assert run.stop_reason is None
    assert run.harness is None
    agent = store.get_agent("a")
    assert agent is not None
    assert agent.harness is None


def test_a_restart_interrupts_live_lab_runs_only(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    store.create_run(make_run("running", 1.0))
    store.create_run(make_run("waiting", 1.0))
    store.set_run_status("waiting", "waiting_approval")
    store.create_run(make_run("done", 1.0))
    store.finish_run("done", "completed", "yo", 2.0)
    turn = make_run("turn", 1.0)
    turn.village_tick = 7
    store.create_run(turn)

    assert sorted(store.mark_interrupted()) == ["running", "waiting"]

    statuses = {r: store.get_run(r) for r in ("running", "waiting", "done", "turn")}
    assert {k: v.status for k, v in statuses.items() if v} == {
        "running": "interrupted",
        "waiting": "interrupted",
        "done": "completed",
        "turn": "running",
    }
    interrupted = statuses["running"]
    assert interrupted is not None
    assert interrupted.ended_at is not None
