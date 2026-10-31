# Implementation Plan: M6 — The Village (first slice)

**Branch**: `main` (feature directory `006-village`) | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-village/spec.md`

## Summary

A new `village/` package holds a fixed 20 × 15 map with six places, a clock, and four villagers
whose state lives in one SQLite row. Each villager is played by an M5 block agent created on
first start (a model call that reads the observation and answers one JSON action, then a
`valid_json` check). A tick builds the four observations, runs the four turns concurrently as
ordinary traced runs tagged with the tick, parses the answers into actions (anything invalid is
`wait`), applies them together, advances the clock and stores the world. A server-side loop runs
ticks at the set interval and pauses itself without a viewer or after repeated failures. The
API adds `/village` endpoints and a stream; the UI adds a Village view drawn in SVG, with a
villager panel whose turns open in the existing run view.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged; no new dependencies (the map is SVG, research §8)

**Storage**: SQLite: new table `village` (one row, JSON state); `runs` gains `village_tick`
(nullable integer, added in place)

**Testing**: pytest with `FakeLLM` (callables answer per villager); vitest for map and panel
view logic

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: first tick visible within 30 s of opening the view on the local model
(SC-001); a tick's four turns run concurrently (vLLM batches them)

**Constraints**: every villager decision is a traced run on its agent's graph; ticks never
overlap; no unwatched running for more than 60 s; templates and agents unchanged

**Scale/Scope**: one world, four villagers, 300 cells, ticks every 1–30 s

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Small modules (`world`, `turn`, `runner`), breadth-first search by hand, no game or graph engine, no dependency |
| II. Observable by default | Pass | Every villager decision is a normal run through the block agent runner (spans on its graph, stored and streamed); the tick is recorded on the run; world changes are visible in the stored state and the stream |
| III. Secure local defaults | Pass | Loopback, same Host/CORS/Origin checks; model output is parsed into a validated action, never executed; speech length capped; redaction unchanged |
| IV. Smallest change | Pass | Villagers reuse block agents and the run pipeline; one state row; the Phase 2 seams (agent ids, config versions, a tick-driven runner) are exactly what is used |
| V. Gates + traceability | Pass | `make check` unchanged; map/observation/action logic covered by pytest, map view logic by vitest; FR → test map in `tasks.md` |

PixiJS is reserved for Phase 2 but not needed for a static grid; SVG keeps the dependency list
unchanged. Post-design re-check: passes; no Complexity Tracking entries.

## Design

Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md).

### `backend/src/agent_lab/village/`

- `world.py`: the map rows, places, `walkable`, `place_at(x, y)`, `path(start, place)` (BFS),
  `nearby(a, b)`, the clock (`clock(tick) -> day, time, period`), the four villager definitions
  (name, title, color, initial, home, persona) and `new_world()`.
- `turn.py`: `observation(world, villager) -> str`, `Action` (pydantic union for move/say/wait),
  `parse_action(answer, world) -> Action | reason`, `villager_agent(villager) -> BlocksConfig`
  (persona, rules and action format in the system prompt).
- `runner.py`: `Village(store, models, bus)`: `load()`, `ensure_agents()`, `tick()`,
  `start()`, `pause()`, `step()`, `set_interval()`, `reset()`, viewer counting and self-pause,
  `state()` for the API and stream.

### Existing code

- `store.py`: `village` table with `load_village()` / `save_village(state)`; `runs.village_tick`
  column; `list_runs()` excludes village turns; `list_turns(agent_id)`.
- `runs.py`: `new_run(..., village_tick=None)` stores it; `Run.village_tick`.
- `api.py`: the `/village` endpoints and `WS /village/stream`; one `Village` per app.

### UI

- `lib/api.ts`: `VillageState` types, village calls, `villageStreamUrl`.
- `lib/village.ts` (pure, vitest): cell colors, place label positions, villager figure positions,
  speech text (`"Hilde → Jonas: …"`, cut to 200), event lines, the status line (running,
  paused and why, ticking).
- `components/village/VillageView.tsx` (SVG map + controls + villager list),
  `VillagerPanel.tsx` (persona, place, last action, events, turns); a turn opens the existing
  `RunViewer`.
- `app/page.tsx`: a switch between "Agents" (today's layout) and "Village".
- Visual work follows the frontend-design skill, keeping the Agent Lab identity.

## Project Structure

### Documentation (this feature)

```text
specs/006-village/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
backend/src/agent_lab/
├── village/__init__.py, world.py, turn.py, runner.py   # new
├── store.py, runs.py, api.py                           # village table, run column, endpoints
backend/tests/
├── test_village_world.py     # map, paths, nearby, clock
├── test_village_turn.py      # observations, actions, invalid answers, agent layout
├── test_village_runner.py    # ticks, concurrency, speech, persistence, self-pause, 100 ticks
├── test_village_api.py       # endpoints, stream, turns list, main list excludes turns
frontend/src/
├── lib/api.ts, lib/village.ts (+ test)
└── components/village/VillageView.tsx, VillagerPanel.tsx, app/page.tsx
README.md, AGENTS.md
```

**Structure Decision**: one new backend package and one new component folder; agents, blocks and
runs are reused as they are.

## Complexity Tracking

None.
