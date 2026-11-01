---
description: "Task list for M9 — Village Motion and Look"
---

# Tasks: M9 — Village Motion and Look

**Input**: `specs/009-village-motion/` (plan.md, spec.md, research.md). **Tests**: FakeLLM only;
runner tests pass `move_gap=0`. **Gate**: `make check` per phase; commit after each phase.

## Phase 1: User Stories 1 and 2 — movement and conversations (P1) 🎯 MVP

- [X] T001 [US1] backend/src/agent_lab/village/runner.py: `CELLS_PER_STEP = 3`, rounds, gap per research §1; tests in backend/tests/test_village_runner.py: up to 3 cells per step through each cell, one move per published state over a step with several walkers, early arrival, a meeting mid-step while walking on, 100 steps with at most 3 cells per villager per step (SC-002), crossing fields → pier in at most a third of the M8 steps (SC-001)
- [X] T002 [US2] turn.py and runner.py: move and find refused while talking ("you are talking with <names>; say goodbye first"), goodbye with `place` or `villager` (invalid → "You said goodbye but stayed: …"), new rules text, `_refresh_rules()` on load, `state()` `work`; tests in test_village_turn.py and test_village_runner.py: refusals, goodbye with place / villager / nothing / invalid destination, the other villager told, the refresh replaces only the unchanged rules text (SC-003)

## Phase 2: User Stories 3 and 4 — idle animations and world (P2, P3)

- [X] T003 [P] [US3] frontend/src/lib/village.ts: `activity`, `rhythm`, `PERIOD_SKY` (replacing `PERIOD_TINT`); `Villager.work` in lib/api.ts; tests in village.test.ts
- [X] T004 [US3] [US4] pixels.tsx, VillageView.tsx, globals.css: walk frames, linear glides, breathing / blinking / glancing, work props and animations, shadows, chimney smoke, butterflies, lake rings, fireflies, sky gradient; reduced motion stills everything; decorations ignore pointer events; screenshots morning, midday, sunset, night, a conversation, each villager working (SC-004)

## Phase 3: Polish

- [X] T005 README.md (movement, goodbye, animations)
- [X] T006 `make check`; real-model day with results recorded below (SC-005)

## Traceability

| FR | Test / check |
|---|---|
| FR-001, FR-002 | test_village_runner.py (rounds, publishes, early arrival, meetings) |
| FR-003 | T004 screenshots; CSS under reduced motion |
| FR-004, FR-005, FR-006 | test_village_turn.py, test_village_runner.py (refusals, goodbye, rules refresh) |
| FR-007, FR-008 | village.test.ts (activity, rhythm); T004 screenshots |
| FR-009, FR-010 | T004 screenshots; CSS reduced motion; `pointer-events: none` |
| FR-011, FR-012 | T001–T003 tests; `make check` (T006) |
| SC-001–SC-003 | test_village_runner.py |
| SC-004 | T004 screenshots |
| SC-005 | T006 real-model day |

## Manual check results (T004, T006, 2026-11-01)

Screenshots with mocked states (headless Chromium): morning, midday at work (Jonas's rod and
float at the pier, Greta's hoe in the fields, Lina's watering can in the garden), evening with a
conversation on the square (sunset gradient, lit lamps and windows), night (deep blue, fireflies,
lamps); shadows under houses, chimney smoke at Hilde's house while she stands at her door,
butterflies over the garden by day, rings on the lake. The pier's name plate moved below the
pier, where Jonas no longer covers it.

Real model (vLLM `qwen3.5-9b`, scratch backend on a copy of the owner's database, 1 s interval,
04:30 to 00:30): the stored villager agents got the new rules on load; 134 decisions; 7 attempts
to walk off mid-conversation were refused with "say goodbye first", and 7 goodbyes followed, 6 of
them with a destination (one ignored: "already at the square") (SC-005); 0 of 657 published
states moved more than one villager; a day took 117 s.
