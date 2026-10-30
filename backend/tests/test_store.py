import time
from pathlib import Path

from agent_lab.agents.react import build_graph
from agent_lab.store import Run, Store
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
