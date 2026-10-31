---
description: "Task list for M7 — Village Life"
---

# Tasks: M7 — Village Life

**Input**: `specs/007-village-life/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-021, SC-001–SC-005); every FR maps to a test or manual
check (see Traceability). Tests use `FakeLLM` only; villager answers come from callables that
read the villager's name from the system prompt (as in M6). Runner tests pass `move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16). Visual work follows the
frontend-design skill and keeps the pixel-art village identity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md

## Conventions used by every task

- A decision is an ordinary run of the villager's block agent through `runs.new_run` /
  `runs.execute_run`, tagged with `village_tick` (the step it started in) and `villager`; the
  village never calls the model itself.
- Model output is parsed into a validated action, never executed; anything invalid is `wait`
  with a reason; decoded actions are redacted again (M6).
- Steps hold one `asyncio.Lock`; decisions apply on the event loop without awaiting in between,
  so they need no lock; at most one decision per villager is in flight (research.md §1).
- Templates, custom agents and block agents behave as before; the golden file is unchanged.

---

## Phase 1: Foundational — map, characters, clock (blocks all stories)

- [X] T001 World in backend/src/agent_lab/village/world.py: replace `ROWS` with the 32 × 22 map (research.md §7: places as M6 plus `B` town hall building, houses `h` Hilde near the town hall, `j` Jonas by the pier, `g` Greta by the fields, `l` Lina by the garden, each 3 × 2 with its door below the middle of the bottom row, `t` trees, `i` lamps; "`~ B h j g l t i` not walkable"); `HOMES` (name → letter, door); `walkable` from the not-walkable set; BFS generalised to target cells (`_distances(targets)`, `step_towards(x, y, targets)`, `steps_between`), with helpers for a place's cells and a home's door; `adjacent(a, b)` ("same cell or one of the 8 neighbours"), `sees(a, b)` ("within 6 cells", Chebyshev); clock minutes = 270 + 10·tick; `Character` gains `wake`, `bed` (minutes: "Jonas 05:00/21:00, Greta 05:30/21:30, Lina 06:30/22:00, Hilde 07:30/23:00"), `routine` (`[(from_hour, place)]`) and keeps the M6 persona with its home and sleeping hours added; `usual_place(name, minute) -> place key | "home"`; `awake_at(name, minute)`; `nearby` removed; `new_world()` with `version: 2`, everyone asleep at its door, the data-model.md villager fields, empty `conversations`, `talked_out`, `log`; tests in backend/tests/test_village_world.py: size and characters, every place and door reachable from every other, doors walkable, the pier at the water, `step_towards` one walkable cell to a place or a door, `adjacent` incl. diagonals and same cell, `sees` at 6 and 7 cells, clock at ticks 0, 3, 117, 147, `usual_place` per routine and outside waking hours, the new world (asleep at doors, 04:30)

**Checkpoint**: `make check` passes (runner, turn and API tests are adapted in the phases below;
until then, mark M6 tests that no longer apply as removed, not skipped).

---

## Phase 2: User Story 1 — A day and a night in a bigger village (P1) 🎯 MVP

**Goal**: villagers wake, work and sleep at their own times on the new map; the night passes
quickly; the world survives restarts.

**Independent test**: a scripted day from 04:30 into day 2: each villager leaves home within a
step of its wake-up time, takes no turns while asleep, walks home at bedtime and sleeps.

- [X] T002 [US1] Runner core in backend/src/agent_lab/village/runner.py: `step()` under the step lock (clock + 1; sleep schedule per research.md §4: wake at the door with trigger `woke` and cleared beliefs; at bedtime goal `home`, `bedtime` on, conversations ended "went home to bed"; at the door with `bedtime` → asleep, events `bedtime`, `slept`); moves: every walker (awake, goal set, not talking, no decision in flight unless `bedtime`) one cell towards its goal, one at a time in an order rotated by the step, publishing after each move and sleeping `gap` (research.md §2; constructor `move_gap: float | None`); arrival → trigger `arrived`, event; background decisions `_decide(name)` as M6 `_turn` (run, parse, redact) applied on completion (`move`/`wait` here; `say`, `find`, `goodbye` in later tasks), skipped while resetting or for a villager with `bedtime`; `_start_decisions()` per research.md §3 (trigger, or idle 3 steps since `last_decided`), only while running or inside Step; Step = one step + await the decisions it started; `_loop` sleeps the interval, or 0.2 s while everyone sleeps; failure self-pause counted per step ("at least one decision finished since the last step and all failed"); idle self-pause as M6; Reset waits for the step and the decisions in flight and discards them; load: a world without `version: 2` → `new_world()` with paused_reason "the village moved to a bigger map and started fresh"; `state()` adds per villager `state`, `wake`, `bed`, `goal` text, `talking_with`, `beliefs` (text), `destination`, and the world `log`, `map.homes`; the stream publishes `decision_started` (villager, run_id) instead of `turn_started`; tests in backend/tests/test_village_runner.py: a scripted day (each villager wakes within one step of its time, no decision while asleep, home and asleep by bedtime + 30 minutes, SC-001), no turns for a sleeping villager, the fast night (all asleep: a night of steps runs without the interval, SC-004), walking costs no model call (SC-005), persistence and load paused, reset during a decision discards it, an M6 world starts fresh with the reason, self-pause after 3 failed steps and without a viewer, Step never overlaps a step
- [X] T003 [P] [US1] Turn and agent in backend/src/agent_lab/village/turn.py: observation per FR-015 (time and period, where it is, its sleeping hours, who is next to it and awake, who it sees within 6 cells, conversation state, what was said to it, beliefs, places and its home with step counts, last 10 events); `move` accepts `home` / "my home"; the rules text (actions `move`, `find`, `say`, `goodbye`, `wait` with examples; "you can only talk to someone standing right next to you"; "you go home to sleep at your bedtime by yourself"); tests in backend/tests/test_village_turn.py: the observation for an awake villager with a neighbour, someone in sight, a line said to it, beliefs; `move home`; the agent body validates with `layout_errors == []`; each agent has its own persona with its sleeping hours
- [X] T004 [US1] API in backend/src/agent_lab/api.py and backend/tests/test_village_api.py: stream event `decision_started`; state fields per contracts/http-api.md; adapt the M6 API tests (controls, agents created once, stream on connect and after a step, foreign Origin refused, turns out of the main list, turns per villager, an edit applies from the next decision, turns survive a replaced agent)

