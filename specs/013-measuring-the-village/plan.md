# Implementation Plan: M13 — Measuring the Village

**Branch**: `main` (feature directory `013-measuring-the-village`) | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-measuring-the-village/spec.md`

## Summary

Three instruments, all outside the village's own behaviour:

1. **Village health**: `village/health.py` computes per-day numbers on request from the stored
   runs, each day's notes (the chronicle run's prompt, or today's day record) and a new
   **day trail**. The runner writes one compact row per step to a new `village_trail` table. A
   `born` timestamp in the world keeps runs from before a Reset, or from the owner in a scenario
   copy, out of the count. Two endpoints and a **Village health** panel show the numbers.
2. **Turn checks**: JSON files in `backend/evals/checks/`, each either a fixture (a village built
   with `build_world`, its prompt built by today's code) or a frozen prompt. The command
   `python -m agent_lab.village.evals checks` runs each check N times on the real model against
   `data/evals.db`, which holds a fresh copy of the owner's agents. It reports passes with a
   Wilson 95% interval and compares results only beyond chance.
3. **Scenarios**: JSON files in `backend/evals/scenarios/`, each a fixture, a horizon and a named
   condition. Every repeat runs on a fresh copy in `data/evals/`, stepped to the horizon with
   `Village.step()`, and is judged with the condition and `day_health`.

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged (the Wilson interval is written by hand)
- **Storage**: SQLite:
  - the owner's database gains a `runs.eval_id` column, the `village_trail` table and an index
    on `runs(village_tick)`;
  - `data/evals.db` holds check runs and `eval_results`;
  - scenario copies go to `data/evals/*.db`.
- **Testing**: pytest with `FakeLLM` (the CLI's runners take a `Models`, so tests give them the
  fake), vitest
- **Target Platform**: local (127.0.0.1)
- **Project Type**: web application plus a command-line module in the backend
- **Performance Goals**: health of 28 days in under 2 s on the owner's database (about 8,000
  runs); a trail row is about 300 bytes per step
- **Constraints**:
  - real-model evals never run inside `make check`;
  - the owner's database is only read by the evals;
  - no world-version bump (`born` is read with a default);
  - while `make dev` runs, store changes reload against the owner's village, so implementation
    stops `make dev` or backs up first (memory note `dev-reload-resets-village`).
- **Scale/Scope**: 4 villagers, at least 12 checks and 3 scenarios shipped

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | New small modules (`health.py`, `evals/fixtures.py`, `checks.py`, `scenarios.py`, `results.py`, `__main__.py`), no framework; the runner gains only the trail write |
| II. Observable by default | Pass | Every check and scenario attempt is an ordinary traced run of the same block agents; check runs carry `eval_id`, scenario runs live in their copy and can be opened with `make dev` on that file |
| III. Secure local defaults | Pass | The evals open the owner's database read-only and write only under `data/`; fixtures are validated (unknown keys rejected); no model output is executed |
| IV. Smallest change | Pass | Health is computed, not stored; existing parsers (`parse_action`, `parse_plan`, the meeting parsers) judge the answers; `Village.step()` drives scenarios; no version bump |
| V. Gates + traceability | Pass | Health numbers, fixtures, expectations, statistics and runners are tested with `FakeLLM`; real-model results are manual checks recorded in `tasks.md`; the evals report and never gate |

Post-design re-check: all pass. There is no Complexity Tracking entry.

## Design

### Backend

- `store.py`:
  - the `eval_id` column (added in place like the M3 columns), with `create_run` storing it;
  - `list_runs` and `list_turns` filter `eval_id IS NULL`;
  - index `runs_by_tick`;
  - the `village_trail` table with `add_trail`, `trail`, `prune_trail` and `clear_trail`;
  - `village_runs(first_tick, last_tick, since)` returns the small columns only;
  - `chronicle_prompt_of(day)` gives the stored prompt of that day's chronicle run;
  - `copy_agents_from(path, ids)`, for the evals.
- `runs.py`: `new_run(..., eval_id=None)`.
- `village/world.py`: `new_world()` sets `born = time.time()`.
- `village/runner.py`:
  - at the end of `_advance`, `store.add_trail(tick, trail_row(world, states))`;
  - prune when the day record opens;
  - Reset clears the trail and sets a new `born`.
- `village/health.py` (new, pure):
  - `trail_row(world, state_of)`;
  - `reason_template(text)`;
  - `day_health(day, runs, notes, trail, chronicle, final)`;
  - the helpers `plan_adherence`, `stuck_hours`, `load_minutes` and `given_back`.
- `village/health_view.py` (new, thin): `days_health(store, world, days)`. It gathers the
  sources per day, caches finished days by `(born, day)`, and computes today from
  `world["day_record"]`.
- `api.py`: `GET /village/health` and `GET /village/health/{day}/turns?reason=`.
- `village/evals/` (new package):
  - `fixtures.py`: `build_world(fixture)` and its validation;
  - `checks.py`:
    - `load_checks(dir)`;
    - `prompt_of(check, world)` builds the prompt for decide, plan, propose, vote,
      decide_meeting or work_plan;
    - `judge(check, answer, world) -> (passed, why)`;
    - `run_checks(checks, models, store, repeats) -> result`;
    - `add_check(store, run_id, name, expect)`;
  - `scenarios.py`:
    - `load_scenarios(dir)`;
    - `CONDITIONS` (meeting_attendance, load_at_site, talk_then_go, built);
    - `run_scenario(scenario, models, owner_db, out_dir, repeats) -> result`;
  - `results.py`: `wilson(passes, n)`, `compare(a, b)`, `save_result` / `load_result` /
    `list_results` on `evals.db`, and the text tables;
  - `__main__.py`: the commands of contracts/interfaces.md, built on `argparse` (stdlib).
- `backend/evals/checks/*.json` (at least 12) and `backend/evals/scenarios/*.json` (3), drawn
  from the M11 and M12 manual checks (list in research §5 and the tasks).
- `Makefile`: `eval-checks` and `eval-scenarios`.

### Frontend

- `lib/api.ts`: the `DayHealth` type, `villageHealth(days)` and `healthTurns(day, reason)`.
- `lib/health.ts` (+ vitest), pure:
  - `healthRow(day)` gives the table cells, with "–" for null and percentages;
  - `refusalLines(day)`;
  - `healthTitle(day)` gives "Day 66 (so far)".
- `components/village/HealthPanel.tsx` (new): the table, a day's detail, and a reason's turns
  (each opening its run).
- `VillageView.tsx`: the **Village health** button.

### Tests

- `test_village_health.py`: every number on scripted runs, notes and trail; null without a
  trail; the reason templates; a day without runs left out; `born` filtering.
- Runner: a trail row each step, pruning, and Reset clearing it.
- Store: `eval_id` runs left out of the turn and run lists.
- API: both endpoints.
- `test_village_evals.py`:
  - fixtures (each key, unknown keys rejected);
  - prompts built by today's code;
  - each expectation kind passing and failing;
  - Wilson against known values;
  - compare marking changes only beyond chance;
  - `run_checks` with `FakeLLM` (results stored, `eval_id` set);
  - `add_check` from a run;
  - `run_scenario` with `FakeLLM` (a copy made, the owner's database unchanged, the condition
    judged, an unfinished run, health per day);
  - the CLI parsing.
- `health.test.ts` for the panel's view logic.

## Project Structure

### Documentation (this feature)

```text
specs/013-measuring-the-village/
├── spec.md
├── plan.md                  # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/interfaces.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code

```text
backend/src/agent_lab/store.py, runs.py, api.py
backend/src/agent_lab/village/world.py, runner.py, health.py (new), health_view.py (new)
backend/src/agent_lab/village/evals/__init__.py, __main__.py, fixtures.py, checks.py,
    scenarios.py, results.py (all new)
backend/evals/checks/*.json, backend/evals/scenarios/*.json (new)
backend/tests/test_village_health.py, test_village_evals.py (new), test_village_runner.py,
    test_store.py, test_village_api.py
frontend/src/lib/api.ts, lib/health.ts (+ test, new), components/village/HealthPanel.tsx (new),
    VillageView.tsx
Makefile, README.md, docs/village.md, docs/api.md, AGENTS.md
```

**Structure Decision**:
- Health lives with the village, because it reads the village's world and runs.
- The evals are a sub-package of the village with a `__main__`, so `python -m` runs them.
- The definitions are data files in `backend/evals/`, reviewed like code.

## Complexity Tracking

None.
