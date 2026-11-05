"""SQLite persistence for test cases and evaluations (M17): a mixin of `store.Store`."""

import json
import sqlite3
import threading
import time
import uuid

from pydantic import TypeAdapter

from agent_lab.evaluation.model import (
    Attempt,
    Case,
    CaseFields,
    Check,
    CheckResult,
    Evaluation,
    EvaluationState,
    FrozenCase,
)

EVALUATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_cases (
    case_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    prompt TEXT NOT NULL,
    checks TEXT NOT NULL,
    approvals TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE (agent_id, name_key)
);
CREATE TABLE IF NOT EXISTS evaluations (
    eval_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    config_version TEXT NOT NULL,
    config TEXT NOT NULL,
    harness TEXT NOT NULL,
    model TEXT NOT NULL,
    repeats INTEGER NOT NULL,
    cases TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE INDEX IF NOT EXISTS evaluations_by_agent ON evaluations(agent_id, started_at);
CREATE TABLE IF NOT EXISTS eval_attempts (
    eval_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    number INTEGER NOT NULL,
    run_id TEXT,
    outcome TEXT NOT NULL,
    reason TEXT,
    checks TEXT NOT NULL,
    llm_calls INTEGER,
    tool_calls INTEGER,
    tokens INTEGER,
    wall_ms INTEGER,
    PRIMARY KEY (eval_id, case_id, number)
);
"""

_CHECKS = TypeAdapter(list[Check])
_RESULTS = TypeAdapter(list[CheckResult])
_FROZEN = TypeAdapter(list[FrozenCase])


class NameInUse(Exception):
    """Another custom agent, or another case of this agent, already has this name (ignoring case
    and surrounding spaces)."""


class EvaluationTables:
    _db: sqlite3.Connection
    _lock: threading.Lock

    # --- test cases ---

    def create_case(self, agent_id: str, fields: CaseFields) -> Case:
        now = time.time()
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        try:
            with self._lock:
                self._db.execute(
                    "INSERT INTO eval_cases (case_id, agent_id, name, name_key, prompt, checks,"
                    " approvals, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (case_id, agent_id, *_case_values(fields), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise NameInUse(fields.name) from exc
        return _as_case(case_id, agent_id, fields)

    def update_case(self, case_id: str, fields: CaseFields) -> Case | None:
        current = self.get_case(case_id)
        if current is None:
            return None
        try:
            with self._lock:
                self._db.execute(
                    "UPDATE eval_cases SET name=?, name_key=?, prompt=?, checks=?, approvals=?,"
                    " updated_at=? WHERE case_id=?",
                    (*_case_values(fields), time.time(), case_id),
                )
        except sqlite3.IntegrityError as exc:
            raise NameInUse(fields.name) from exc
        return _as_case(case_id, current.agent_id, fields)

    def delete_case(self, case_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM eval_cases WHERE case_id=?", (case_id,))
        return cursor.rowcount > 0

    def get_case(self, case_id: str) -> Case | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM eval_cases WHERE case_id=?", (case_id,)
            ).fetchone()
        return _case(row) if row else None

    def list_cases(self, agent_id: str) -> list[Case]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM eval_cases WHERE agent_id=? ORDER BY name_key", (agent_id,)
            ).fetchall()
        return [_case(r) for r in rows]

    # --- evaluations ---

    def create_evaluation(self, evaluation: Evaluation) -> None:
        e = evaluation
        with self._lock:
            self._db.execute(
                "INSERT INTO evaluations (eval_id, agent_id, agent_name, config_version, config,"
                " harness, model, repeats, cases, state, started_at, ended_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    e.eval_id,
                    e.agent_id,
                    e.agent_name,
                    e.config_version,
                    json.dumps(e.config),
                    json.dumps(e.harness),
                    e.model.model_dump_json(),
                    e.repeats,
                    _FROZEN.dump_json(e.cases).decode(),
                    e.state,
                    e.started_at,
                    e.ended_at,
                ),
            )

    def finish_evaluation(self, eval_id: str, state: EvaluationState, ended_at: float) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE evaluations SET state=?, ended_at=? WHERE eval_id=?",
                (state, ended_at, eval_id),
            )

    def mark_evaluations_interrupted(self) -> None:
        """Evaluations a stopped lab left running: they do not resume (FR-022)."""
        with self._lock:
            self._db.execute(
                "UPDATE evaluations SET state='interrupted', ended_at=? WHERE state='running'",
                (time.time(),),
            )

    def get_evaluation(self, eval_id: str) -> Evaluation | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM evaluations WHERE eval_id=?", (eval_id,)
            ).fetchone()
        return _evaluation(row) if row else None

    def list_evaluations(self, agent_id: str) -> list[Evaluation]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM evaluations WHERE agent_id=? ORDER BY started_at DESC, rowid DESC",
                (agent_id,),
            ).fetchall()
        return [_evaluation(r) for r in rows]

    def add_attempt(self, attempt: Attempt) -> None:
        a = attempt
        with self._lock:
            self._db.execute(
                "INSERT INTO eval_attempts (eval_id, case_id, number, run_id, outcome, reason,"
                " checks, llm_calls, tool_calls, tokens, wall_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    a.eval_id,
                    a.case_id,
                    a.number,
                    a.run_id,
                    a.outcome,
                    a.reason,
                    _RESULTS.dump_json(a.checks).decode(),
                    a.llm_calls,
                    a.tool_calls,
                    a.tokens,
                    a.wall_ms,
                ),
            )

    def attempts(self, eval_id: str) -> list[Attempt]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM eval_attempts WHERE eval_id=? ORDER BY rowid", (eval_id,)
            ).fetchall()
        return [_attempt(r) for r in rows]

    def _delete_evaluation_data(self, agent_id: str) -> None:
        """An agent's cases and results, and the runs only those results point to. Holds no lock:
        the caller does."""
        self._db.execute("DELETE FROM eval_cases WHERE agent_id=?", (agent_id,))
        ids = "SELECT eval_id FROM evaluations WHERE agent_id=?"
        statements = (
            f"DELETE FROM spans WHERE run_id IN (SELECT run_id FROM runs WHERE eval_id IN ({ids}))",  # noqa: S608
            f"DELETE FROM runs WHERE eval_id IN ({ids})",  # noqa: S608
            f"DELETE FROM eval_attempts WHERE eval_id IN ({ids})",  # noqa: S608
        )
        for statement in statements:
            self._db.execute(statement, (agent_id,))
        self._db.execute("DELETE FROM evaluations WHERE agent_id=?", (agent_id,))


def _case_values(fields: CaseFields) -> tuple[str, str, str, str, str]:
    return (
        fields.name,
        fields.name.strip().lower(),
        fields.prompt,
        _CHECKS.dump_json(fields.checks).decode(),
        fields.approvals,
    )


def _as_case(case_id: str, agent_id: str, fields: CaseFields) -> Case:
    return Case(case_id=case_id, agent_id=agent_id, **fields.model_dump())


def _case(row: sqlite3.Row) -> Case:
    return Case(
        case_id=row["case_id"],
        agent_id=row["agent_id"],
        name=row["name"],
        prompt=row["prompt"],
        checks=_CHECKS.validate_json(row["checks"]),
        approvals=row["approvals"],
    )


def _evaluation(row: sqlite3.Row) -> Evaluation:
    data = dict(row)
    data["config"] = json.loads(data["config"])
    data["harness"] = json.loads(data["harness"])
    data["model"] = json.loads(data["model"])
    data["cases"] = json.loads(data["cases"])
    return Evaluation.model_validate(data)


def _attempt(row: sqlite3.Row) -> Attempt:
    data = dict(row)
    data["checks"] = json.loads(data["checks"])
    return Attempt.model_validate(data)
