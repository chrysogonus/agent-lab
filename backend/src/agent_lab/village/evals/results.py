"""Pass rates with honest ranges, comparisons beyond chance, and kept results
(specs/013-measuring-the-village/research.md §5, §8)."""

import json
import sqlite3
import threading
from math import sqrt
from pathlib import Path
from typing import Any

Z = 1.96  # 95%

Result = dict[str, Any]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_results (
    result_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL,
    model TEXT NOT NULL,
    settings TEXT NOT NULL,
    repeats INTEGER NOT NULL,
    data TEXT NOT NULL
);
"""


def wilson(passes: int, n: int) -> tuple[float, float]:
    """The 95% Wilson score interval of a pass rate: what `n` attempts can honestly claim."""
    if n == 0:
        return 0.0, 1.0
    p = passes / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _items(result: Result) -> dict[str, tuple[int, int]]:
    """name → (passes, attempts) of checks, or (held, finished) of scenarios."""
    data = result["data"]
    if "checks" in data:
        return {c["name"]: (c["passes"], c["attempts"]) for c in data["checks"]}
    return {s["name"]: (s["held"], s["finished"]) for s in data.get("scenarios", [])}


def compare(before: Result, after: Result) -> tuple[list[dict[str, Any]], list[str]]:
    """Per name: better or worse only when the two 95% ranges do not overlap, else no clear
    change; and notes on settings that differ."""
    a, b = _items(before), _items(after)
    lines: list[dict[str, Any]] = []
    for name in [n for n in a if n in b]:
        (low_a, high_a), (low_b, high_b) = wilson(*a[name]), wilson(*b[name])
        verdict = "better" if low_b > high_a else "worse" if high_b < low_a else "no clear change"
        lines.append({"name": name, "before": a[name], "after": b[name], "verdict": verdict})
    notes: list[str] = []
    if before["model"] != after["model"]:
        notes.append(f"the models differ: {before['model']} and {after['model']}")
    if before["repeats"] != after["repeats"]:
        notes.append(f"the repeats differ: {before['repeats']} and {after['repeats']}")
    return lines, notes


class Results:
    """Check and scenario results, kept in their own database under data/."""

    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.executescript(_SCHEMA)

    def save(self, result: Result) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO eval_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result["result_id"],
                    result["kind"],
                    result["created_at"],
                    result["model"],
                    json.dumps(result["settings"]),
                    result["repeats"],
                    json.dumps(result["data"]),
                ),
            )

    def load(self, result_id: str) -> Result | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM eval_results WHERE result_id=?", (result_id,)
            ).fetchone()
        return _result(row) if row else None

    def list(self, kind: str | None = None) -> list[Result]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM eval_results WHERE ? IS NULL OR kind=? ORDER BY created_at DESC",
                (kind, kind),
            ).fetchall()
        return [_result(r) for r in rows]


def _result(row: sqlite3.Row) -> Result:
    found = dict(row)
    found["settings"] = json.loads(found["settings"])
    found["data"] = json.loads(found["data"])
    return found


def _range(passes: int, n: int) -> str:
    low, high = wilson(passes, n)
    return f"[{round(100 * low)}% to {round(100 * high)}%]"


def checks_table(result: Result) -> str:
    lines = [f"checks {result['result_id']} · {result['model']} · {result['repeats']} repeats"]
    for c in result["data"]["checks"]:
        rate = f"{c['passes']}/{c['attempts']}"
        span = _range(c["passes"], c["attempts"])
        lines.append(f"  {c['name']:<24} {c['kind']:<8} {rate:>6}  {span}")
        lines += [f"      - {f['why']} (run {f['run_id']})" for f in c["failures"]]
    overall = result["data"].get("overall")
    if overall:
        lines.append(
            f"  {'overall':<33} {overall['passes']}/{overall['attempts']}  "
            f"{_range(overall['passes'], overall['attempts'])}"
        )
    return "\n".join(lines)


def scenarios_table(result: Result) -> str:
    lines = [f"scenarios {result['result_id']} · {result['model']} · {result['repeats']} repeats"]
    for s in result["data"]["scenarios"]:
        lines.append(
            f"  {s['name']:<24} held {s['held']}/{s['finished']} finished "
            f"({s['attempts']} run) {_range(s['held'], s['finished'])}"
        )
        for run in s["runs"]:
            state = "unfinished" if not run["finished"] else "held" if run["held"] else "failed"
            lines.append(f"      - {state}: {run['why']} ({run['db']})")
    return "\n".join(lines)


def compare_table(lines: list[dict[str, Any]], notes: list[str]) -> str:
    out = [f"  {n}" for n in notes]
    for line in lines:
        before, after = line["before"], line["after"]
        rates = f"{before[0]}/{before[1]} → {after[0]}/{after[1]}"
        out.append(f"  {line['name']:<24} {rates}  {line['verdict']}")
    return "\n".join(out)
