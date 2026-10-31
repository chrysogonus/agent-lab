"""SQLite persistence for runs and spans."""

import json
import sqlite3
import threading
import time
import uuid
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
    ended_at REAL,
    agent_name TEXT,
    template_id TEXT
);
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    sample_prompt TEXT NOT NULL,
    config TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
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
CREATE TABLE IF NOT EXISTS village (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL
);
"""

# Columns added after M2; older databases get them in place, their runs keep NULL.
_RUN_COLUMNS_SINCE_M3 = {
    "agent_name": "TEXT",
    "template_id": "TEXT",
    "village_tick": "INTEGER",  # M6: a villager's turn belongs to this tick
    "villager": "TEXT",
    "village_action": "TEXT",  # JSON: the action applied for the turn, with any wait reason
}

_SPAN_JSON = ("input", "output", "attributes")

# Runs with their totals, computed from their spans so M1 runs get them too.
_RUNS_WITH_TOTALS = """
SELECT runs.*,
    COUNT(CASE WHEN spans.kind = 'llm' THEN 1 END) AS llm_calls,
    COUNT(CASE WHEN spans.kind = 'tool' THEN 1 END) AS tool_calls,
    COALESCE(SUM(spans.tokens_in), 0) AS tokens_in,
    COALESCE(SUM(spans.tokens_out), 0) AS tokens_out
FROM runs LEFT JOIN spans ON spans.run_id = runs.run_id
"""


class RunTotals(BaseModel):
    llm_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    wall_ms: int | None  # None while the run is running


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
    totals: RunTotals | None = None  # filled when read from the store
    agent_name: str | None = None  # the agent's name when the run started; None before M3
    template_id: str | None = None  # None before M3
    village_tick: int | None = None  # set on a villager's turn (M6)
    villager: str | None = None
    village_action: dict[str, Any] | None = None


class NameInUse(Exception):
    """Another custom agent already has this name (ignoring case and surrounding spaces)."""


class CustomAgent(BaseModel):
    agent_id: str
    template_id: str
    name: str
    description: str
    sample_prompt: str
    config: dict[str, Any]  # the template's config without `model`
    created_at: float
    updated_at: float


class Store:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One connection shared by the event loop thread and test threads; writes are tiny.
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.executescript(_SCHEMA)
        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(runs)")}
        for column, kind in _RUN_COLUMNS_SINCE_M3.items():
            if column not in columns:
                self._db.execute(f"ALTER TABLE runs ADD COLUMN {column} {kind}")

    def close(self) -> None:
        self._db.close()

    def create_run(self, run: Run) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs (run_id, agent_id, config_version, prompt, status, answer, graph,"
                " config, started_at, ended_at, agent_name, template_id, village_tick, villager)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    run.agent_name,
                    run.template_id,
                    run.village_tick,
                    run.villager,
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
            row = self._db.execute(
                _RUNS_WITH_TOTALS + "WHERE runs.run_id=? GROUP BY runs.run_id", (run_id,)
            ).fetchone()
        return _run(row) if row else None

    def list_runs(self, limit: int = 100) -> list[Run]:
        with self._lock:
            rows = self._db.execute(
                _RUNS_WITH_TOTALS
                + "WHERE runs.village_tick IS NULL"  # turns are listed per villager
                " GROUP BY runs.run_id ORDER BY runs.started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_run(r) for r in rows]

    def list_turns(self, villager: str, limit: int = 200) -> list[Run]:
        """A villager's turns, newest first, whichever agent played them."""
        with self._lock:
            rows = self._db.execute(
                # Insertion order: the wall clock can step back (e.g. under WSL), rowid cannot.
                _RUNS_WITH_TOTALS + "WHERE runs.villager=?"
                " GROUP BY runs.run_id ORDER BY runs.rowid DESC LIMIT ?",
                (villager, limit),
            ).fetchall()
        return [_run(r) for r in rows]

    def set_village_action(self, run_id: str, action: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE runs SET village_action=? WHERE run_id=?", (json.dumps(action), run_id)
            )

    def load_village(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT state FROM village WHERE id=1").fetchone()
        return json.loads(row["state"]) if row else None

    def save_village(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO village (id, state) VALUES (1, ?)"
                " ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (json.dumps(state),),
            )

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

    def create_agent(
        self,
        *,
        template_id: str,
        name: str,
        description: str,
        sample_prompt: str,
        config: dict[str, Any],
    ) -> CustomAgent:
        now = time.time()
        agent = CustomAgent(
            agent_id=f"custom-{uuid.uuid4().hex[:12]}",
            template_id=template_id,
            name=name,
            description=description,
            sample_prompt=sample_prompt,
            config=config,
            created_at=now,
            updated_at=now,
        )
        self._write_agent(
            "INSERT INTO agents (name, name_key, description, sample_prompt, config, created_at,"
            " updated_at, agent_id, template_id) VALUES (?,?,?,?,?,?,?,?,?)",
            agent,
        )
        return agent

    def update_agent(
        self,
        agent_id: str,
        *,
        name: str,
        description: str,
        sample_prompt: str,
        config: dict[str, Any],
    ) -> CustomAgent | None:
        current = self.get_agent(agent_id)
        if current is None:
            return None
        agent = current.model_copy(
            update={
                "name": name,
                "description": description,
                "sample_prompt": sample_prompt,
                "config": config,
                "updated_at": time.time(),
            }
        )
        self._write_agent(
            "UPDATE agents SET name=?, name_key=?, description=?, sample_prompt=?, config=?,"
            " created_at=?, updated_at=? WHERE agent_id=? AND template_id=?",
            agent,
        )
        return agent

    def _write_agent(self, sql: str, agent: CustomAgent) -> None:
        # The INSERT and UPDATE above both take their parameters in this order.
        values = (
            agent.name,
            agent.name.strip().lower(),
            agent.description,
            agent.sample_prompt,
            json.dumps(agent.config),
            agent.created_at,
            agent.updated_at,
            agent.agent_id,
            agent.template_id,
        )
        try:
            with self._lock:
                self._db.execute(sql, values)
        except sqlite3.IntegrityError as exc:
            raise NameInUse(agent.name) from exc

    def delete_agent(self, agent_id: str) -> bool:
        """Runs of the agent keep their own snapshot and stay."""
        with self._lock:
            cursor = self._db.execute("DELETE FROM agents WHERE agent_id=?", (agent_id,))
        return cursor.rowcount > 0

    def get_agent(self, agent_id: str) -> CustomAgent | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        return _agent(row) if row else None

    def list_agents(self) -> list[CustomAgent]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM agents ORDER BY name_key").fetchall()
        return [_agent(r) for r in rows]


def _agent(row: sqlite3.Row) -> CustomAgent:
    data = dict(row)
    del data["name_key"]
    data["config"] = json.loads(data["config"])
    return CustomAgent.model_validate(data)


def _run(row: sqlite3.Row) -> Run:
    data = dict(row)
    data["graph"] = Graph.model_validate_json(data["graph"])
    data["config"] = json.loads(data["config"])
    if data.get("village_action") is not None:
        data["village_action"] = json.loads(data["village_action"])
    ended = data["ended_at"]
    data["totals"] = RunTotals(
        llm_calls=data.pop("llm_calls"),
        tool_calls=data.pop("tool_calls"),
        tokens_in=data.pop("tokens_in"),
        tokens_out=data.pop("tokens_out"),
        wall_ms=round((ended - data["started_at"]) * 1000) if ended is not None else None,
    )
    return Run.model_validate(data)
