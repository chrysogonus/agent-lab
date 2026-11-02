"""Turn checks: one situation given to the real model many times, each answer judged against
the kind of answer wanted (specs/013-measuring-the-village/research.md §5)."""

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import model_of
from agent_lab.bus import Bus
from agent_lab.llm.models import Models
from agent_lab.runs import execute_run, new_run, resolve
from agent_lab.store import Store
from agent_lab.village.evals.fixtures import FixtureError, build_world
from agent_lab.village.evals.results import Results, wilson
from agent_lab.village.meeting import (
    decision_prompt,
    parse_decision,
    parse_proposals,
    parse_tasks,
    parse_vote,
    proposal_prompt,
    vote_prompt,
    work_plan_prompt,
)
from agent_lab.village.plan import parse_plan, plan_prompt
from agent_lab.village.turn import observation, parse_action
from agent_lab.village.world import new_world

AGENTS = ("villager", "planner", "meeting")
PROMPTS = ("decide", "plan", "propose", "vote", "decide_meeting", "work_plan")
EXPECTS = ("action", "valid", "tasks_include", "not")
ANSWER_SHOWN = 300

Check = dict[str, Any]
World = dict[str, Any]


def load_checks(directory: str | Path) -> list[Check]:
    """Every check in the directory, in name order; a malformed one stops with its file name."""
    checks: list[Check] = []
    for path in sorted(Path(directory).glob("*.json")):
        check: Check = json.loads(path.read_text())
        situation = check.get("situation", {})
        problems: list[str] = []
        if check.get("agent") not in AGENTS:
            problems.append("agent")
        if situation.get("prompt") not in PROMPTS:
            problems.append("situation.prompt")
        if not {"fixture", "frozen"} & set(situation):
            problems.append("situation (fixture or frozen)")
        if len(set(check.get("expect", {})) & set(EXPECTS)) != 1:
            problems.append("expect")
        if check.get("agent") == "villager" and not check.get("as"):
            problems.append("as")
        if problems:
            raise ValueError(f"{path.name}: bad {', '.join(problems)}")
        if "fixture" in situation:
            try:
                build_world(situation["fixture"])
            except FixtureError as exc:
                raise ValueError(f"{path.name}: {exc}") from None
        checks.append(check)
    return checks


def prompt_of(check: Check) -> tuple[str, World | None]:
    """The prompt to ask, built with today's code from a fixture, or the frozen text."""
    situation = check["situation"]
    if "frozen" in situation:
        return situation["frozen"], None
    world = build_world(situation["fixture"])
    name = check.get("as", "Hilde")
    builders = {
        "decide": lambda: observation(world, name),
        "plan": lambda: plan_prompt(world, name),
        "propose": lambda: proposal_prompt(world),
        "vote": lambda: vote_prompt(world, name),
        "decide_meeting": lambda: decision_prompt(world),
        "work_plan": lambda: work_plan_prompt(world),
    }
    return builders[situation["prompt"]](), world


def _matches(found: dict[str, Any], pattern: dict[str, Any]) -> bool:
    return all(found.get(key) == value for key, value in pattern.items())


def _decoded(answer: str | None) -> dict[str, Any] | None:
    try:
        found = json.loads(answer or "")
    except json.JSONDecodeError:
        return None
    return found if isinstance(found, dict) else None  # pyright: ignore[reportUnknownVariableType]


def _valid(check: Check, answer: str, world: World | None) -> str | None:
    """None when the planner's or meeting's parser accepts the answer, else why not."""
    kind, name = check["situation"]["prompt"], check.get("as", "Hilde")
    world = world or new_world()
    empty: dict[str, Any] = {"proposals": [], "votes": {}}
    meeting: dict[str, Any] = world["meeting"] or empty
    if kind == "plan":
        return parse_plan(answer, name)[1]
    if kind == "propose":
        return parse_proposals(answer, world)[1]
    if kind == "vote":
        return parse_vote(answer, meeting["proposals"])[1]
    if kind == "decide_meeting":
        decision, why = parse_decision(answer, meeting["proposals"], meeting["votes"])
        return why if not decision or decision["by"] != "hilde" else None
    return parse_tasks(answer)[1]


def judge(check: Check, answer: str | None, world: World | None) -> tuple[bool, str | None]:
    """Whether an answer is the kind wanted, and why not."""
    expect = check["expect"]
    if "valid" in expect or "tasks_include" in expect:
        why = _valid(check, answer or "", world)
        if why:
            return False, f"not valid: {why}"
        if "tasks_include" in expect:
            tasks = parse_tasks(answer)[0] or []
            if not any(_matches(t, expect["tasks_include"]) for t in tasks):
                return False, "no such task in the work plan"
        return True, None
    if world is not None:
        found, reason = parse_action(answer, world, check["as"])
    else:
        found, reason = _decoded(answer), "the answer is not JSON"
        if found is None:
            return False, f"answered wait: {reason}"
    if "not" in expect:
        unwanted = next((p for p in expect["not"] if _matches(found, p)), None)
        return (False, f"an answer that is not wanted: {unwanted}") if unwanted else (True, None)
    wanted: dict[str, Any] = expect["action"]
    if found["action"] == "wait" and wanted.get("action") != "wait":
        return False, f"answered wait: {reason or 'wait'}"
    for key, value in wanted.items():
        if found.get(key) != value:
            return False, f"{key} was {found.get(key)!r}, not {value!r}"
    return True, None


# --- running checks on the real model ---


