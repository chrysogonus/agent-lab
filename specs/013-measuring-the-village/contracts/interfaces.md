# Interface changes in M13

## HTTP API

| Endpoint | What it does |
|---|---|
| `GET /village/health?days=14` | `{"days": [DayHealth, …]}`, newest first, at most 28 days back; the day in progress has `final: false` |
| `GET /village/health/{day}/turns?reason=<template>` | the decision runs of that day whose wait reason matches the template (`<villager> is not next to you`), newest first, as `Run`s |

`DayHealth` is the shape in data-model.md. Runs with an `eval_id` never appear in
`/village/villagers/{name}/turns` or `/runs`.

## Command line

```text
uv run python -m agent_lab.village.evals checks    [--repeats 10] [--only NAME …] [--db data/agent_lab.db]
uv run python -m agent_lab.village.evals scenarios [--repeats 5]  [--only NAME …] [--db data/agent_lab.db]
uv run python -m agent_lab.village.evals add-check --run RUN_ID --name NAME --expect JSON
uv run python -m agent_lab.village.evals results   [--kind checks|scenarios]
uv run python -m agent_lab.village.evals compare   RESULT_A RESULT_B
uv run python -m agent_lab.village.evals health    [--db PATH] [--days 7]
```

- **Where things go**:
  - `--db` is the owner's database. It is only read, to copy the current agents.
  - Results and check runs go to `data/evals.db`.
  - Scenario copies go to `data/evals/<scenario>-<n>.db`.
- **The model**: the usual environment (`LLM_BASE_URL`, `LLM_MODEL`, …) chooses it. The
  Makefile targets `eval-checks` and `eval-scenarios` pass `--env-file ../.env` like `dev`.
- **Output**:
  - checks: a table with one line per check, `name  kind  passes/attempts  [low–high]`, then
    the failures with their reasons and run ids;
  - comparison: one line per check, `name  before → after  better | worse | no clear change`;
  - `health` prints the same numbers as the panel, for any database, scenario copies included.
- **Exit status**: always 0 when the run finished. An eval reports; it does not gate.
- **Errors**: an unreachable model server makes the runs fail, and they are counted as failed
  calls.

## Files in git

- `backend/evals/checks/*.json`: turn checks (data-model.md). At least 12 ship.
- `backend/evals/scenarios/*.json`: scenarios. At least 3 ship.

## UI

A **Village health** button next to **Read the chronicle** and **Village projects** opens a
panel:

- a table of the recent days (newest first): decisions, waits %, refusals, talk lines (median),
  plan kept %, trades, loads, stuck hours, weather slips. The day in progress is marked "so far",
  and missing numbers show "–" with a title explaining why;
- a day's detail, with every number and the refusals by reason (most first). Each reason opens
  the list of its turns, and each turn opens its trace.
