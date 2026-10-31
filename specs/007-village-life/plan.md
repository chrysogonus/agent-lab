# Implementation Plan: M7 — Village Life

**Branch**: `main` (feature directory `007-village-life`) | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-village-life/spec.md`

## Summary

The M6 `village/` package grows instead of being replaced. `world.py` gets a 32 × 22 map with
four houses, trees and lamps as cells, each villager's sleeping hours and usual routine, and a
clock that starts at 04:30. The runner splits M6's tick into two independent parts: a **step
loop** that advances the clock 10 minutes, wakes and beds villagers, and walks every walker one
cell (one walker at a time, published after each move, spread over the step); and **decisions**
that run in the background per villager, started only by a trigger (woke, arrived, met, spoken
to, found, missed, idle for 30 minutes) and applied the moment they finish. Speech only reaches
awake villagers next to the speaker; conversations hold both villagers in place and end on
goodbye, walking away, sleep, silence or 10 lines. Each villager keeps beliefs about where the
others are (seen within 6 cells, heard, or routine). Every decision is still an M6 turn: a
traced run of the villager's block agent. The UI draws the new map elements (town hall
building cells, houses, trees, lamps), sleeping villagers, thinking and talking marks, a rolling
speech log, and each villager's sleeping hours and beliefs.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged; no new dependencies

**Storage**: the M6 `village` row (JSON) with a new state shape (`version: 2`); runs columns
unchanged (`village_tick` now holds the step a decision started in)

**Testing**: pytest with `FakeLLM` (callables answer per villager, as in M6) and a runner hook
that sets the move spacing to 0; vitest for the new view logic

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: a whole night with everyone asleep passes in under 15 s (SC-004); no
model call per walking step (SC-005)

**Constraints**: decisions are traced runs on their agent's graph; steps never overlap; at most
one decision per villager in flight; no unwatched running for more than 60 s

**Scale/Scope**: one world, four villagers, 704 cells, a step every 1–30 s

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | The same small modules (`world`, `turn`, `runner`), BFS by hand, no game engine or scheduler library |
| II. Observable by default | Pass | Every decision is a normal run of the villager's block agent (spans on its graph, stored, streamed), tagged with its step; world changes are in the stored state and the stream |
| III. Secure local defaults | Pass | Same Host/CORS/Origin checks; model output is parsed into a validated action, never executed; speech capped at 200 characters; redaction of decoded actions kept |
| IV. Smallest change | Pass | Extends the M6 package, store, API and view; the tick-driven runner seam is the one being used; no new abstraction beyond what the spec needs |
| V. Gates + traceability | Pass | `make check` unchanged; FR → test map in `tasks.md` |

Post-design re-check: passes; no Complexity Tracking entries.

## Design

Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md).

### `backend/src/agent_lab/village/`

- `world.py`: the new `ROWS` (32 × 22; `B` town hall building, `h j g l` houses, `t` trees,
  `i` lamps: none walkable), `HOMES` (owner → letter, door cell), the clock from 04:30,
  `Character` gains `wake`, `bed` and `routine` (hour → place), `usual_place(name, minute)`,
  `adjacent(a, b)` (same or neighbouring cell, diagonals included), `sees(a, b)` (within 6
  cells), BFS to a list of target cells (place cells, a door, a cell), `new_world()` with
  everyone asleep at home.
- `turn.py`: the new observation (FR-015), actions `move` (a place or `home`), `find`, `say`,
  `goodbye`, `wait`, validated against the current world (adjacency, known names), the heard-
  place rule for beliefs, the updated rules text in the villager's agent.
- `runner.py`: `Village.step()` (clock, sleep schedule, staggered moves, sightings, meetings,
  conversation upkeep, start decisions), background `_decide(villager)` tasks applied on
  completion, `_loop()` with the fast night, Step = one step plus awaiting its decisions, Pause,
  Reset (waits for decisions in flight and discards them), the failure self-pause counted per
  step, a fresh start from an M6 world.

### Existing code

- `store.py`, `runs.py`: unchanged (turns keep `village_tick`, `villager`, `village_action`).
- `api.py`: same endpoints; the stream adds `decision_started` (replacing `turn_started`, same
  fields) and drops `tick_started`; `VillageState` grows (contract).

### UI

- `lib/api.ts`: the new `VillageState` fields.
- `lib/village.ts` (pure, vitest): `stateText`, `beliefLines`, `sleepText`, the speech log for
  the dialog box, home areas from the map.
- `components/village/pixels.tsx`: town hall from `B` cells, a house sprite per home (roof in its
  owner's color), trees and lamps from map cells (the hard-coded lists go), "Zz" over a sleeping
  villager's house.
- `VillageView.tsx`: hide sleeping villagers, a thinking mark while deciding, the talk bubble for
  a fresh line, the dialog box from the log (newest at the bottom); list rows with the state.
- `VillagerPanel.tsx`: sleeping hours and "Thinks the others are" (beliefs).

## Project Structure

### Documentation (this feature)

```text
specs/007-village-life/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
backend/src/agent_lab/village/world.py, turn.py, runner.py   # changed
backend/src/agent_lab/api.py                                  # stream event names
backend/tests/test_village_world.py, test_village_turn.py,
              test_village_runner.py, test_village_api.py     # rewritten for M7
frontend/src/lib/api.ts, lib/village.ts (+ test)
frontend/src/components/village/pixels.tsx (+ test), VillageView.tsx, VillagerPanel.tsx
README.md, AGENTS.md
```

**Structure Decision**: the M6 package and components change in place; nothing new is added
outside them.

## Complexity Tracking

None.
