import time
from pathlib import Path

from agent_lab.agents.react import build_graph
from agent_lab.store import Run, RunTotals, Store
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
