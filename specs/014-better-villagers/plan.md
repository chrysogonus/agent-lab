# Implementation Plan: M14 — Better Villagers

**Branch**: `main` (feature directory `014-better-villagers`) | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-better-villagers/spec.md`

## Summary

The work comes in five parts:

1. **Split the runner first.** `runner.py` is 1,533 lines, so the meeting runs move into
   `meeting_runs.py`. Behaviour does not change.
2. **Intentions.** The villager's existing actions become intentions (go, work, build, bring,
   see), joined by two new verbs, `build` and `bring`, and by the `until` and `say` fields. A new
   pure module `intention.py` gives the next step, and the runner takes the certain steps without
   a model call. Villagers holding an intention are asked only when something happens.
3. **What you can do here.** A new pure module `affordances.py` lists the actions that would be
   accepted now, as exact JSON. It replaces the scattered M11 and M12 hints.
4. **Reaching each other and leaving talks.**
   - A say from afar becomes a find with that line.
   - A find ends with "lost sight" when the person goes out of sight.
   - Gives go only to the villager sought or one who asked for the goods.
   - Answers that start an intention elsewhere become a goodbye and setting off. That one rule
     replaces the bedtime and meeting special cases.
5. **Memory.** Memories from another season count for less, older reflections are folded into a
   summary in the night's reflection, and the chronicle marks weather talk.

World version 7. M13's instruments measure the change against its baseline, with four new
checks.

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged
- **Storage**: the village row, world version 7
- **Testing**: pytest with `FakeLLM`, vitest; M13 evals on the real model for the success
  criteria
- **Target Platform**: local (127.0.0.1)
- **Project Type**: web application
- **Performance Goals**: no more model calls per village day than at baseline, and waits at most
  35% (SC-004)
- **Constraints**:
  - the world-version bump, `upgrade` and `_load` change in one write, with `make dev` stopped
    and the owner's database backed up;
  - the new rules reach stored agents only where they still hold the M12 text verbatim.
- **Scale/Scope**: 4 villagers, 5 intention kinds, at most 6 affordances

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass, after Phase 1 | The meeting runs leave `runner.py` (about 1,530 lines down to about 1,275). The intention steps and affordances are small pure modules. |
| II. Observable by default | Pass | Intentions start in decision runs; their `village_action` carries the intention, and every end is an event and a note. Certain steps make no model call, so no untraced call is added. |
| III. Secure local defaults | Pass | New answer fields are validated (place keys, times, names, `say` cut to the speech length); nothing is executed. |
| IV. Smallest change | Pass | The existing actions become intentions instead of a new answer shape. The affordance list reuses the refusal functions and replaces hints rather than adding to them. The summary is part of the existing nightly reflection. |
| V. Gates + traceability | Pass | Each requirement maps to a FakeLLM test; the real-model success criteria are manual checks with the M13 instruments. |

Post-design re-check: all pass. The runner split is planned as its own phase with no behaviour
change (research §7).

## Design

### Phase 1: split the runner (refactor, tests unchanged)

- New `village/meeting_runs.py`: `MeetingRuns`, a mixin holding `_meeting`, `_call_to_meeting`,
  `_open_meeting`, `_end_meeting`, `_start_meeting_run`, `_meeting_call`, `_asked_again`,
  `_still`, `_propose`, `_vote`, `_decide_meeting`, `_decided` and `_assign`.
- `Village(MeetingRuns)` keeps every name, so the tests, which use `v._still` and similar, stay
  unchanged.

### Backend

- `intention.py` (new, pure):
  - `KINDS`;
  - `start(world, name, action) -> intention`;
  - `next_step(world, v) -> step`;
  - `intention_text(intention)`, the observation line;
  - `ended_text(name, intention, why)`.
- `affordances.py` (new, pure): `can_do(world, name) -> list[(json, why)]`, from `work_refusal`,
  `give_refusal`, `buy_refusal`, the site checks and who is next to you.
- `turn.py`:
  - new `Build` and `Bring` models; `Work` gains `place` and `until`; `Find` gains `say`;
  - `parse_action`:
    - checks the new fields;
    - a say from afar becomes a find;
    - a find of a neighbour becomes a wait with the hint;
    - talking plus an intention elsewhere becomes a goodbye carrying the intention;
    - the give rule (intention target or request);
  - the observation gets the intention line and "What you can do here:", loses the hint lines,
    and gives names next to you and in sight;
  - `RULES` and `OLD_RULES`.
- `runner.py`:
  - `_apply` starts intentions and records the replaced ones;
  - `_advance` applies `next_step` for each awake villager with an intention, after the moves:
    walk, start work, set down, say, done, given up;
  - `_due` stops idle re-decisions for villagers with an intention;
  - "arrived" asks only when the intention is done;
  - `_walks`: intention walkers walk while talking, and `_to_meeting` goes;
  - bedtime ends the intention ("the day is over");
  - `_say` notes requests;
  - finds end as "lost sight";
  - `state()` gives the intention;
  - world version 7 with `upgrade`.
- `work.py`: `give_refusal` gains the reason saying what the goods are for (used when a give is
  refused by the new rule).
- `memory.py`:
  - `score` with the season;
  - `summary` importance;
  - `reflection_prompt` lists older reflections and asks for `"summary"`;
  - `parse_reflection` accepts it;
  - `REFLECT` gets the summary sentence, and `OLD_REFLECT` holds the M8 text.

  The runner folds a summary into the memories, and refreshes stored reflection agents on load.
- `chronicle.py`: notes naming weather the day did not have are marked "(talk, not the day's
  weather)".
- `evals/checks.py`: the new expectation `excludes: [words]`.
- `backend/evals/checks/`: the 4 new checks of research §6.

### Frontend

- `lib/api.ts`: `Villager.intention`; the work, build, bring and find action fields; the new
  event kinds.
- `lib/village.ts` (+ test):
  - `intentionText(intention)`;
  - `turnLabel` for build and bring, and the intention on work, move and find;
  - `stateText` uses the intention ("Building at the site until 15:00").
- `VillagerPanel.tsx`: an "Set on" line under the plan.

### Tests

- New `test_village_intention.py` and `test_village_affordances.py` for the pure modules.
- Extended: turn, runner, memory, chronicle, world, evals.
- The existing tests for the bedtime walk and walking to the meeting while talking must keep
  passing under the general rule.

## Project Structure

```text
backend/src/agent_lab/village/meeting_runs.py (new), intention.py (new), affordances.py (new),
    runner.py, turn.py, work.py, memory.py, chronicle.py, world.py, evals/checks.py
backend/evals/checks/*.json (4 new)
backend/tests/test_village_intention.py, test_village_affordances.py (new), test_village_turn.py,
    test_village_runner.py, test_village_memory.py, test_village_chronicle.py,
    test_village_world.py, test_village_evals.py
frontend/src/lib/api.ts, lib/village.ts (+ test), components/village/VillagerPanel.tsx
README.md, docs/village.md, AGENTS.md
```

**Structure Decision**:
- Village rules stay in small pure modules under `village/`, and the runner only applies them.
- The meeting runs move to a mixin so the runner is readable again.

## Complexity Tracking

None after Phase 1. The mixin is the smallest split that keeps every name and test unchanged.
