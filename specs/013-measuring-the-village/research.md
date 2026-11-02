# Research: M13 — Measuring the Village

## 1. Where the numbers come from

- **Decision**: village health is computed on request from three sources.
  1. **Runs.** They are already stored, with `village_tick`, `villager`, `status` and
     `village_action`. Each run's day comes from its tick; for a chronicle run it comes from
     `village_action.day`.
  2. **Notes.** The happenings of a day:
     - for a finished day, they are the items in that night's chronicle run prompt (the run
       stores its prompt);
     - for the day in progress, they are `world["day_record"]`.
  3. **The day trail.** This is new (§2) and holds positions and states between decisions.
- **Runs counted**: only runs started at or after `world["born"]` count. `born` is a new key:
  - `new_world()` sets it to the wall-clock time;
  - Reset and fresh worlds get a new `born`, so health "starts again from day 1";
  - an existing world without the key counts all runs (`world.get("born", 0)`).

  This needs no world-version bump.
- **Why**:
  - no extra model calls (spec assumption);
  - the chronicle prompt already holds every note of a finished day (trades, deliveries,
    meetings, talks with their lines, finished projects);
  - `born` keeps a reset village, or a scenario copy that holds the owner's runs, from counting
    old runs.
- **Alternatives**:
  - a stored health table written at night — rejected, because it would have to be migrated
    whenever a number changes; computing is cheap (§7);
  - a run column for the village's epoch — rejected as a schema change for what one timestamp
    does.

## 2. The day trail (FR-001)

- **Decision**: a new table `village_trail(tick INTEGER PRIMARY KEY, row TEXT NOT NULL)`.
  - At the end of every `_advance` the runner writes one row, as compact JSON:
    `{"v": [[name, x, y, place|null, state, carrying|null], …], "project": key|null,
    "used": n}`. Here `state` is `_state_of` (asleep, bedtime, deciding, talking, working,
    walking, idle) and `used` is the number of loads worked in so far.
  - That is 144 rows of about 300 bytes per village day.
  - Rows older than 28 village days are deleted once a day, when the day record opens.
  - Reset deletes every row. `INSERT OR REPLACE` covers a restarted tick.
  - Store methods: `add_trail(tick, row)`, `trail(first_tick, last_tick)`, `clear_trail()`,
    `prune_trail(before_tick)`.
- **Why**:
  - plan adherence and time stuck need where everyone was between decisions;
  - the village keeps only its current state, villagers' last ten events and the decision
    prompts, which show where a villager was only when it decided.
- **Before M13**: days without trail rows mark these numbers unavailable (`None`), never 0:
  plan adherence, stuck hours, loads worked in and load times.

## 3. The numbers (FR-002, `village/health.py`, pure)

`day_health(day, runs, notes, trail, chronicle, final) -> dict`; every number is `None` when its
source is missing.

| Number | Source and rule |
|---|---|
| `decisions`, `waits` | runs with a villager whose action is a decision kind (move, find, say, goodbye, work, give, buy, wait); waits are `wait`, and turns that failed are counted under `failed_calls` instead |
| `refusals` | waits with a reason, grouped by the reason with villager names replaced by `<villager>` and goods by `<goods>` ("<villager> is not next to you") |
| `conversations` | notes "A and B talked; what they said (their claims): …": count and lines per talk (the transcript joined by " / ") |
| `repeated_lines` | waits with "you already said that" |
| `plan_adherence` | each plan entry in effect is the last plan run for that villager before the entry's time. An entry is kept when, between its time and one hour after it, the trail has the villager at its place (by label) or next to the villager it names. Reported as kept / entries. Trail needed |
| `meeting` | notes: who came, votes, the decision or how it ended; null on days without one |
| `trades` | applied buy actions |
| `loads_set_down`, `loads_worked_in` | applied give-at-site actions; the trail's `used` rising |
| `load_minutes` | per load, from the buy to the villager setting that goods down; the median. Trail needed for days before M13 to be left out |
| `given_back` | gives A→B followed by B→A of the same goods the same day, plus refusals "just gave you this" |
| `weather_slips` | `weather_slips(title + text, weather(day))` of the day's chronicle entry (chronicle.py) |
| `stuck_hours` | villager-hours awake, not working, on the same cell and in the same state for 6+ steps. Trail needed |
| `calls` | runs per kind: decision, plan, reflect, chronicle, meeting (propose, vote, decide, assign); plus `failed_calls` (status not completed) |

