---
description: "Task list for M13 — Measuring the Village"
---

# Tasks: M13 — Measuring the Village

**Input**: `specs/013-measuring-the-village/` (plan.md, spec.md, research.md, data-model.md,
contracts/interfaces.md, quickstart.md)

**Tests**: requested by the spec (FR-014, SC-001). `FakeLLM` only. Every task writes its failing
test first; runner tests pass `move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **Your village stays safe.** Before any store or runner edit, stop `make dev` (or back up
  `backend/data/agent_lab.db` with the sqlite backup API). The `--reload` backend runs
  half-finished edits against the owner's live village (memory note
  `dev-reload-resets-village`).
- **The evals only read the owner's database.** They write only to `backend/data/evals.db` and
  `backend/data/evals/`, which are both under the git-ignored `data/`.
- **Every attempt is a traced run.** Each check or scenario attempt is an ordinary run through
  `new_run` / `execute_run`. The answers are judged with the existing parsers (`parse_action`,
  `parse_plan`, the meeting parsers), never executed.
- **Missing means null.** A number whose source is missing is `None` in the backend and "–" in
  the UI, never 0.

---

## Phase 1: Foundational — store, trail, born, fixtures

- [X] T001 backend/src/agent_lab/store.py (data-model.md "Store"):
  - `runs.eval_id TEXT NULL`, added in place like `_RUN_COLUMNS_SINCE_M3`; `create_run` stores
    `run.eval_id` (new optional field on `Run`);
  - `list_runs` and `list_turns` add `AND runs.eval_id IS NULL`;
  - `CREATE INDEX IF NOT EXISTS runs_by_tick ON runs(village_tick)`;
  - table `village_trail(tick INTEGER PRIMARY KEY, row TEXT NOT NULL)` with `add_trail(tick,
    row)` (`INSERT OR REPLACE`), `trail(first_tick, last_tick) -> list[(tick, row)]`,
    `prune_trail(before_tick)` and `clear_trail()`;
  - `village_runs(first_tick, last_tick, since) -> list[dict]`, reading only `run_id`,
    `villager`, `village_tick`, `status`, `village_action` and `started_at`, for runs with
    `started_at >= since` and `eval_id IS NULL`;
  - `chronicle_prompt_of(day, since) -> str | None`: the prompt of the newest completed run
    whose `village_action` is a chronicle of that day.

  backend/src/agent_lab/runs.py: `new_run(..., eval_id=None)`.

  Tests in backend/tests/test_store.py:
  - a database without the column gets it;
  - eval runs are left out of both lists;
  - trail round trip, prune and clear;
  - `village_runs` filters by tick, `since` and `eval_id`;
  - `chronicle_prompt_of`.

  Requirements: FR-001, FR-013.
- [X] T002 Village changes:
  - backend/src/agent_lab/village/world.py: `new_world()` adds `born: time.time()`.
  - backend/src/agent_lab/village/health.py (new): `trail_row(world, states) -> dict`, which
    gives `{"v": [[name, x, y, place, state, carrying], …], "project": key | null, "used": int}`.
  - backend/src/agent_lab/village/runner.py:
    - at the end of `_advance`, `store.add_trail(tick, trail_row(...))` with `_state_of` per
      villager;
    - when a new day record opens, `prune_trail(tick - 28 * 144)`;
    - Reset calls `clear_trail()` and gets a new `born`;
    - `state()` leaves out `born`.

  Tests in backend/tests/test_village_runner.py:
  - one trail row per step with each villager's cell, place, state and carrying, and the
    project's used loads;
  - rows older than 28 days are pruned on a new day;
  - Reset clears the trail and sets a later `born`;
  - a world without `born` still loads (no version bump).

  Requirement: FR-001.
- [X] T003 [P] New backend/src/agent_lab/village/evals/__init__.py and fixtures.py (research §4,
  data-model.md "Fixture"): `build_world(fixture) -> world` from `new_world()` with:
  - `day`, `time`;
  - per villager:
    - `at`: a place key, "home", "site" (the project's first site cell) or `[x, y]`;
    - `asleep` (default false for named villagers; the others stay asleep at home);
    - `carrying`, `working` (a place key or "site");
    - `goal`: a place, "home" or "site";
    - `memories` and `learnings` as texts, at the fixture's tick minus one;
    - `inbox` `[{from, text}]`, `said`, `events` as texts;
    - `plan` entries, parsed with plan.py's entry format;
  - `conversations` `[[a, b, lines]]`;
  - `trader` (`true`: `trader_stock(day)`, or an explicit stock);
  - `project` (`key` plus optional `site`, `used`, `tasks`) and `built` (keys);
  - `meeting` (`kind`, `proposals [{key, reason}]`, `votes`, `present`);
  - `stalls`, `growth`;
  - `born` set to now.

  Every villager named is awake unless `asleep`; `last_decided` is the fixture's tick. Unknown
  keys, places, goods, projects or villagers raise `FixtureError` with what was wrong.

  Tests in new backend/tests/test_village_evals.py:
  - each key;
  - the defaults;
  - every error;
  - a fixture world gives an `observation` naming what it set (the trader, the project, the
    meeting, the carried load).

  Requirements: FR-004, FR-008.

## Phase 2: User Story 1 — Village health per day (P1) 🎯 MVP

- [X] T004 [US1] backend/src/agent_lab/village/health.py (research §3, data-model.md "Day
  health"):
  - `reason_template(text)`: villager names become `<villager>` (also inside quotes, as in
    "unknown villager 'Hilde'"), and building and basket goods become `<goods>`.
  - `day_health(day, runs, notes, trail, chronicle, final) -> dict | None` returns `None` for a
    day with no runs.
  - Its numbers:
    - `decisions` and `waits`, over the decision kinds move, find, say, goodbye, work, give,
      buy and wait; failed turns go to `failed_calls`;
    - `calls` per kind;
    - `refusals` (templates, most first);
    - `conversations` from the notes "A and B talked; what they said (their claims): x / y / z",
      as the count, lines per talk and the median;
    - `repeated_lines`;
    - `plan_adherence` `{kept, entries}`. The plan in effect is the last plan run for that
      villager before the entry. An entry is kept when, between its time and one hour after it,
      the trail has the villager at its place (by label) or next to the villager it names. With
      no trail it is `null`;
    - `meeting` from the notes and the meeting actions (`present`, `votes`, `outcome`), or
      `null`;
    - `trades` (applied buys);
    - `loads_set_down` (applied give-at-site actions);
    - `loads_worked_in` from the trail's `used` rising (or `null`);
    - `load_minutes`: the median from a villager's buy to its setting down that goods (or
      `null`);
    - `given_back`: A gave B goods and B gave them back the same day, plus refusals "just gave
      you this";
    - `weather_slips` from the chronicle entry, or `null` before it is written;
    - `stuck_hours`: villager-steps awake, not working and not asleep at home, on the same cell
      and in the same state for 6 or more steps in a row, divided by 6 (or `null`).

  Tests in new backend/tests/test_village_health.py:
  - every number on hand-made runs, notes and trail, equal to counts done by hand (SC-001);
  - each `null` case without a trail or chronicle;
  - the templates;
  - a day without runs.

  Requirements: FR-002, SC-001.
- [X] T005 [US1] Health on request:
  - New backend/src/agent_lab/village/health_view.py: `days_health(store, world, days=14)`.
    - It takes up to 28 days back from today, using runs since `world.get("born", 0)`.
    - Notes for a finished day come from `chronicle_prompt_of(day)`, as the lines under the
      "What happened" heading; for today they come from `world["day_record"]`.
    - It reads the trail for the day's ticks, and the chronicle entry from `world["chronicle"]`.
    - Today has `final: false`.
    - Finished days are cached in memory by `(born, day)`.
  - backend/src/agent_lab/api.py: `GET /village/health?days=` and
    `GET /village/health/{day}/turns?reason=` (decision runs of that day whose wait reason has
    that template, newest first, as `Run`s; 422 for a bad day).

  Tests:
  - backend/tests/test_village_health.py: `days_health` on a scripted village, covering finished
    and in-progress days, `born` filtering and caching;
  - backend/tests/test_village_api.py: both endpoints, their shape and the reason filter;
  - a timing check that 28 days over 8,000 runs take under 2 s (SC-002).

  Requirements: FR-001–FR-003, SC-002.
- [X] T006 [US1] Frontend:
  - frontend/src/lib/api.ts: the `DayHealth` type (data-model.md), `villageHealth(days)` and
    `healthTurns(day, reason)`.
  - frontend/src/lib/health.ts (new, pure):
    - `healthRow(day)` gives the cells decisions, waits %, refusals, talk lines (median), plan
      kept %, trades, loads (set down / worked in), stuck hours and weather slips, with "–" for
      null and a reason for the title;
    - `healthTitle(day)` gives "Day 66" or "Day 67 (so far)";
    - `refusalLines(day)`.
  - frontend/src/components/village/HealthPanel.tsx (new):
    - the table of days, newest first;
    - a day's detail with every number;
    - the refusals by reason, each opening the list of its turns, and each turn opening its run
      (as ChroniclePanel opens runs).
  - VillageView.tsx: a **Village health** button beside **Village projects**.

  Tests in frontend/src/lib/health.test.ts:
  - `healthRow` with full and null numbers;
  - `healthTitle`;
  - `refusalLines`.

  Screenshot of the panel on the owner's village (taken with T014). Requirement: FR-003.

## Phase 3: User Story 2 — Turn checks (P1)

- [X] T007 [P] [US2] New backend/src/agent_lab/village/evals/results.py (research §5, §8):
  - `wilson(passes, n) -> (low, high)` gives the 95% Wilson score interval (z = 1.96), or (0, 1)
    for n = 0;
  - `compare(a, b)` gives per name `better`, `worse` or `no clear change` (intervals that do not
    overlap), and points out a different model or number of repeats;
  - `open_results(path)` creates `eval_results(result_id, kind, created_at, model, settings,
    repeats, data)`;
  - `save_result`, `load_result` and `list_results`;
  - `checks_table(result)`, `scenarios_table(result)` and `compare_table(a, b)` as plain text.

  Tests in test_village_evals.py:
  - `wilson` against known values (7/10 → about 0.40–0.89; 0/10; 10/10);
  - `compare` with overlapping and separate intervals;
  - save and load round trip;
  - the tables.

  Requirements: FR-006, FR-007, SC-005.
- [X] T008 [US2] New backend/src/agent_lab/village/evals/checks.py (research §5, data-model.md
  "Turn check"):
  - `load_checks(dir)` validates every file and rejects unknown kinds.
  - `prompt_of(check, world)`:
    - decide → `observation(world, as)`;
    - plan → `plan_prompt`;
    - propose, vote, decide_meeting and work_plan → the meeting prompts;
    - frozen → the text as it is.
  - `agent_of(check, owner_world)` gives the villager's agent id, `planner_agent_id` or
    `meeting_agent_id`.
  - `judge(check, answer, world) -> (passed, why)`:
    - `action`: `parse_action` against the fixture world, or plain JSON for frozen prompts;
      every field given must match, and a refusal turned into a wait fails with "answered wait:
      <reason>";
    - `valid`: `parse_plan` or the meeting parser accepts it;
    - `tasks_include`: `parse_tasks` holds a matching task;
    - `not`: no listed pattern matches.
  - `run_checks(checks, models, owner_db, evals_db, repeats, only) -> result`:
    - copy the owner's agents by id into `evals_db` (owner database opened read-only);
    - run each check `repeats` times with `new_run(..., eval_id=result_id, villager=as)` and
      `execute_run`;
    - a failed run counts as "the run failed";
    - save the result with the model and settings.
  - `add_check(owner_db, run_id, name, expect, out_dir)` writes a frozen check holding the
    run's prompt and agent role.

  Tests in test_village_evals.py:
  - each prompt kind built with today's code (a fixture check's prompt changes when
    `observation` changes; a frozen one does not);
  - every expectation kind passing and failing;
  - `run_checks` with `FakeLLM`: passes and failures counted, `eval_id` on the runs, nothing
    written to the owner's database, the result saved;
  - `add_check` from a stored run.

  Requirements: FR-004–FR-007, FR-013.
- [X] T009 [US2] New backend/src/agent_lab/village/evals/__main__.py (contracts/interfaces.md
  "Command line", `argparse`):
  - `checks`, `add-check`, `results`, `compare` and `health` (the same numbers as the panel,
    printed for any `--db`);
  - models from `Settings`, as the app does;
  - exit status 0 when the run finished.

  Makefile: `eval-checks` (`cd backend && uv run $(ENV_FILE) python -m agent_lab.village.evals
  checks`) and `eval-scenarios`.

  Tests in test_village_evals.py: argument parsing for each command, and `health` on a scripted
  database. Requirement: FR-013.
- [X] T010 [P] [US2] backend/evals/checks/*.json, the 14 checks of research §5 ("The checks that
  ship"). All are fixtures except `proposals-valid`, which is frozen from the M12 run-E proposal
  prompt (copied into the file).

  Test in test_village_evals.py: every shipped check loads, its fixture builds, and its prompt
  holds what the situation needs (for example `load-at-site`'s prompt says "You are at the
  building site: set down your load"). Requirement: FR-012.

## Phase 4: User Story 3 — Scenarios (P2)

- [X] T011 [US3] New backend/src/agent_lab/village/evals/scenarios.py (research §6, data-model.md
  "Scenario"):
  - `load_scenarios(dir)`;
  - `CONDITIONS`:
    - `meeting_attendance {at_least}`: the meeting's `present`, Hilde included;
    - `load_at_site {goods, by}`: the trail or project shows the goods on or used at the site by
      that time;
    - `talk_then_go {pair, max_lines, within_hours}`: their conversation note has at most
      `max_lines` lines, and the trail shows both walking or working within the hours after it
      ended;
    - `built {key, by_day}`;
  - each condition returns `(held, why)`;
  - `run_scenario(scenario, models, owner_db, out_dir, repeats) -> result`. Each repeat:
    1. a fresh `out_dir/<name>-<n>.db` with the owner's agents copied and
       `build_world(start)` saved;
    2. `Village(..., move_gap=0)` and `await step()` until the horizon;
    3. a repeat is `unfinished` when the village paused with `failed_ticks` or raised;
    4. the condition, plus `day_health` for each day touched (`days_health` on the copy), and
       the chronicle entries.

  Tests in test_village_evals.py with `FakeLLM`:
  - each condition holding and not holding;
  - a scenario run makes its copies;
  - the owner's database is byte for byte unchanged (a checksum of the file before and after);
  - the horizon is respected;
  - an unfinished repeat (every call raising) is not counted;
  - health per day is in the result.

  Requirements: FR-008–FR-011, FR-014.
- [X] T012 [US3] `__main__.py`: `scenarios` (`--repeats`, `--only`), with results saved and
  `compare` working on scenario results too. backend/evals/scenarios/*.json: the 3 scenarios of
  research §6.

  Test: every shipped scenario loads and its start builds. Requirements: FR-011, FR-012.

## Phase 5: Polish

- [X] T013 Docs:
  - README.md: village health and evals; the roadmap with M13 Measuring the village done and
    M14 Better villagers next.
  - docs/village.md: a "Measuring the village" section covering the panel, checks, scenarios,
    how to read the ranges, and adding a check from a recorded turn.
  - docs/api.md: both health endpoints.
  - AGENTS.md:
    - `health.py`, `health_view.py` and `village/evals/` in the layout;
    - "real-model evals never run in `make check`";
    - the current feature.
- [ ] T014 `make check`, then quickstart.md's manual steps on the real model:
  - health on the owner's village;
  - the checks at 10 repeats, then twice at 20 with `compare`;
  - the scenarios at 5 repeats, with the owner's village row checksummed before and after;
  - the baseline of the three weakest behaviours.

  Results go in a new "Manual check results" section at the end of
  specs/013-measuring-the-village/tasks.md (SC-002–SC-006).

## Dependencies

| Task | Needs |
|---|---|
| T001 | – |
| T002 | T001 |
| T003 | – (alongside T001 and T002) |
| T004 | T002 (`trail_row` lives in `health.py`) |
| T005 | T001, T004 |
| T006 | T005 |
| T007 | – (alongside Phase 1) |
| T008 | T001, T003, T007 |
| T009 | T005, T008 |
| T010 | T003, T008 |
| T011 | T002, T003, T005, T007 |
| T012 | T009, T011 |
| T013, T014 | everything |

Stories in order:
- US1 needs only Phase 1.
- US2 needs T001 and T003; its `health` command needs US1's T005.
- US3 needs US1's `days_health` and US2's results and CLI.

## Parallel opportunities

- T003 (fixtures) and T007 (statistics and results) alongside the store and runner work of
  T001–T002.
- T010 (check files) while T009 is written.
- The frontend T006 while US2's backend starts.

## Implementation strategy

- **MVP:** Phase 1 plus US1. Village health on the live village, with no model calls and value
  from the first day.
- **Then:** the turn checks, the cheapest way to compare prompt changes, followed by the
  scenarios.
- **Last:** T014 records the baseline that M14 must beat.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | test_store.py (trail, `village_runs`); test_village_runner.py (a row per step, prune, Reset) |
| FR-002 | test_village_health.py (every number, nulls, templates) |
| FR-003 | test_village_api.py; health.test.ts; T006 screenshot |
| FR-004, FR-005 | test_village_evals.py (fixtures, prompts, frozen checks, `add_check`) |
| FR-006, FR-007 | test_village_evals.py (`run_checks`, Wilson, compare, results) |
| FR-008–FR-011 | test_village_evals.py (scenarios, conditions, copies, owner unchanged, unfinished) |
| FR-012 | test_village_evals.py (shipped checks and scenarios load and build) |
| FR-013 | test_store.py (eval runs out of the lists); CLI tests |
| FR-014, FR-015 | all of the above; `make check` (T014) |

| SC | Test / check |
|---|---|
| SC-001 | test_village_health.py (counts by hand) |
| SC-002 | test_village_health.py timing; quickstart step 1 |
| SC-003 | quickstart step 2 (real model) |
| SC-004 | quickstart step 3 (real model, checksum) |
| SC-005 | test_village_evals.py (compare); quickstart step 2 (twice at 20 repeats) |
| SC-006 | quickstart step 4 (baseline in tasks.md) |
