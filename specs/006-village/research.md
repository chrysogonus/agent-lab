# Research: M6 — The Village (first slice)

Decisions inside the existing stack; no new dependencies (see §8).

## 1. A villager turn is an ordinary run

- **Decision**: each turn calls the existing `runs.new_run` / `runs.execute_run` with the
  villager's agent id and the observation as the prompt, awaited directly by the tick (not via
  `POST /runs`). The answer is read back from the stored run and parsed into an action. `runs`
  gains a nullable `village_tick INTEGER` column (added in place like the M3 columns);
  `new_run` takes an optional `village_tick`.
- **Rationale**: tracing, redaction, `config_version`, the model choice and run replay all work
  unchanged (FR-011, FR-013: the agent is resolved from the store on every turn, so an edit
  applies from the next tick). The column lets the main list exclude village turns (FR-012) and
  the village list them per villager.
- **Alternatives**: a separate turn table with its own spans (duplicates tracing); calling the
  model directly (loses the trace, violates Principle II).

## 2. The villager's agent

- **Decision**: on first start the village creates one block agent per villager (M5), named
  after it ("Mayor Hilde", …; a free name with " (village)" appended if taken), and stores the
  agent ids in the world. Layout: model block `decide` (system = persona + world rules + the
  action format; message `{previous}`, i.e. the observation) followed by check `answer-is-json`
  (`valid_json`). Reset recreates agents that were deleted.
- **Action format** (the model answers with exactly one JSON object):
  `{"action": "move", "place": "market"}`, `{"action": "say", "text": "…", "to": "Jonas"}`
  (`to` optional), `{"action": "wait"}`. The village validates it with a pydantic `Action`
  union: place one of the six, text 1–500 characters (cut to 200 when shown and heard), `to` one
  of the other three villagers' first names. Anything else, a failed check or a failed run →
  `wait` with the reason (FR-008, FR-016).
- **Rationale**: the owner can open and edit any villager in the builder like any block agent;
  the check makes unreadable answers visible in the trace.
- **Alternatives**: structured output via `decide` (only decision blocks request a schema;
  adding a schema to model blocks is a new block feature, deferred); hard-coded prompt in Python
  (not editable, against the lab's purpose).

## 3. The map

- **Decision**: a fixed 20 × 15 map written as text rows in `village/world.py`:
  `.` grass, `=` path, `~` water, and one letter per place: `T` town hall, `S` square,
  `M` market, `P` pier, `F` fields, `G` flower garden. Every cell but water is walkable; a
  place is the set of its letter cells. Movement: breadth-first search on the 4-neighbour grid
  to the nearest cell of the destination place, one cell per tick (FR-009). "Nearby" (spec
  assumption): the same place, or within 3 cells (Chebyshev distance) outside places. Homes:
  Hilde town hall, Jonas pier, Greta fields, Lina flower garden.
- **Rationale**: readable, diffable, and the map is tested like data.

## 4. Clock

- **Decision**: tick `t` → minutes = 360 + 10·t; day = 1 + minutes // 1440; time of day:
  05:00–11:00 morning, 11:00–14:00 midday, 14:00–18:00 afternoon, 18:00–22:00 evening, otherwise
  night. Villagers keep acting at night (their personas may choose to wait at home).

## 5. The tick and the loop (`village/runner.py`)

- **Decision**: `tick()` = build every villager's observation from the state at the start of
  the tick → run the four turns with `asyncio.gather` → parse actions → apply all together
  (moves, then speech delivered into the hearers' inboxes and events) → advance the clock →
  store the world → publish the new state. A `Village` object owns one asyncio task while
  running: tick, then sleep the remainder of the interval (never overlapping, FR-007). Pause
  sets a flag checked between ticks; Step runs one tick when paused.
- **Self-pause** (FR-010): after 3 consecutive ticks where every turn failed; and when no
  Village view has been connected for 60 s (the WebSocket count, with a timestamp of the last
  disconnect). The world stores why it paused.
- **Restart**: the world loads paused from the database (US1-5).
- **Rationale**: one owner, one world; an in-process task is the smallest loop that the server
  controls.

## 6. Observations

- **Decision**: plain text, built in `village/turn.py`:

  ```text
  Day 1, 07:20, morning. You are at the market.
  Nearby: Jonas the fisher.
  Places: town hall 6 steps north-west, square 3 steps west, … (steps by shortest path)
  Heard since your last turn:
  - Jonas to you: "Fresh fish today!"
  Your last events:
  - 07:10 You arrived at the market.
  What do you do? Answer with one JSON object.
  ```

  Persona, rules and the action format live in the agent's system prompt (editable); the
  observation carries only the changing world state.

## 7. Storage

- **Decision**: table `village` with one row (`id = 1`, `state` JSON: tick, running flag,
  interval, pause reason, failed-tick count, villagers with agent id, position, destination,
  last action, speech, inbox, last 10 events). Written after every completed tick, on control
  changes and on reset. Turns are runs (§1).
- **Alternatives**: a row per tick (history for forks; out of scope).

## 8. Drawing the map without a dependency

- **Decision**: SVG rendered by React: one `<rect>` per cell (colors from the theme), place
  labels, villagers as `<g>` buttons (circle in the villager's color, initial, name below,
  `tabIndex`, `aria-label`), speech as a bubble above the figure; moves animate with a short CSS
  transition (off under `prefers-reduced-motion`).
- **Rationale**: 300 cells and four figures are well within SVG; it is accessible and testable
  and needs no library. The constitution reserves PixiJS for Phase 2, it does not require it; the
  owner is not asked for a new dependency (repo rule).
- **Alternatives**: PixiJS canvas (a dependency for a static grid; less accessible).

## 9. Streaming

- **Decision**: `WS /village/stream` sends `{"type": "state", "state": …}` on connect and after
  every tick and control change, plus `{"type": "tick_started", "tick": n}`; turns in progress
  stream through the existing `/runs/{id}/stream` when opened. Same Origin check as the run
  stream. The connection count feeds the self-pause.
