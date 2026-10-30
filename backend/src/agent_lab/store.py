"""SQLite persistence for runs and spans."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from agent_lab.graph import Graph
from agent_lab.tracing.span import Span

RunStatus = Literal["running", "completed", "max_iterations", "error"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    config_version TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    answer TEXT,
    graph TEXT NOT NULL,
    config TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    config_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    input TEXT,
    output TEXT,
    error TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT,
    attributes TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spans_by_run ON spans(run_id, started_at);
"""

_SPAN_JSON = ("input", "output", "attributes")


class Run(BaseModel):
    run_id: str
    agent_id: str
    config_version: str
    prompt: str
    status: RunStatus
    answer: str | None = None
    graph: Graph
    config: dict[str, Any]
    started_at: float
    ended_at: float | None = None


class Store:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One connection shared by the event loop thread and test threads; writes are tiny.
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def create_run(self, run: Run) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run.run_id,
                    run.agent_id,
                    run.config_version,
                    run.prompt,
                    run.status,
                    run.answer,
                    run.graph.model_dump_json(),
                    json.dumps(run.config),
                    run.started_at,
                    run.ended_at,
                ),
            )

    def finish_run(
        self, run_id: str, status: RunStatus, answer: str | None, ended_at: float
    ) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE runs SET status=?, answer=?, ended_at=? WHERE run_id=?",
                (status, answer, ended_at, run_id),
            )

    def save_span(self, span: Span) -> None:
        """Insert or replace: called when a span starts and again when it ends."""
        row = span.model_dump(mode="json")
        for key in _SPAN_JSON:
            row[key] = json.dumps(row[key])
        # Column names come from the Span model, never from input.
        columns = ", ".join(row)
        placeholders = ", ".join(f":{k}" for k in row)
        sql = f"INSERT OR REPLACE INTO spans ({columns}) VALUES ({placeholders})"  # noqa: S608
        with self._lock:
            self._db.execute(sql, row)

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return _run(row) if row else None

    def list_runs(self, limit: int = 100) -> list[Run]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_run(r) for r in rows]

    def get_spans(self, run_id: str) -> list[Span]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM spans WHERE run_id=? ORDER BY started_at, rowid", (run_id,)
            ).fetchall()
        spans: list[Span] = []
        for r in rows:
            data = dict(r)
            for key in _SPAN_JSON:
                data[key] = json.loads(data[key]) if data[key] is not None else None
            spans.append(Span.model_validate(data))
        return spans


def _run(row: sqlite3.Row) -> Run:
    data = dict(row)
    data["graph"] = Graph.model_validate_json(data["graph"])
    data["config"] = json.loads(data["config"])
    return Run.model_validate(data)
