# Implementation Plan: M11 — Plans and Purpose

**Branch**: `main` (feature directory `011-plans-and-purpose`) | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-plans-and-purpose/spec.md`

## Summary

Backend: a new `plan.py` holds the "Village planner" block agent; the runner runs it for each
villager on waking and after long conversations (at most two revisions a day), like the
reflections, and the observation shows the plan with the current and next entry marked. The
observation is regrouped into what the villager knows for sure and what others told it (marked as
claims); new villager rules add work, give and "trust what you see over what you hear", and
stored agents with the M7 or M9 rules get them. A say repeating one of the speaker's last three
lines becomes a wait. A new `work.py` holds work, baskets and the festival stalls: working steps
of everyone on a place add up for tending and baskets, baskets are given to villagers or set out
on the square, and the stalls reach the observation, festival memories and the chronicle. World
version 5, upgraded from 4. Frontend: "Today's plan" in the villager panel, the working state,
turn labels for plan, work and give, and stalls and carried baskets on the map.

## Technical Context

**Language/Version**: Python 3.12, TypeScript / Next.js 16 · **Dependencies**: unchanged ·
**Storage**: the village row, world version 5 · **Testing**: pytest with `FakeLLM`, vitest ·
**Constraints**: plan runs never count as decisions or toward the failure pause; one plan per
villager per day; the state stays small (plans ≤ 6 entries) because it is published after every
move; no image assets, decorations never intercept clicks

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Two small new modules (`plan.py`, `work.py`) hold the new rules; `runner.py` only wires them (plan tasks like reflections, one call in `_advance`) |
| II. Observable by default | Pass | Plans and revisions are ordinary traced runs of a block agent tagged with the villager; work and give are decisions recorded as `village_action` |
| III. Secure local defaults | Pass | The planner's answer is validated, cut and redacted after decoding, never executed |
| IV. Smallest change | Pass | No new endpoint or dependency; the planner reuses the reflection pattern; tending keeps M10's growth rules and only changes what counts |
| V. Gates + traceability | Pass | FR → test map in `tasks.md`; view logic (plan entry text, turn labels, state text, stalls text) in `lib/village.ts` with vitest |

Post-design re-check: unchanged, all pass. One spec edge case changed during design: work while
talking is allowed (working together depends on it), and FR-014 no longer lists "still talking".

## Design

### Backend (`village/`)

- `plan.py` (new, research §1): `PLAN_ENTRIES = 6`, `PURPOSE_TEXT = 120`, `REVISIONS = 2`,
  `plan_prompt(world, name, revise)`, `parse_plan(answer, name) -> (plan entries | None,
  reason)`, `plan_lines(plan, minute)`, `marks(plan, minute) -> (current, next)`,
  `entry_text(entry)`, `planner_agent()`.
- `work.py` (new, research §4): `GOODS`, `goods_at`, `work_refusal`, `give_refusal`,
  `work_step(world) -> list[tuple[str, str]]`, `stalls_text`, `empty_stalls()`.
- `world.py`: `VERSION = 5`; `new_world()` adds `plan`, `basket`, `working`, `said` per villager
  and `stalls`, `harvest`, `planner_agent_id`; `upgrade()` chains 2 → 3 → 4 → 5.
- `seasons.py`: `end_day` clears the stalls when winter comes.
- `turn.py`:
  - `Work` and `Give` actions.
  - `parse_action` handles work, give and repeated lines; `same_line`.
  - `observation` is regrouped into facts and claims, with plan, basket, working, stalls and
    "What you said lately"; `seen_text`.
  - `RULES` (M11, in two steps: US1–US2 sentences, then work and give), `OLD_RULES = (M7, M9,
    the first M11 step)`.
- `chronicle.py`: claims marking in `chronicle_prompt`; plans arrive through the day record; the
  stalls line on the festival day.
- `runner.py`:
  - `_load` upgrades versions 2–4; `_refresh_rules` checks `OLD_RULES`.
  - `ensure_agents` creates the planner; Reset keeps its id.
  - `self.plans`, `_start_plan(name, revise)` and `_plan(...)`, started in `_schedule` (waking)
    and `_end_conversation` (≥ 4 lines); `_settle` waits for them.
  - `_apply` handles work and give. `_set_off`, `_seek` and bedtime end working. `_say` keeps
    `said`. The conversation note marks claims.
  - `_advance` calls `work_step` in place of counting standing villagers, and turns baskets into
    events, triggers and notes.
  - `_remember_festival` names the stalls.
  - `state()` adds `plan` (today's, with marks), `basket`, `working`, the `working` state and
    `stalls`, and drops `said`, `harvest` and `planner_agent_id`.

### Tests

- The shared test responder (`tests/test_village_runner.py`) answers planner prompts: a scripted
  `plan` queue, otherwise a default valid plan, so existing tests keep running. Assertions that
  count a villager's turns now include the plan runs.
- New `test_village_plan.py` and `test_village_work.py` for the pure modules; runner, turn,
  chronicle, world and API tests extended.

### Frontend

- `lib/api.ts`: `Villager.plan`, `basket`, `working`, the state `working`, `VillageState.stalls`,
  the plan, work and give `VillageAction`s and the new event kinds.
- `lib/village.ts` (+ test): `planEntryText`, `stateText` for working, `turnLabel` for plan, work
  and give, `stallsText`.
- `VillagerPanel.tsx`: the "Today's plan" section.
- `seasons.tsx`: `Stalls` and `Basket`; `VillageView.tsx` draws them (stalls in autumn or when
  goods are out, a basket beside each carrying villager).

## Project Structure

```text
backend/src/agent_lab/village/plan.py (new), work.py (new), world.py, seasons.py, turn.py,
    chronicle.py, runner.py
backend/tests/test_village_plan.py (new), test_village_work.py (new), test_village_runner.py,
    test_village_turn.py, test_village_chronicle.py, test_village_world.py,
    test_village_seasons.py, test_village_api.py
frontend/src/lib/api.ts, lib/village.ts (+ test), components/village/VillagerPanel.tsx,
    seasons.tsx, VillageView.tsx
README.md, AGENTS.md
```

## Complexity Tracking

None.
