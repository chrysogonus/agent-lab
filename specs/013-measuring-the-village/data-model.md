# Data Model: M13 — Measuring the Village

## World (new key, no version bump)

| Field | Type | Notes |
|---|---|---|
| `born` | `float` (wall-clock seconds) | set by `new_world()` and by Reset; a world without it counts every run (`get("born", 0)`) |

## Store

### `runs` (new column)

| Column | Type | Notes |
|---|---|---|
| `eval_id` | `TEXT NULL` | set on runs made by a turn check; `list_turns` and `list_runs` leave them out |

There is also a new index `runs_by_tick ON runs(village_tick)`.

### `village_trail` (new table)

| Column | Type | Notes |
|---|---|---|
| `tick` | `INTEGER PRIMARY KEY` | one row per step, written at the end of `_advance` |
| `row` | `TEXT` (JSON) | `{"v": [[name, x, y, place, state, carrying], …], "project": key \| null, "used": int}` |

Rows older than 28 village days are pruned when a day record opens; Reset clears the table.

### `eval_results` (new table, in `backend/data/evals.db`)

| Column | Type | Notes |
|---|---|---|
| `result_id` | `TEXT PRIMARY KEY` | |
| `kind` | `"checks" \| "scenarios"` | |
| `created_at` | `REAL` | |
| `model` | `TEXT` | provider and model of the agents run |
| `settings` | `TEXT` (JSON) | reasoning on or off, the source database |
| `repeats` | `INTEGER` | |
| `data` | `TEXT` (JSON) | below |

## Day health (computed, `village/health.py`)

```text
{day, final: bool, trail: bool,                     # trail: positions were recorded that day
 decisions: int, waits: int, failed_calls: int,
 calls: {decision, plan, reflect, chronicle, meeting: int},
 refusals: [{reason: "<villager> is not next to you", count}],   # most first
 conversations: {count, lines: [int], median_lines},
 repeated_lines: int,
 plan_adherence: {kept, entries} | null,
 meeting: {present: [name], votes: int, outcome: str} | null,
 trades: int, loads_set_down: int, loads_worked_in: int | null, load_minutes: int | null,
 given_back: int,
 weather_slips: [kind] | null,                      # null before the chronicle is written
 stuck_hours: float | null}
```

A day with no runs counted is left out. `null` always means the source was missing that day,
never zero.

## Fixture (JSON, `village/evals/fixtures.py`)

```text
{day: int, time: "HH:MM",
 villagers: {Name: {at: place | "home" | "site" | [x, y], asleep?, carrying?, working?,
                    goal?: place | "home" | "site", memories?: [str], learnings?: [str],
                    inbox?: [{from, text}], said?: [str], plan?: [{time, place|villager, purpose}],
                    events?: [str]}},
 conversations?: [[a, b, lines]],
 trader?: true | {wood, paint, saplings},
 project?: {key, site?: {...}, used?: {...}, tasks?: [...]}, built?: [key],
 meeting?: {kind, proposals: [{key, reason}], votes?: {...}, present?: [...]},
 stalls?: {...}, growth?: {fields, flower_garden}}
```

Villagers not named are asleep at home. Unknown keys, places or goods are an error.

## Turn check (JSON file, `backend/evals/checks/<name>.json`)

```text
{name, agent: "villager" | "planner" | "meeting", as?: Name,
 situation: {fixture: Fixture, prompt: "decide" | "plan" | "propose" | "vote" |
                                       "decide_meeting" | "work_plan"}
          | {frozen: str, from_run?: run_id},
 expect: {action: {...}} | {valid: true} | {tasks_include: {...}} | {not: [{...}]}}
```

Each attempt passes or fails with a reason: "answered wait: …", "gave to Hilde, not set down",
"not valid: …", "the run failed".

## Check result data

```text
{checks: [{name, kind: "fixture" | "frozen", passes, attempts,
           interval: [low, high], failures: [{run_id, answer, why}]}],
 overall: {passes, attempts, interval}}
```

## Scenario (JSON file, `backend/evals/scenarios/<name>.json`)

```text
{name, start: Fixture, horizon: {until: "HH:MM"} | {hours: int}, repeats?: int,
 condition: {kind: "meeting_attendance", at_least}
          | {kind: "load_at_site", goods, by: "HH:MM"}
          | {kind: "talk_then_go", pair: [a, b], max_lines, within_hours}
          | {kind: "built", key, by_day}}
```

## Scenario result data

```text
{scenarios: [{name, held, finished, attempts, interval,
              runs: [{db, held: bool | null, why, finished: bool, health: [DayHealth],
                      chronicle: [{day, title, text}]}]}]}
```

## Comparison

For each check or scenario in both results, `better` / `worse` when the 95% intervals do not
overlap, else `no clear change`. The settings of both results are shown, and a difference in
model or repeats is pointed out.
