---
description: "Task list for M8 — Villager Memory"
---

# Tasks: M8 — Villager Memory

**Input**: `specs/008-village-memory/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-010, SC-001–SC-005). `FakeLLM` only; answers come from
callables that tell decisions from reflections by the system prompt. Runner tests pass
`move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- A reflection is an ordinary run of the shared reflection agent through `runs.new_run` /
  `runs.execute_run`, tagged with `village_tick` and `villager`; the village never calls the
  model itself; its answer is validated, never executed, and redacted after decoding.
- Reflections live in their own task map and never count as decisions (research.md §3).

---

## Phase 1: Foundational — memory module and world shape

- [ ] T001 [P] New backend/src/agent_lab/village/memory.py (research.md §1–§3): `IMPORTANCE` ("conversation 3, found 2, missed 2, met 1, reflection 5"), `remember(villager, tick, kind, text, about, place)` (text cut to 400; "at most 60 per villager", dropping the lowest importance + recency), `score`, `recall(memories, tick, names, place, limit=5)` (oldest first), `memories_of_day(memories, tick)`, `reflection_prompt(world, name)`, `parse_reflection(answer, name) -> (result | None, reason)` ("`learnings` a list of at most 3 non-empty strings, `views` keyed by the other villagers' first names; texts cut to 200"), `reflection_agent()` (block agent "Village reflection": model block `reflect` + check `answer-is-json`); world.py: `VERSION = 3`, new villager fields `memories`, `learnings`, `views`, world `reflection_agent_id`, `upgrade(world)` for version 2; tests in new backend/tests/test_village_memory.py: importance per kind, the limit drops the least valuable, recall prefers relevant then important then recent, the prompt lists today's memories, learnings and views, every valid and invalid reflection answer, the agent validates as a block agent, upgrading a version-2 world

## Phase 2: User Story 1 — Villagers remember what happened (P1) 🎯 MVP

- [ ] T002 [US1] Runner and observation: conversations keep a transcript; memories on conversation end (both), found, missed, first meeting of the day; turn.py observation adds "What you remember:" (recall with the villagers next to it, being looked for or talking with it, and its place) ; `state()` adds `memories` (newest first, with day and time); tests in test_village_runner.py and test_village_turn.py: a conversation becomes a memory of both with its lines (SC-001), found and missed memories, one met memory per villager per day, a morning conversation recalled when the two meet in the afternoon (SC-002), the limit over 10 scripted days (SC-005)

## Phase 3: User Story 2 — Learning at the end of the day (P2)

- [ ] T003 [US2] Reflections in runner.py: the reflection agent in `ensure_agents` (created once, recreated by Reset if deleted, id in the world); `_reflect(name)` started when a villager falls asleep after a day with memories, chained per villager, tagged with the step, `decision_started` published; valid answers add learnings (12 kept), replace views and add a reflection memory; invalid ones record the reason in the run's `village_action`; Step and Reset wait for reflections; reflections excluded from the failure count; turn.py: learnings and "; you think: …" views in the observation; `state()` adds `learnings`, `views`, `beliefs[].view`; M7 worlds upgraded on load; tests: reflection once on falling asleep, none after an uneventful day (SC-003), learnings and views in the next day's observations (SC-004), invalid answers change nothing, reflections never overlap, a failing reflection does not pause the village, reset clears memory, an M7 world loads with empty memory, the reflection agent created once and listed

## Phase 4: User Story 3 — Seeing what a villager has learned (P3)

- [ ] T004 [P] [US3] frontend/src/lib/api.ts and lib/village.ts: villager `learnings`, `views`, `memories`, `beliefs[].view`; `VillageAction` `reflect`; `turnLabel` "reflects on day 1" (or the reason); `memoryLines`; tests in village.test.ts
- [ ] T005 [US3] frontend/src/components/village/VillagerPanel.tsx: "Has learned" (with day), views next to beliefs, "Remembers" from lasting memories (10, then "Show all"), screenshots at 1400 × 950

## Phase 5: Polish

- [ ] T006 README.md (village memory), AGENTS.md (`memory.py` in the layout, reflections in the contracts)
- [ ] T007 `make check`; quickstart manual steps on the real model with results recorded below

## Dependencies

T001 → T002 → T003 → (T004 → T005) → T006 → T007.

## Traceability

| FR | Test / check |
|---|---|
| FR-001, FR-002 | test_village_memory.py (importance, limit); test_village_runner.py (memories from events, 10 days) |
| FR-003 | test_village_memory.py (recall); test_village_runner.py (afternoon recall) |
| FR-004, FR-005 | test_village_runner.py (reflection on sleep, valid/invalid); test_village_memory.py (parse, agent) |
| FR-006 | test_village_turn.py / test_village_runner.py (learnings and views in observations) |
| FR-007 | test_village_runner.py (no overlap, not counted as failures) |
| FR-008 | test_village_runner.py (persistence, reset, M7 world) |
| FR-009 | village.test.ts; T005 screenshots; quickstart step 2 |
| FR-010, FR-011 | T001–T003 tests; `make check` (T007) |

| SC | Test / check |
|---|---|
| SC-001, SC-002 | test_village_runner.py |
| SC-003, SC-004 | test_village_runner.py |
| SC-005 | test_village_runner.py (10 scripted days) |
| SC-006 | quickstart step 3 (real model) |