---

## Phase 3: User Story 2 — Villagers that move at their own pace (P2)

**Goal**: moves and decisions happen at different moments; a slow decision freezes only its
villager.

**Independent test**: over one village hour, every published state differs from the previous by
at most one move; a villager waiting on a slow answer stands still while the others walk.

- [X] T005 [US2] Tests in backend/tests/test_village_runner.py (fix runner.py where they fail): staggered moves (subscribe to the bus: each `state` after a move differs by one villager's position; the order rotates between steps), 100 steps on walkable cells with at most one cell per villager per step (SC-002), a slow decision (FakeLLM delay for one villager) keeps that villager in place while another walks and decides, decisions start only on triggers (a walker is not asked each step; an idle villager decides again after 3 steps)

---

## Phase 4: User Story 3 — Meeting and talking face to face (P3)

**Goal**: speech only between neighbours; meetings by chance and on purpose; conversations
that start, last and end.

**Independent test**: a line reaches only the adjacent addressee; speech with nobody adjacent is
`wait`; two villagers who become neighbours both get `met`; `find` ends in `found` or `missed`.

- [X] T006 [US3] Speech, conversations and find in backend/src/agent_lab/village/turn.py (parse `say` with adjacency and talked-out checks, `find`, `goodbye`) and runner.py (deliver lines to awake neighbours: inbox, events, log, trigger `spoken to`, start the addressee's decision when running; conversations per research.md §5: talking villagers do not walk, end on goodbye / move / find / bedtime / apart / 3 silent steps / 10 lines with `ended` events and the talked-out pair; `met` on new adjacency after moves and steps; `find` targets per research.md §6, re-aimed while seen, `found` / `missed` with the reason); tests in test_village_turn.py (every valid and invalid `say`, `find`, `goodbye` with reasons: "nobody next to you", "Lina is not next to you", unknown villager, already next to them, talked out) and test_village_runner.py (a line reaches the addressee only, not a villager two cells away, SC-003; no-addressee speech reaches every awake neighbour; a sleeping neighbour hears nothing; `met` for both on a chance meeting; a conversation keeps both in place, ends on goodbye and on walking away, and after 10 lines makes the pair talked out until apart; `find` found and missed)

---

## Phase 5: User Story 4 — Knowing where the others are (P4)

**Goal**: each villager has a belief about every other one, which can be out of date.

**Independent test**: a sighting updates the belief, a heard place updates it as heard, with
nothing known it is the routine; moving out of sight does not update it.

- [X] T007 [US4] Beliefs in runner.py and turn.py: sightings after every move and step (`seen`, cell and place), the heard rule ("a heard line mentions the other's name and exactly one place label or home") on delivery, routine fallback in the observation and `state()` text ("at the pier (seen 07:40)", "at the square (heard from Greta at 07:30)", "usually at the market around now"), cleared on waking; tests in test_village_runner.py and test_village_turn.py for the three sources, staleness after moving out of sight, clearing on waking, and `find` using the belief

---

## Phase 6: UI (US1–US4)

- [X] T008 [P] View logic in frontend/src/lib/api.ts (new `VillageState` fields) and frontend/src/lib/village.ts: `stateText(villager)` ("Asleep at home", "Going home to bed", "Thinking…", "Talking with Greta", "Walking to the pier", "Looking for Lina", "At the market"), `sleepText` ("Up at 05:00, in bed at 21:00"), `logLines(state)` (last 4, newest last), `homeAreas(map)` (letter boxes with owner), `figures` skips sleeping villagers; remove what is no longer used (`speeches`, `narration` move to the log); tests in frontend/src/lib/village.test.ts
- [X] T009 Pixel art in frontend/src/components/village/pixels.tsx: the town hall drawn on its `B` cells, a house sprite per home (roof in the owner's color, door at the door cell, name plate), trees and lamps from `t` / `i` cells (the hard-coded lists go), "Zz" over a sleeping owner's house, lit lamps unchanged; test that every map character the backend uses has a drawing (pixels.test.ts)
- [X] T010 Village view in frontend/src/components/village/VillageView.tsx and VillagerPanel.tsx: hide sleeping villagers, a thinking mark while deciding, the talk bubble for a line said this step, the dialog box from the log (newest last; narration when empty), the list with `stateText`, the panel with `sleepText` and "Thinks the others are" (beliefs), `decision_started` refreshes the turns; screenshots at 1400 × 950 and 390 × 844 (day, evening with lit lamps, night with "Zz", a conversation)

---

## Phase 7: Polish

- [X] T011 Docs: AGENTS.md (village layout line, roadmap M8–M11), README.md (village section: homes, sleep, meetings), specs/006-village nothing; the M6 golden behaviour of templates unchanged
- [X] T012 `make check`; quickstart manual steps on the real model with results recorded below

---

## Dependencies

T001 → T002 → (T003 ∥ T004) → T005 → T006 → T007 → T008 ∥ T009 → T010 → T011 → T012.

## Implementation strategy

MVP = Phases 1–2 (homes, sleep, the step loop with background decisions). Then pacing tests
(US2), meetings (US3), beliefs (US4), the view, docs.

## Traceability

| FR | Test / check |
|---|---|
| FR-001, FR-002 | test_village_world.py (map, homes, doors); pixels.test.ts; T010 screenshots |
| FR-003, FR-004 | test_village_world.py (hours, new world); test_village_runner.py (scripted day) |
| FR-005 | test_village_runner.py (fast night) |
| FR-006 | test_village_runner.py (staggered moves, one cell per step, no model call per step) |
| FR-007 | test_village_runner.py (triggers only, idle after 3 steps) |
| FR-008 | test_village_runner.py (slow decision, steps never overlap) |
| FR-009, FR-010 | test_village_turn.py (actions, adjacency reasons); test_village_runner.py (delivery) |
| FR-011, FR-012 | test_village_runner.py (conversations, met) |
| FR-013 | test_village_runner.py (find found / missed) |
| FR-014, FR-015 | test_village_runner.py, test_village_turn.py (beliefs, observation) |
| FR-016 | test_village_turn.py (personas with routines and hours); quickstart step 3 |
| FR-017 | test_village_runner.py (persistence, reset, M6 world, self-pauses); test_village_api.py |
| FR-018 | test_village_api.py (turns are runs, out of the main list, edits apply) |
| FR-019, FR-020 | village.test.ts; T010 screenshots; quickstart steps 3–5 |
| FR-021, FR-022 | T001–T007 tests; `make check` (T012) |

| SC | Test / check |
|---|---|
| SC-001 | test_village_runner.py (scripted day); quickstart step 2 |
| SC-002 | test_village_runner.py (100 steps, staggered) |
| SC-003 | test_village_runner.py (speech reaches neighbours only) |
| SC-004 | test_village_runner.py (fast night timing); quickstart step 5 |
| SC-005 | test_village_runner.py (no model call while walking) |
| SC-006 | quickstart step 3 (real model) |

## Manual check results (T012, 2026-11-01)

vLLM `qwen3.5-9b`; a scratch backend on a copy of the owner's database (the stored M6 world
started fresh on the new map and its villager agents were updated), driven over the API and
stream at a 1 s interval; the view checked with mocked states (headless Chromium).

| Quickstart step | Result |
|---|---|
| 1. Open the view | bigger map with four houses (roofs in their owners' colors, name plates), everyone asleep with "Zz", day 1, 04:30, "Paused: the village moved to a bigger map and started fresh" |
| 2. Wake-up times, staggered moves | first decisions at 05:00 (Jonas), 05:30 (Greta), 06:30 (Lina), 07:30 (Hilde) (SC-001); 0 of 562 published states moved more than one villager (US2-1) |
| 3. Talking face to face | a full day: 29 lines, Hilde used `find` 7 times; she found Jonas at the market ("We need those fresh fish for the harvest festival on the square!") and talked with Lina about festival flowers (SC-006); waits were readable ("Greta is not next to you", "it was already your bedtime") |
| 4. Villager panel | sleeping hours, "Thinks the others are" (routine, seen, heard), events and turns |
| 5. Evening and night | every villager's last decision came before its bedtime; at 05:30 on day 2 Jonas and Greta were up and walking, Hilde and Lina asleep; a day and a night of 150 steps took 133 s at a 1 s interval |
| 6. Restart, Reset | covered by tests (load paused, reset to 04:30 with everyone asleep) |

Fixed during the checks: the model often named villagers by title ("Mayor Hilde"), which made
speech and finds wait; names now match a first name or a title. Villagers drifted home in the
morning; the observation now says where the villager usually is at this hour. The dev server
served an outdated cached stylesheet until `frontend/.next` was cleared.