def read_owner(owner_db: str | Path) -> tuple[World, list[str]]:
    """The owner's world and the ids of its village agents, read without writing."""
    db = sqlite3.connect(f"file:{owner_db}?mode=ro", uri=True)
    try:
        row = db.execute("SELECT state FROM village WHERE id=1").fetchone()
    finally:
        db.close()
    if row is None:
        raise ValueError(f"{owner_db} holds no village")
    world: World = json.loads(row[0])
    ids = [v["agent_id"] for v in world["villagers"]]
    shared = ("reflection_agent_id", "chronicler_agent_id", "planner_agent_id", "meeting_agent_id")
    ids += [world.get(k) for k in shared]
    return world, [i for i in ids if i]


def agent_models(store: Store, agent_ids: list[str], models: Models) -> dict[str, str]:
    """The model each agent actually runs on, by name ("local/qwen3.5-9b, thinking off"): an
    agent can pin its own, so the default alone does not say what was measured."""
    found: dict[str, str] = {}
    for agent_id in agent_ids:
        _, config, name, _ = resolve(agent_id, store, models)
        ref = model_of(config)
        thinking = getattr(config, "reasoning", None)
        found[name] = f"{ref.provider}/{ref.model}" + (
            "" if thinking is None else f", thinking {'on' if thinking else 'off'}"
        )
    return found


def agent_of(check: Check, owner: World) -> str:
    if check["agent"] == "planner":
        return owner["planner_agent_id"]
    if check["agent"] == "meeting":
        return owner["meeting_agent_id"]
    return next(v["agent_id"] for v in owner["villagers"] if v["name"] == check["as"])


async def _attempt(
    check: Check, prompt: str, agent_id: str, models: Models, store: Store, result_id: str
) -> tuple[str | None, str | None, str | None]:
    """(run id, answer, why it failed) for one attempt."""
    run, config, spec, llm = new_run(
        prompt, agent_id, models, store, villager=check.get("as"), eval_id=result_id
    )
    store.create_run(run)
    await execute_run(
        run=run, prompt=prompt, config=config, spec=spec, llm=llm, store=store, bus=Bus()
    )
    done = store.get_run(run.run_id)
    if done is None or done.status != "completed":
        return run.run_id, None, "the run failed"
    return run.run_id, done.answer, None


async def run_checks(
    checks: list[Check],
    models: Models,
    owner_db: str | Path,
    evals_db: str | Path,
    repeats: int,
) -> dict[str, Any]:
    """Each check `repeats` times against the owner's current agents, copied into the evals
    database; the owner's database is only read. The result is kept and returned."""
    owner, agent_ids = read_owner(owner_db)
    store = Store(evals_db)
    store.copy_agents_from(owner_db, agent_ids)
    result_id = uuid.uuid4().hex[:12]
    rows: list[dict[str, Any]] = []
    for check in checks:
        prompt, world = prompt_of(check)
        attempts = await asyncio.gather(
            *[
                _attempt(check, prompt, agent_of(check, owner), models, store, result_id)
                for _ in range(repeats)
            ]
        )
        failures: list[dict[str, Any]] = []
        for run_id, answer, failed in attempts:
            passed, why = (False, failed) if failed else judge(check, answer, world)
            if not passed:
                failures.append(
                    {"run_id": run_id, "answer": (answer or "")[:ANSWER_SHOWN], "why": why}
                )
        passes = repeats - len(failures)
        kind = "fixture" if "fixture" in check["situation"] else "frozen"
        rows.append(
            {
                "name": check["name"],
                "kind": kind,
                "passes": passes,
                "attempts": repeats,
                "interval": list(wilson(passes, repeats)),
                "failures": failures,
            }
        )
    total = sum(r["passes"] for r in rows), sum(r["attempts"] for r in rows)
    default = models.default
    result: dict[str, Any] = {
        "result_id": result_id,
        "kind": "checks",
        "created_at": time.time(),
        "model": f"{default.provider}/{default.model}",
        "settings": {"owner_db": str(owner_db), "models": agent_models(store, agent_ids, models)},
        "repeats": repeats,
        "data": {
            "checks": rows,
            "overall": {"passes": total[0], "attempts": total[1], "interval": list(wilson(*total))},
        },
    }
    Results(evals_db).save(result)
    return result


def add_check(
    owner_db: str | Path, run_id: str, name: str, expect: dict[str, Any], out_dir: str | Path
) -> Path:
    """A frozen check from a recorded run: its exact prompt, its agent, and what is wanted."""
    owner, _ = read_owner(owner_db)
    db = sqlite3.connect(f"file:{owner_db}?mode=ro", uri=True)
    try:
        row = db.execute(
            "SELECT prompt, agent_id, villager, village_action FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
    finally:
        db.close()
    if row is None:
        raise ValueError(f"no run {run_id!r} in {owner_db}")
    prompt, agent_id, villager, action_text = row
    recorded: dict[str, Any] = json.loads(action_text) if action_text else {}
    action: str | None = recorded.get("action")
    check: Check = {"name": name, "situation": {"frozen": prompt, "from_run": run_id}}
    if agent_id == owner.get("planner_agent_id"):
        check |= {"agent": "planner", "as": villager}
        check["situation"]["prompt"] = "plan"
    elif agent_id == owner.get("meeting_agent_id"):
        kinds = {"propose": "propose", "vote": "vote", "decide": "decide_meeting"}
        check |= {"agent": "meeting", "as": villager}
        check["situation"]["prompt"] = kinds.get(action or "", "work_plan")
    else:
        check |= {"agent": "villager", "as": villager}
        check["situation"]["prompt"] = "decide"
    check["expect"] = expect
    path = Path(out_dir) / f"{name}.json"
    path.write_text(json.dumps(check, indent=2) + "\n")
    return path
