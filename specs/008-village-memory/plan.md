# Implementation Plan: M8 — Villager Memory

**Branch**: `main` (feature directory `008-village-memory`) | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-village-memory/spec.md`

## Summary

A new module `village/memory.py` holds the pure memory logic: writing a memory (importance by
kind, the 60-memory limit), scoring and recalling memories by relevance, importance and
recency, the reflection prompt, the reflection answer's validation, and the reflection agent's
block layout. The runner writes memories where M7 already records events (conversation end,
found, missed, first meeting of the day), starts a reflection task when a villager falls asleep
after a day with memories, and applies its answer (learnings, views, a reflection memory). The
observation gains "What you have learned", "What you remember" and a view next to each belief.
The state exposes learnings, views and memories; the villager panel shows them and labels
reflections among the turns. The world shape moves to version 3; M7 worlds are upgraded in
place.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged; no new dependencies (recall by words, research §2)

**Storage**: the `village` row (JSON) with `version: 3`; runs unchanged (reflections are runs
tagged with `village_tick` and `villager`, their parsed answer in `village_action`)

**Testing**: pytest with `FakeLLM` callables that answer decisions and reflections by system
prompt; vitest for the panel logic

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: one extra model call per villager per night; observations stay under
about 2,500 characters

**Constraints**: reflections never block steps or decisions; one reflection per villager at a
time; memory per villager bounded (60 memories, 12 learnings)

**Scale/Scope**: four villagers, one shared reflection agent

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Memory, recall and reflection written by hand in one small module; no vector store or memory library |
| II. Observable by default | Pass | Each reflection is a traced run of an editable block agent; its prompt shows exactly what was recalled; its parsed answer is stored with the run |
| III. Secure local defaults | Pass | Model output is validated into learnings and views (names checked, lengths capped), never executed; decoded text is redacted again as in M6 |
| IV. Smallest change | Pass | Extends the village package, its state and the panel; one new module; no new endpoint |
| V. Gates + traceability | Pass | `make check` unchanged; FR → test map in `tasks.md` |

Post-design re-check: passes; no Complexity Tracking entries.

## Design

Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md).

### `backend/src/agent_lab/village/`

- `memory.py` (new, pure): `IMPORTANCE`, `remember(villager, tick, kind, text, about, place)`,
  `score(memory, tick, names, place)`, `recall(memories, tick, names, place, limit=5)`,
  `today(memories, tick)`, `reflection_prompt(world, name)`, `parse_reflection(answer, name)`,
  `reflection_agent()`.
- `world.py`: `VERSION = 3`; villagers gain `memories`, `learnings`, `views`; the world gains
  `reflection_agent_id`; `upgrade(world)` adds them to a version-2 world.
- `turn.py`: the observation's learnings, recalled memories and views.
- `runner.py`: conversation transcripts, memory hooks, reflections (`_reflect` tasks keyed by
  villager, chained), the reflection agent in `ensure_agents`, Step and Reset waiting for
  reflections, the state's new fields.

### UI

- `lib/api.ts`: villager `learnings`, `views`, `memories`; `VillageAction` gains `reflect`.
- `lib/village.ts`: `memoryLines`, `learningLines`, `turnLabel` for reflections, beliefs with
  views.
- `components/village/VillagerPanel.tsx`: "Has learned", views in "Thinks the others are",
  "Remembers" from lasting memories (10, then "Show all").

## Project Structure

```text
backend/src/agent_lab/village/memory.py                 # new
backend/src/agent_lab/village/world.py, turn.py, runner.py
backend/tests/test_village_memory.py                    # new
backend/tests/test_village_runner.py, test_village_api.py, test_village_turn.py
frontend/src/lib/api.ts, lib/village.ts (+ test), components/village/VillagerPanel.tsx
README.md, AGENTS.md
```

**Structure Decision**: one new pure module next to `turn.py`; everything else extends M7 in
place.

## Complexity Tracking

None.
