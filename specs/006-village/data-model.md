# Data Model: M6 — The Village

## Map (constant, `village/world.py`)

| Field | Value |
|---|---|
| size | 20 × 15 cells, (x, y) with x 0–19, y 0–14 |
| cells | text rows: `.` grass, `=` path, `~` water (not walkable), `T S M P F G` place cells |
| places | `town_hall` (T), `square` (S), `market` (M), `pier` (P), `fields` (F), `flower_garden` (G), each with a label ("town hall", …) |

## World (one row in table `village`, JSON)

| Field | Rule |
|---|---|
| `tick` | integer ≥ 0; clock derived from it (research §4) |
| `running` | bool; false after load, reset, pause and self-pause |
| `ticking` | bool, not stored; true while a tick holds the tick lock |
| `interval` | seconds between tick starts, 1–30, default 5 |
| `paused_reason` | null, `"owner"`, `"no viewer for 60 s"`, `"every turn failed 3 ticks in a row"` |
| `failed_ticks` | consecutive ticks in which every turn failed |
| `villagers` | the four villagers below, in a fixed order |

## Villager

| Field | Rule |
|---|---|
| `name` | `Hilde`, `Jonas`, `Greta`, `Lina` (first name; unique, used as `to`) |
| `title` | "Mayor Hilde", "Jonas the fisher", "Greta the farmer", "Lina the flower girl" |
| `color`, `initial` | per villager; initials H, J, G, L |
| `home` | place key |
| `agent_id` | the block agent that plays it (null until first start) |
| `x`, `y` | a walkable cell |
| `destination` | place key or null |
| `last_action` | `{"action", …}` and, if it became `wait`, the reason |
| `speech` | `{"text", "to"}` said this tick, or null (shown as a bubble) |
| `inbox` | speech heard since its last turn: `{"from", "to", "text", "tick"}` |
| `events` | last 10 `{"tick", "kind": arrived|heard|said|waited, "text", "from"?, "to"?}` |

## Action (parsed from a turn's answer)

| `action` | Fields | Effect |
|---|---|---|
| `move` | `place`: one of the six keys or labels | sets the destination; the villager walks one cell per tick; already there → `wait` ("already at the market") |
| `say` | `text`: not empty after trimming, any length; `to`: another villager's first name, optional | heard by everyone nearby at the start of the next tick; shown cut to 200 characters |
| `wait` | – | nothing |

Invalid answer, failed `answer-is-json` check or failed run → `wait` with the reason.

## Run (existing table, three new columns)

- `village_tick INTEGER NULL`: the tick a villager turn belongs to; null for every other run.
- `villager TEXT NULL`: the villager's first name; turn history is queried by it, so a reset that
  replaces a deleted agent keeps the villager's earlier turns listed.
- `village_action TEXT NULL` (JSON): the action applied for this turn, and the reason when it
  became `wait`; written when the tick is applied.
- `GET /runs` lists only rows with `village_tick IS NULL`.
- Prompt = the observation; answer = the model's JSON text.

## State transitions

```text
paused --start--> running --pause / self-pause--> paused
paused --step--> (one tick) --> paused
any --reset--> paused, tick 0, villagers at home, inboxes and events empty
backend start --> paused (state loaded)
```
