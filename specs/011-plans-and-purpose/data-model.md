# Data Model: M11 — Plans and Purpose

The village stays one JSON row; `VERSION = 5`.

## Villager (new fields)

| Field | Type | Notes |
|---|---|---|
| `plan` | `{day, entries: [{minute, place, villager, purpose}], revisions} \| null` | 2–6 entries sorted by minute; exactly one of `place` (place key or `"home"`) and `villager` (first name, not itself); purpose ≤ 120 chars; revisions 0–2; only today's plan counts |
| `basket` | `"fish" \| "vegetables" \| "flowers" \| null` | one at a time, kept overnight |
| `working` | `{place, steps} \| null` | place: `fields`, `flower_garden` or `pier`; steps worked since its last basket |
| `said` | `[str]` | its last 3 lines as spoken, oldest first |

## World (new fields)

| Field | Type | Notes |
|---|---|---|
| `stalls` | `{fish: int, vegetables: int, flowers: int}` | goods set out for the festival; cleared when winter starts |
| `harvest` | `{pier: int, fields: int, flower_garden: int}` | working steps toward the next basket, 0–6; 0 while the place has no goods |
| `planner_agent_id` | `str \| null` | the shared "Village planner" agent, kept across Reset |

`tended` (M10) keeps its shape but now counts working steps of every worker, not steps with
someone standing on the place.

## Validation

- Plan answer: `{"plan": [{"time", "place"?, "villager"?, "purpose"}]}`; entries with a bad time,
  an unknown place and villager, or an empty purpose are dropped; > 6 cut to the first 6 by
  time; < 2 → invalid.
- Work: fields and garden for anyone; pier for Jonas or anyone while Jonas works there.
- Give: needs a basket; to an awake villager next to the giver with empty hands, or without a
  name on the square onto the stalls.
- A say repeating one of the speaker's `said` (case, spaces and punctuation ignored) → wait.

## State transitions

```text
working:  null --work (valid place)--> {place, steps 0}
          {place} --move | find | goodbye with place/villager | bedtime--> null
          say, wait, give: unchanged
basket:   null --6 working steps added up at a place with goods, longest worker--> goods
          goods --give to a villager--> null (theirs: goods)
          goods --give on the square--> null (stalls[goods] += 1)
plan:     null --valid plan on waking--> today's plan
          plan --conversation ≥ 4 lines, revisions < 2--> revised plan (revisions + 1)
          invalid answer: unchanged; a new day: yesterday's plan no longer shown
```

## Villager memory

Festival memories name the stalls' goods. No new memory kinds.

## Upgrade from version 4

`upgrade()` chains 2 → 3 → 4 → 5. Version 5 adds the fields above: no plans, empty hands, not
working, nothing said, empty stalls, harvest 0s, `planner_agent_id` null.

## Reset

`new_world()` with the new fields empty; Reset keeps `reflection_agent_id`,
`chronicler_agent_id` and `planner_agent_id`.
