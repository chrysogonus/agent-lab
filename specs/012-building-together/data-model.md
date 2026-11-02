# Data Model: M12 — Building Together

The village stays one JSON row; `VERSION = 6`.

## Villager (changed field)

| Field | Type | Notes |
|---|---|---|
| `basket` | `"fish" \| "vegetables" \| "flowers" \| "wood" \| "paint" \| "saplings" \| null` | what the villager carries, one thing at a time: a basket (the first three) or a load; kept overnight |
| `working` | `{place, steps} \| null` | place gains `"site"`: building at the current project |

## World (new fields)

| Field | Type | Notes |
|---|---|---|
| `trader` | `{day, stock: {wood, paint, saplings}} \| null` | at the market from 09:00 to 14:00; stock from `trader_stock(day)`, down by one per trade |
| `meeting` | see below `\| null` | the latest meeting, kept until the next meeting day |
| `project` | see below `\| null` | the one project being built |
| `built` | `[{key, day}]` | finished projects, in order; never undone (Reset clears) |
| `meeting_agent_id` | `str \| null` | the shared "Village meeting" agent, kept across Reset |

### Meeting

```text
{day, kind: "vote" | "review",
 proposals: [{key, reason, run_id}],            # vote meetings: 1–3 catalogue keys, not built
 votes: {name: {key | null, reason, run_id}},   # key null: an invalid vote, not counted
 present: [name],                               # who came between 17:00 and 17:30
 decision: {key, reason, against: bool, by: "hilde" | "vote", run_id} | null,
 outcome: str | null}                           # "decided", "called off: …", "nothing left to build", "reviewed"
```

### Project

```text
{key,                                   # a catalogue key
 site: {wood, paint, saplings},         # loads lying at the site, not yet worked in
 used: {wood, paint, saplings},         # loads worked in, per goods
 work: int,                             # working steps toward the next load, 0–5
 tasks: [{task: "buy" | "bring" | "build", goods: str | null, villagers: [name]}],
 day: int}                              # the day it was decided
```

Still to deliver per goods: `needs[g] - site[g] - used[g]`. Progress (`done`) is `sum(used)` of
`total` = `sum(needs)`; it is finished when `used` equals `needs`. Per-goods `used` matters
because loads arrive in any order (paint first or wood first leave different needs).

## Catalogue (static, `build.py`)

`{key, name, kind: "paint" | "trees" | "stand" | "building" | "boat", needs: {goods: n},
site: [cell], at: [cell], done_text}` — ten entries, listed in research §3.

## Map

`ROWS` gains two blocked building plots, `b` (bakehouse, 14–17 × 13–14) and `r` (barn,
9–12 × 17–18). `BLOCKED` adds `b` and `r`.

## Validation

- **Buy**: `{"action": "buy", "goods": g}`. `g` must be a building good, and the trader must be
  here (`trader.day` today, 09:00–14:00) with `stock[g] > 0`. The villager must stand on a
  market cell with a basket of fish, vegetables or flowers in hand.
- **Give without a name**:
  - on the square, basket goods go onto the stalls;
  - on a site cell, a load goes on the site if `needs_left[g] > 0`;
  - anywhere else it is refused.
- **Work on a site cell**: valid while the project's site holds a load.
- **Move**: "building site" or "site" is valid while a project runs. Its cells are the project's
  `site`.
- **Proposals**: each project is matched by name or key; unknown, built and repeated ones are
  dropped; reasons are cut to 120 characters; at most 3, at least 1.
- **Vote**: names a proposal; reason ≤ 120.
- **Decision**: names a proposal; reason ≤ 120. When it is invalid, the most valid votes decide;
  with no valid votes there is no decision.
- **Tasks**:
  - 1–6 tasks;
  - `task` is one of buy, bring, build;
  - goods are a building good, required for buy and bring;
  - villagers are known names;
  - a task with nobody left is dropped.

## State transitions

```text
trader:   null --first step in [09:00, 14:00) of a day without that day's trader--> {day, stock}
          {day, stock} --buy--> stock[g] - 1
          {day, stock} --first step at or after 14:00--> null
basket:   basket goods --buy--> load (the basket leaves with the trader)
          load --give at the site (needed)--> null (project.site[g] + 1)
          load --give to a villager--> null (theirs: the load)
meeting:  meeting day, Hilde wakes, no project --valid proposals--> {kind vote, proposals}
                                             --invalid--> {outcome "called off: Hilde had no proposals"}
          meeting day, Hilde wakes, a project --> {kind review}
          17:00–17:30: present + villagers on town hall cells; each non-Hilde joiner → one vote run
          ≥ 17:30, no vote run in flight: Hilde absent → "called off: Hilde did not come"
                                          vote → decision run → decision (or vote fallback) → "decided"
                                          review → work-plan run → "reviewed"
project:  null --decision--> {key, site 0s, used 0s, work 0, tasks []} --work-plan run--> tasks
          site holds a load, workers there --6 working steps--> site[g] - 1, used[g] + 1
          used = needs --> null; built + {key, day}
```

## Villager memory

New kinds `meeting` (attendees, when the meeting ends) and `built` (everyone awake, when a project
is finished).

## Upgrade from version 5

`upgrade()` chains 2 → 3 → 4 → 5 → 6 with explicit steps. Version 6 adds `trader`, `meeting` and
`project` as null, `built` as an empty list, and `meeting_agent_id` as null. A villager standing
on a new plot cell moves to that plot's first site cell.

## Reset

`new_world()` with all of the above empty; Reset keeps `reflection_agent_id`,
`chronicler_agent_id`, `planner_agent_id` and `meeting_agent_id`.
