"""`python -m agent_lab.village.evals`: turn checks, scenarios, results and village health on the
command line (specs/013-measuring-the-village/contracts/interfaces.md). Reports, never gates."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from agent_lab.config import Settings
from agent_lab.llm.models import Models, models_from_settings
from agent_lab.store import Store
from agent_lab.village.evals.checks import add_check, load_checks, read_owner, run_checks
from agent_lab.village.evals.results import Results, checks_table, compare, compare_table
from agent_lab.village.health_view import days_health

OWNER_DB = "data/agent_lab.db"
EVALS_DB = "data/evals.db"
CHECKS = "evals/checks"
SCENARIOS = "evals/scenarios"
COPIES = "data/evals"


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="python -m agent_lab.village.evals")
    commands = top.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--db", default=OWNER_DB, help="the owner's database (only read)")
        sub.add_argument("--evals", default=EVALS_DB, help="where results and check runs go")
        return sub

    checks = command("checks", "run the turn checks on the real model")
    checks.add_argument("--repeats", type=int, default=10)
    checks.add_argument("--only", nargs="+", default=None)
    checks.add_argument("--dir", default=CHECKS)
    scenarios = command("scenarios", "run the scenarios on fresh copies")
    scenarios.add_argument("--repeats", type=int, default=5)
    scenarios.add_argument("--only", nargs="+", default=None)
    scenarios.add_argument("--dir", default=SCENARIOS)
    scenarios.add_argument("--copies", default=COPIES)
    add = command("add-check", "a frozen check from a recorded run")
    add.add_argument("--run", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--expect", required=True, help='e.g. \'{"action": {"action": "give"}}\'')
    add.add_argument("--dir", default=CHECKS)
    results = command("results", "list the kept results")
    results.add_argument("--kind", choices=("checks", "scenarios"), default=None)
    comparison = command("compare", "compare two results, changes beyond chance only")
    comparison.add_argument("results", nargs=2)
    health = command("health", "village health of the recent days")
    health.add_argument("--days", type=int, default=7)
    return top


def _models() -> Models:
    return models_from_settings(Settings.from_env())


def _health(db: str, days: int) -> int:
    world, _ = read_owner(db)
    for day in days_health(Store(db), world, days):
        print(f"Day {day['day']}{'' if day['final'] else ' (so far)'}")
        waits = f"{round(100 * day['waits'] / day['decisions'])}%" if day["decisions"] else "-"
        plan = day["plan_adherence"]
        kept = f"{plan['kept']}/{plan['entries']}" if plan else "-"
        print(
            f"  Decisions {day['decisions']}  Waits {waits}  Plan kept {kept}  "
            f"Trades {day['trades']}  Loads {day['loads_set_down']}/{day['loads_worked_in']}  "
            f"Stuck hours {day['stuck_hours']}  Weather slips {day['weather_slips']}"
        )
        found, whispers = day["happenings"], day["whispers"]
        print(
            f"  Happenings {found['count']} ({found['dealt']} dealt)  "
            f"Boat trips {day['boat_trips']}  "
            f"Whispers {whispers['count']} ({whispers['followed']} followed)"
        )
        for r in day["refusals"]:
            print(f"    {r['count']}x {r['reason']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "checks":
        checks = load_checks(args.dir)
        if args.only:
            checks = [c for c in checks if c["name"] in args.only]
        result = asyncio.run(run_checks(checks, _models(), args.db, args.evals, args.repeats))
        print(checks_table(result))
        return 0
    if args.command == "scenarios":
        from agent_lab.village.evals.scenarios import load_scenarios, run_scenarios

        scenarios = load_scenarios(args.dir)
        if args.only:
            scenarios = [s for s in scenarios if s["name"] in args.only]
        from agent_lab.village.evals.results import scenarios_table

        result = asyncio.run(
            run_scenarios(scenarios, _models(), args.db, args.copies, args.evals, args.repeats)
        )
        print(scenarios_table(result))
        return 0
    if args.command == "add-check":
        path = add_check(args.db, args.run, args.name, json.loads(args.expect), args.dir)
        print(f"wrote {path}")
        return 0
    kept = Results(args.evals)
    if args.command == "results":
        for r in kept.list(args.kind):
            print(f"{r['result_id']}  {r['kind']:<9} {r['model']}  {r['repeats']} repeats")
        return 0
    if args.command == "compare":
        before, after = (kept.load(i) for i in args.results)
        if before is None or after is None:
            print("no such result", file=sys.stderr)
            return 1
        print(compare_table(*compare(before, after)))
        return 0
    return _health(args.db, args.days)


if __name__ == "__main__":
    Path(EVALS_DB).parent.mkdir(parents=True, exist_ok=True)
    sys.exit(main())
