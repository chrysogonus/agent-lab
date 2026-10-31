# Data Model: M7 — Village Life

## Map (constant, `village/world.py`)

| Field | Value |
|---|---|
| size | 32 × 22 cells, (x, y) with x 0–31, y 0–21 |
| walkable | `.` grass, `=` path, place letters `T S M P F G` |
| not walkable | `~` water, `B` town hall building, `h j g l` houses, `t` tree, `i` lamp |
| places | as M6: `town_hall`, `square`, `market`, `pier`, `fields`, `flower_garden` |
| homes | Hilde `h`, Jonas `j`, Greta `g`, Lina `l`; door = the cell below the middle of the house's bottom row, walkable |

## Character (constant)

| Field | Rule |
|---|---|
| `wake`, `bed` | minutes of the day: Jonas 05:00/21:00, Greta 05:30/21:30, Lina 06:30/22:00, Hilde 07:30/23:00 |
| `routine` | `[(from_hour, place)]` for its waking hours, e.g. Jonas `[(5, pier), (11, market), (14, pier)]` |
| others | as M6 (name, title, color, initial, work place, persona) |

## World (one row in table `village`, JSON)

| Field | Rule |
|---|---|
| `version` | `2`; anything else is replaced by a new world on load |
| `tick` | step number ≥ 0; minutes = 270 + 10·tick (day 1, 04:30) |
| `running`, `interval`, `paused_reason`, `failed_ticks` | as M6 (`failed_ticks` counts steps whose finished decisions all failed) |
| `villagers` | the four villagers below |
| `conversations` | `[{a, b, lines, last_tick}]`, one per talking pair |
| `talked_out` | `[[a, b]]` pairs that reached 10 lines and have not been apart since |
| `log` | last 8 lines said in the village: `{tick, from, to, text}` |

## Villager

| Field | Rule |
|---|---|
| `name`, `agent_id`, `x`, `y`, `last_action`, `inbox`, `events` | as M6 (`events`: last 10) |
| `asleep` | bool; asleep villagers stand at their door, hidden |
| `bedtime` | bool; walking home to sleep, no decisions |
| `goal` | null, `{"kind": "place", "place"}`, `{"kind": "home"}`, `{"kind": "find", "villager", "target": [[x, y], …]}` |
| `triggers` | reasons to decide since its last decision: `woke`, `arrived`, `met`, `spoken to`, `found`, `missed`, `conversation ended` |
| `last_decided` | tick of its last decision start |
| `neighbours` | names adjacent at the last check (to detect new meetings) |
| `beliefs` | `{other: {where, cell, tick, source: seen|heard, from?}}`; `where` a place key, `home` or null (outside places) |
| `speech` | the last line it said, `{text, to, tick}`, or null |

## Action (parsed from a decision's answer)

| `action` | Fields | Valid when | Effect |
|---|---|---|---|
| `move` | `place`: a place key/label or `home` | not already there | goal set; ends its conversations ("walked away") |
| `find` | `villager`: another first name | not already adjacent | goal `find`; ends its conversations |
| `say` | `text` (not empty), `to` optional | an awake neighbour (the addressee if given); pair not talked out | line delivered; conversation created or extended |
| `goodbye` | `text` optional | – | the line (if any) is said, then its conversations end |
| `wait` | – | – | nothing |

Invalid answer, failed check or failed run → `wait` with the reason (as M6).

## Event kinds

`woke`, `bedtime`, `slept`, `set_off`, `arrived`, `met`, `found`, `missed`, `heard`, `said`,
`ended` (a conversation, with the reason), `waited`.

## Runtime only (not stored)

- `decisions`: villager → asyncio task in flight; `ticking`: a step holds the step lock;
  `deciding`: names with a decision in flight (exposed in the state).

## State transitions (villager)

```text
asleep --wake time--> idle (at its door, trigger woke)
idle --move/find--> walking --arrive/found/missed--> idle
idle/walking --say or spoken to--> talking --goodbye/walk/apart/silence/10 lines--> idle
any awake --bedtime--> going to bed --at door--> asleep
any awake --trigger--> deciding (stands still) --answer applied--> per action
```
