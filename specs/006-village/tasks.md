---
description: "Task list for M6 — The Village (first slice)"
---

# Tasks: M6 — The Village (first slice)

**Input**: `specs/006-village/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-016, SC-002–SC-005); every FR maps to a test or manual check
(see Traceability). Tests use `FakeLLM` only; villager answers come from callables that read the
villager's name from the system prompt.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16). Visual work on the Village view uses
the frontend-design skill, keeping the Agent Lab identity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 / US2 / US3 from spec.md

## Conventions used by every task

- A villager turn is an ordinary run of its block agent through `runs.new_run` /
  `runs.execute_run`; the village never calls the model itself (research.md §1).
- Model output is parsed into a validated `Action`, never executed; anything invalid is `wait`
  with a reason (data-model.md "Action").
- Ticks and the controls Step, Reset and interval changes share one `asyncio.Lock`; ticks never
  overlap (research.md §5).
- Templates, custom agents and block agents behave as in M5; the golden template file is not
  changed.

---

## Phase 1: Setup — storage and run fields

- [X] T001 Storage in backend/src/agent_lab/store.py: table `village` (`id INTEGER PRIMARY KEY CHECK (id = 1)`, `state TEXT NOT NULL`) with `load_village() -> dict | None` and `save_village(state: dict)`; `runs` gains `village_tick INTEGER`, `villager TEXT`, `village_action TEXT` (JSON), added in place when `PRAGMA table_info(runs)` lacks them (the existing migration loop takes a column type); `Run` gains `village_tick: int | None`, `villager: str | None`, `village_action: dict | None`; `list_runs()` adds `WHERE runs.village_tick IS NULL`; new `list_turns(villager, limit=200)` (rows with that `villager`, newest first) and `set_village_action(run_id, action: dict)`; tests in backend/tests/test_store.py: an M5 database gains the columns and its runs still list, `list_runs` skips village turns, `list_turns` returns them by villager, the village row round-trips
- [X] T002 Runs in backend/src/agent_lab/runs.py: `new_run(..., village_tick: int | None = None, villager: str | None = None)` stores both on the run; existing callers unchanged; test in backend/tests/test_api.py that `GET /runs` stays unchanged for normal runs and `Run` JSON carries the three new fields as null

---

## Phase 2: Foundational — world, observations, actions (blocks all stories)

- [ ] T003 [P] World in new backend/src/agent_lab/village/world.py (package `village/__init__.py` with a docstring): `ROWS` (15 strings of 20 characters: `.` grass, `=` path, `~` water, `T` town hall, `S` square, `M` market, `P` pier, `F` fields, `G` flower garden; every place reachable from every other over walkable cells; the pier next to water), `PLACES` (key → label: `town_hall` "town hall", `square`, `market`, `pier`, `fields`, `flower_garden` "flower garden"), `walkable(x, y)`, `place_at(x, y) -> str | None`, `place_cells(key)`, `label_cell(key)` (top-left cell of the place, for the UI label), `step_towards(x, y, place) -> (x, y)` (breadth-first search over the 4-neighbour grid to the nearest cell of the place; first step of a shortest path; no move when already inside), `steps_between(x, y, place) -> int`, `nearby(a, b) -> bool` ("the same place, or within 3 cells (Chebyshev distance) outside places"), `clock(tick) -> (day, "HH:MM", period)` with minutes = 360 + 10·tick and periods "05:00–11:00 morning, 11:00–14:00 midday, 14:00–18:00 afternoon, 18:00–22:00 evening, otherwise night"; `VILLAGERS`: Hilde "Mayor Hilde" (home `town_hall`, initial H), Jonas "Jonas the fisher" (`pier`, J), Greta "Greta the farmer" (`fields`, G), Lina "Lina the flower girl" (`flower_garden`, L), each with a color token and a persona paragraph (personality, daily rhythm; Hilde plans the harvest festival and needs fish, vegetables and flowers; Jonas quiet and patient, brings the catch to market; Greta practical, worries about the weather; Lina cheerful and curious, carries news); `new_world() -> dict` (data-model.md "World": tick 0, paused, interval 5, villagers at a cell of their home, no destination, empty speech, inbox and events); tests in new backend/tests/test_village_world.py: map size and characters, all places reachable, `step_towards` moves one cell and never onto water, arrival, `nearby` inside and outside places, clock at ticks 0, 30, 144, 900
- [ ] T004 [P] Turns in new backend/src/agent_lab/village/turn.py: `observation(world, name) -> str` (research.md §6: day, time and period; its place or "on the way to …"; nearby villagers by title; every place with its step count; speech heard since its last turn as `- Jonas to you: "…"` / `- Jonas to Greta: "…"` / `- Jonas: "…"`; its last 10 events with times; the closing question); `Action` = pydantic union: `{"action": "move", "place"}` (a place key or label), `{"action": "say", "text", "to"?}` ("text not empty after trimming, any length"; `to` another villager's first name), `{"action": "wait"}`; `parse_action(answer: str | None, world, name) -> tuple[Action, str | None]` returning `wait` and the reason for: no answer, not JSON, unknown action, unknown place, empty text, unknown or own name as `to`, moving to the place it is already at; `villager_agent(villager) -> dict` (a block agent body: name = title, `template_id` "blocks", sample prompt, config with model block `decide` (system = persona + "You live in a small village with Hilde, Jonas, Greta and Lina…" rules + the three action formats with examples; message `{previous}`) and check `answer-is-json` (`valid_json`)); tests in new backend/tests/test_village_turn.py: the observation for a villager with nearby people, heard speech (to it, to someone else, to all) and events; every valid action; every invalid case with its reason; the agent body validates as a block agent with `layout_errors == []`

**Checkpoint**: `make check` passes; the world and turn logic are tested without any model call.

---

## Phase 3: User Story 1 — Watch the village live (P1) 🎯 MVP

**Goal**: start, pause and step the village; villagers move and talk on a map; the world
survives restarts.

**Independent test**: with scripted answers, three ticks move the villagers, deliver speech to
the villagers nearby, advance the clock by three ticks and store the world after each one.

### Backend

- [ ] T005 [US1] Runner in new backend/src/agent_lab/village/runner.py: `Village(store, models, bus, secrets)` with `state()` (data-model.md "World" plus clock fields and `ticking`); `load()` (the stored world or `new_world()`, always paused after load); `ensure_agents()` (creates each villager's block agent through `store.create_agent` with a free name — the title, or the title + " (village)" when taken — and stores its id; recreates agents that no longer exist); `tick()` under the lock: observations from the state at tick start → for each villager `new_run(observation, agent_id, models, store, secrets, village_tick=tick, villager=name)` + `execute_run` concurrently with `asyncio.gather(..., return_exceptions=True)` (an unknown agent, an unavailable model or a failed run becomes `wait` "turn failed: …") → `parse_action` → apply all together (moves: set destination and `step_towards`; arrival adds an "arrived" event; speech: `speech` for the bubble cut to 200 characters, an event "said" for the speaker, and for every villager nearby (after moves) an inbox entry and a "heard" event; waits add a "waited" event with the reason) → `set_village_action(run_id, action + reason)` for each turn → events kept to the last 10 → inbox cleared for villagers who just had their turn → `failed_ticks` (+1 when every turn failed, else 0) → tick + 1 → `save_village` → publish `{"type": "state"}` on the bus; `start()`, `pause()` (flag, current tick finishes), `step()` (409 while running or ticking), `set_interval(seconds)` ("1–30", under the lock), `reset()` (under the lock: `new_world()`, `ensure_agents()`, save); the loop task while running: tick, then sleep the rest of the interval; self-pause with `paused_reason` "every turn failed 3 ticks in a row" when `failed_ticks` reaches 3
- [ ] T006 [US1] Viewer counting and the idle pause in backend/src/agent_lab/village/runner.py: `viewer_joined()` / `viewer_left()` track open Village streams and the time the last one closed; the loop pauses with `paused_reason` "no viewer for 60 s" when no viewer has been connected for 60 seconds (checked between ticks); reopening within 60 s keeps it running; the delay is a constructor argument so tests can use a short one
- [ ] T007 [US1] API in backend/src/agent_lab/api.py (contracts/http-api.md): one `Village` per app, loaded at startup; `GET /village`, `POST /village/start` (calls `ensure_agents` first), `POST /village/pause`, `POST /village/step` (409 while running or ticking), `PUT /village/interval {"seconds"}` (422 outside 1–30), `POST /village/reset`; `WS /village/stream` with the run stream's Origin check, sending the state on connect and every published state, and calling `viewer_joined` / `viewer_left`; the map in the state: `rows` and `places` with label positions
- [ ] T008 [US1] Tests in new backend/tests/test_village_runner.py (scripted callables per villager, `Village` driven directly): three ticks move and deliver speech as scripted and advance the clock; actions of one tick apply together (two villagers see each other's state from the tick start); speech reaches nearby villagers only, with the addressee; the world is stored after each tick and a new `Village` on the same store loads it paused (SC-005); reset; 100 ticks of random valid moves keep everyone on walkable cells and move at most one cell per tick (SC-002); three all-failed ticks pause with the reason; the idle pause with a 0.1 s delay; Step during a tick and two concurrent Steps never overlap (one gets 409); reset during a tick waits for it
- [ ] T009 [US1] Tests in new backend/tests/test_village_api.py: the endpoints and their status codes, the interval range, the stream sends the state on connect and after a step, a foreign Origin is refused, `POST /village/start` creates four agents once (listed in `GET /agents` with `template_id` "blocks")

### Frontend

- [ ] T010 [P] [US1] frontend/src/lib/api.ts: `VillageState`, `Villager`, `VillageEvent`, `Turn` types; `getVillage()`, `startVillage()`, `pauseVillage()`, `stepVillage()`, `setVillageInterval(seconds)`, `resetVillage()`, `villagerTurns(name)`, `villageStreamUrl()`; `Run` gains the three village fields
- [ ] T011 [P] [US1] Pure view logic in new frontend/src/lib/village.ts with tests in new frontend/src/lib/village.test.ts: `cellKind(char)` (grass, path, water, place), `figures(state)` (one per villager at its cell; villagers sharing a cell are offset so all stay visible), `speechText(villager, state)` (`"Hilde → Jonas: …"` or `"Hilde: …"`, already cut by the server), `statusLine(state)` ("Running", "Ticking…", "Paused: no viewer for 60 s", …), `clockText(state)` ("Day 1, 07:20, morning")
- [ ] T012 [US1] Village view in new frontend/src/components/village/VillageView.tsx: SVG map from the state rows (one rect per cell in theme colors, place labels), villagers as `<g>` buttons (circle in the villager's color, initial, name below, `aria-label` with title and place), speech bubbles for this tick's speech, moves eased with a short transition (none under `prefers-reduced-motion`); controls: Start / Pause, Step (disabled while running or ticking), interval input (1–30 s), Reset (with `confirm()`), clock and status line; live updates from `villageStreamUrl()`
- [ ] T013 [US1] Wire in frontend/src/app/page.tsx: a switch between "Agents" (today's layout) and "Village" in the header; the Village view mounts its stream only while shown

**Checkpoint**: the village can be started, paused, stepped and reset from the UI; villagers move
and talk.

---

## Phase 4: User Story 2 — Four villagers with their own personalities (P2)

**Goal**: personas, memory and invalid answers behave as specified.

**Independent test**: each villager's observation shows its persona inputs and last events; a
move takes several ticks with an arrival event; every invalid answer becomes a recorded wait.

- [ ] T014 [P] [US2] Tests in backend/tests/test_village_turn.py: each of the four agent bodies carries its own persona and the shared rules; the observation of a villager on the way shows "on the way to the market" and its step counts; the 11th event pushes out the oldest (only 10 shown)
- [ ] T015 [P] [US2] Tests in backend/tests/test_village_runner.py: a move to a place 5 steps away takes 5 ticks and ends with one "arrived" event; each invalid answer (no answer, not JSON, unknown action, unknown place, empty text, unknown `to`, already there, failed run) leaves the villager in place with a "waited" event naming the reason, and the same reason in the turn's `village_action` (SC-004)
- [ ] T016 [US2] Persona review in backend/src/agent_lab/village/world.py: the four persona texts and the shared rules read naturally, mention when each villager tends to be where, keep answers short, and ask for exactly one JSON object; checked by running quickstart step 3 on the real model (T024)

**Checkpoint**: villagers act in character within the action rules; every wait explains itself.

---

## Phase 5: User Story 3 — Look inside a villager (P3)

**Goal**: a villager panel with events and turns, turns opening in the run view; edits apply
from the next tick; village turns stay out of the main list.

**Independent test**: turns are listed per villager with their tick and action; editing the
agent between ticks gives a new `config_version`; deleting the agent and resetting keeps old
turns listed.

- [ ] T017 [US3] `GET /village/villagers/{name}/turns` in backend/src/agent_lab/api.py → `[Turn]` from `store.list_turns(name)`, 404 for an unknown name; tests in backend/tests/test_village_api.py: turns carry `village_tick`, `villager` and `village_action` (the wait reason readable after more than ten later events), `GET /runs` lists none of them (FR-012), an edit of a villager's agent between two steps gives the next turn a new `config_version` and its instructions (FR-013), delete a villager's agent → its turns wait "turn failed: unknown agent" → reset recreates the agent → `list_turns` returns old and new turns
- [ ] T018 [P] [US3] Panel logic in frontend/src/lib/village.ts (+ tests in frontend/src/lib/village.test.ts): `eventLines(villager, state)` ("07:10 Arrived at the market", "07:20 Heard Jonas: …", "07:30 Waited: unknown place 'harbour'"), `turnLabel(turn)` (tick time, action or wait reason, status)
- [ ] T019 [US3] Villager panel in new frontend/src/components/village/VillagerPanel.tsx: opened by clicking or pressing Enter on a figure; title, role and persona summary, place or destination, last action, the last 10 events, turns newest first (`villagerTurns`), refreshed after each tick; choosing a turn opens the existing `RunViewer` for it (live while running); a link "Edit agent" switches to the Agents view with the villager's agent selected

**Checkpoint**: every villager decision can be traced from the map to its model call.

---

## Phase 6: Polish

- [ ] T020 [P] Docs: README.md (the Village: Start/Pause/Step/Reset, interval, the four villagers, editing a villager's agent, self-pauses; API rows for `/village…`); AGENTS.md (layout: `village/` package; rule: villager turns are ordinary runs, the village never calls the model directly)
- [ ] T021 `make check` passes; FR → test map below complete
- [ ] T022 Manual checks from quickstart.md steps 1–8 on vLLM; record results (including whether the villagers talk to each other and the mayor mentions the festival, SC-006) in a "Manual check results" section of this file

---

## Dependencies

- Phase 1 → Phase 2 → stories. T001 → T002; T003 ∥ T004.
- US1 needs Phase 2. US2's tests need the runner (T005). US3 needs T005 and T007.
- Frontend: T010 ∥ T011, then T012, T013; T018 ∥ T017, then T019.

## Parallel opportunities

- Phase 2: T003 ∥ T004.
- US1: frontend T010–T011 alongside backend T005–T009.
- US2: T014 ∥ T015.

```bash
# Phase 2 example
Task: "World in backend/src/agent_lab/village/world.py"
Task: "Turns in backend/src/agent_lab/village/turn.py"
```

## Implementation strategy

1. Storage and pure world/turn logic first; they are testable without a model.
2. MVP = US1: the village runs on the map; stop and run quickstart steps 1–2.
3. US2 hardens personalities, memory and invalid answers.
4. US3 opens every decision to inspection.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_village_world.py (map, places, water, clock) |
| FR-002 | test_village_runner.py (stored per tick, load paused, reset) |
| FR-003 | test_village_world.py (four villagers, homes, initials); quickstart step 1 |
| FR-004 | test_village_api.py (agents created once, listed); test_village_turn.py (agent body) |
| FR-005 | test_village_turn.py (last 10 events); test_village_runner.py (events per action) |
| FR-006 | test_village_turn.py (observation, actions) |
| FR-007 | test_village_runner.py (concurrent turns, applied together, no overlap) |
| FR-008 | test_village_runner.py (invalid answers → wait with reason, in events and turn) |
| FR-009 | test_village_world.py (step_towards); test_village_runner.py (5-step move, 100 ticks) |
| FR-010 | test_village_runner.py (start, pause, step, interval, failed-tick and idle pauses); test_village_api.py |
| FR-011 | test_village_api.py (turns are runs with tick and villager); `assert_trace_valid` on a turn |
| FR-012 | test_village_api.py (`GET /runs` without turns, turns per villager) |
| FR-013 | test_village_api.py (edit between steps → new `config_version`) |
| FR-014 | village.test.ts (figures, speech, status); quickstart steps 1–3 |
| FR-015 | village.test.ts (event lines, turn labels); quickstart step 4 |
| FR-016 | T004, T008, T009, T014, T015, T017 |
| FR-017 | `make check` (T021) |

| SC | Test / check |
|---|---|
| SC-001 | quickstart step 2 (timed) |
| SC-002 | test_village_runner.py (100 ticks) |
| SC-003 | test_village_api.py (turns traced with their tick) |
| SC-004 | test_village_runner.py (invalid answers) |
| SC-005 | test_village_runner.py (load after restart); quickstart step 8 |
| SC-006 | quickstart step 3 (real model) |