- **Why**: each number answers one of the M12 findings (waits, talk refusals, wrong work,
  handing to Hilde, stale plans, weather slips). Grouping by templated reasons keeps 30
  "Hilde is not next to you" and 20 "Jonas is not next to you" as one problem.

## 4. Fixtures: a village from a few lines (`village/evals/fixtures.py`)

- **Decision**: one JSON format describes a starting village, shared by turn checks and
  scenarios. `build_world(fixture) -> world` starts from `new_world()` and applies:
  - `day`, `time`;
  - per villager:
    - `at`: a place key, "home", "site" or `[x, y]`;
    - `asleep`, `carrying`, `working`, `goal`;
    - `memories` and `learnings` as texts;
    - `inbox` lines, `events`, `said` and `plan`;
  - `conversations` (pairs with lines so far);
  - `trader: true` (that day's stock) or an explicit stock;
  - `project` (key, site, used, tasks) and `built`;
  - `meeting` (kind, proposals, votes, present);
  - `stalls` and `growth`.

  Unknown keys are an error.
- **Why**:
  - a world fixture is rebuilt by today's code (spec FR-004/FR-005), so a check sees prompt
    changes;
  - one format for checks and scenarios keeps them small and readable;
  - the scratch-world scripts of the M12 checks (`setup12.py`) were exactly this, by hand.

## 5. Turn checks (`village/evals/checks.py`)

- **Decision**: one JSON file per check in `backend/evals/checks/` (in git). A check has:
  - `name`;
  - `agent`: `villager` (with `as`, the name), `planner` or `meeting`;
  - `situation`, either:
    - `{"fixture": {…}, "prompt": "decide" | "plan" | "propose" | "vote" | "decide_meeting" |
      "work_plan"}`, which builds the prompt with today's `observation` / `plan_prompt` /
      meeting prompts; or
    - `{"frozen": "<the prompt>", "from_run": run_id | null}`;
  - `expect`, one of:
    - `{"action": {...fields}}` — the answer, parsed against the fixture's world with
      `parse_action` (frozen prompts: decoded JSON only), matches every field given; a wanted
      "wait" must be asked for explicitly;
    - `{"valid": true}` — the planner or meeting parser accepts it;
    - `{"tasks_include": {...}}` — a work plan holds such a task;
    - `{"not": [{...}, …]}` — none of these.

  `add-check` writes a frozen check from a recorded run (its prompt and agent).
- **Running**: each check is run `repeats` times, as ordinary runs through `new_run` /
  `execute_run` with `villager` set and a new run column `eval_id`.
  - `list_turns` and `list_runs` leave runs with an `eval_id` out (FR-013).
  - Checks run against a separate database, `backend/data/evals.db`. Its agents are copied
    from the owner's database at the start of every run by id (the villagers', planner and
    meeting agent ids are read from the owner's world), so the owner's prompts are tested and
    the owner's history stays clean.
- **Stats**:
  - each pass rate comes with a Wilson 95% interval (by hand, no dependency);
  - a comparison marks a check `better` / `worse` only when the two intervals do not overlap,
    else `no clear change`.

  Two non-overlapping 95% intervals mean p well below 0.05, so an unchanged suite of 14 checks
  flags fewer than 1 by chance (SC-005).
- **Alternatives**:
  - a pytest plugin — rejected: the real model must stay out of the gates (constitution V);
  - a two-proportion z-test — about as long, but its normal approximation is poor at small n
    and near 0% or 100%;
  - temperature 0 for steadier answers — rejected: the village runs at its default sampling,
    and checks should measure that.

### The checks that ship (14, all fixtures unless marked)

Each line names the check, the situation it sets up, and the expected answer.

| # | Name | Situation → expected |
|---|---|---|
| 1 | `load-at-site` | carrying a needed load at the building site → give, no name |
| 2 | `load-away` | carrying a needed load at its door → move to the building site |
| 3 | `meeting-call-talking` | talking with Lina, just called to the meeting → goodbye, place the town hall |
| 4 | `meeting-call-far` | Hilde at the fields at 16:40 on a meeting day → move to the town hall |
| 5 | `answer-the-speaker` | Greta just spoke to Jonas → say, to Greta |
| 6 | `buy-saplings` | at the market with a basket, trader there, the trees need saplings → buy saplings |
| 7 | `build-with-loads` | at the site holding saplings → work |
| 8 | `stalls-in-autumn` | on the square in autumn with fish → give, no name |
| 9 | `talked-out` | a long talk, told so → goodbye |
| 10 | `not-to-hilde` | carrying wood next to Hilde, the site elsewhere → not give to Hilde |
| 11 | `work-at-own-place` | Greta at the ripe fields in the morning, nothing else on → work |
| 12 | `plan-valid` | the planner on a meeting day → valid plan |
| 13 | `work-plan-buys` | Hilde's work plan for the trees → tasks include buy saplings |
| 14 | `proposals-valid` (frozen, from run E's failed proposal prompt) | → valid proposals |

## 6. Scenarios (`village/evals/scenarios.py`)

### The scenarios that ship

| Name | Start | Horizon | Condition |
|---|---|---|---|
| `meeting-attendance` | day 66 at 16:00, proposals made, everyone at work | until 18:40 | `meeting_attendance {at_least: 3}` |
| `load-reaches-site` | day 67 at 10:00, trees decided with "buy saplings: Lina", Lina at the market with flowers, trader there | until 12:00 | `load_at_site {goods: saplings, by: 12:00}` |
| `talk-then-go` | day 67 at 10:00, Jonas and Greta meet on the path, both with plans | 2 hours | `talk_then_go {pair: [Jonas, Greta], max_lines: 6, within_hours: 1}` |


- **Decision**: one JSON file per scenario in `backend/evals/scenarios/`, holding `name`,
  `start` (a fixture), `horizon` (`{"until": "18:30"}` or `{"hours": 26}`), `condition` and
  `repeats` (default 5). Each condition is a named kind with parameters, evaluated on the run:
  - `meeting_attendance {at_least: 3}`;
  - `load_at_site {goods: "saplings", by: "12:00"}`;
  - `talk_then_go {pair: [a, b], max_lines: 6, within_hours: 1}` (the talk ended with at most 6
    lines, and both were walking or working within an hour of the meeting);
  - `built {key, by_day}`.

  A new condition kind is a small function plus a test.
- **Running**: each repeat:
  1. a fresh file `backend/data/evals/<scenario>-<n>.db`, holding the owner's agents (copied as
     in §5) and `build_world(start)` with a new `born`;
  2. `Village(store=…, models=…, bus=Bus(), move_gap=0)`;
  3. `await village.step()` until the horizon. Step settles every decision, so no real-time
     waiting happens, and runs are as deterministic as the model allows;
  4. the condition, and `day_health` for every day touched.

  A repeat whose village paused (`failed_ticks`) or raised is recorded as `unfinished`. The
  owner's database is opened read-only to copy agents.
- **Why**:
  - Step is the existing deterministic driver;
  - copies are what the M12 checks did by hand (spec FR-009);
  - the files stay for inspection with the runs' traces;
  - a later `make dev` on such a file shows the run in the UI.

## 7. Speed (SC-002)

- **Decision**: health reads only small columns (`villager`, `village_tick`, `status`,
  `village_action`, and `started_at` for `born`) for the requested days, plus one chronicle
  prompt per day. A new index `runs(village_tick)` helps.
  - The owner's database holds about 8,000 runs, which is about 250 a day.
  - Finished days are cached in memory by `(born, day)`.
- **Why**: it is well under a second without a stored table.

## 8. Where results live and how the owner sees them

- **Decision**:
  - **Check and scenario results** go in `evals.db`, table
    `eval_results(result_id, kind, created_at, model, settings, repeats, data)`. They are listed
    and compared on the command line: `uv run python -m agent_lab.village.evals …`, with
    `make eval-checks` and `make eval-scenarios` as shortcuts.
  - **Village health** goes in the UI, in a **Village health** panel next to the chronicle:
    - a table of the last days with the main numbers (the day in progress marked);
    - a day's detail with every number and the refusals by reason;
    - each reason opens its turns.
- **Why**: the spec keeps evals on the command line for this milestone. Health belongs to the
  village the owner watches.
