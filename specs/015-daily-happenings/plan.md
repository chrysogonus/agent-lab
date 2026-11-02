# Implementation Plan: M15 — Daily Happenings and Boat Trips

**Branch**: `main` (feature directory `015-daily-happenings`) | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-daily-happenings/spec.md`

## Summary

The work comes in three parts:

1. **Daily happenings.** A new pure module `happenings.py` picks one or two happenings per day,
   seeded by the day as the trader and the weather are, from a small catalogue (letter, visitor,
   lost animal, repair, peddler). The runner's new mixin `HappeningRuns`:
   - starts them when the day opens;
   - moves them each step (arrive, be noticed, follow, end);
   - lets villagers deal with them.

   Dealing with a happening needs one new answer, `lead`. Repairs use `work` and the peddler uses
   `buy`; letters and visitors need no answer.
2. **Boat trips.** A new pure module `boat.py` holds the boat's rules, and a new answer `row`
   (with an optional companion, who joins by its own `row`) takes the built boat around a loop
   of lake cells. Fishing from the boat is twice as fast, and the boat's talk lasts the trip.
3. **Whispers.** A new endpoint passes the owner's line to one villager's inbox from "a voice",
   as a claim. It triggers a decision, and the decision is marked `after_whisper`.

World version 8. M13's instruments get six checks, a boat scenario and new health numbers. The
frontend draws the figures and the boat, and adds a whisper box and keepsakes to the panel.

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged
- **Storage**: the village row, world version 8
- **Testing**: pytest with `FakeLLM`, vitest; M13 evals on the real model for the success
  criteria
- **Target Platform**: local (127.0.0.1)
- **Project Type**: web application
- **Performance Goals**: model calls per village day within 20% of M14's (162–172); happenings
  and boat steps make no model calls
- **Constraints**:
  - the world-version bump, `upgrade` and `_load` change in one write, with `make dev` stopped
    and the owner's database backed up;
  - the rules reach stored agents only where they still hold the M14 text verbatim.
- **Scale/Scope**: 5 happening kinds, at most 2 a day; 1 boat; whispers limited to 200
  characters and 3 per villager a day

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Happenings and the boat are small pure modules. Their runner glue is a mixin like M14's meeting runs, so `runner.py` stays about its size. |
| II. Observable by default | Pass | No new model calls. Decisions dealing with happenings, rowing or answering a whisper are ordinary traced runs, and every happening, trip and whisper is an event and a note. |
| III. Secure local defaults | Pass | The whisper endpoint binds to 127.0.0.1 like the rest. The text is length-checked and placed in one prompt as a claim, never executed. New answer fields are validated. |
| IV. Smallest change | Pass | One new answer for happenings (`lead`), with `work` and `buy` reused, and one for the boat (`row`). Whispers reuse the inbox. No new agent. |
| V. Gates + traceability | Pass | Every requirement maps to a FakeLLM test; the success criteria are manual checks with the M13 instruments. |

Post-design re-check: all pass.

## Design

### Backend

- `happenings.py` (new, pure):
  - `CATALOGUE`;
  - `day_happenings(day)`;
  - `happening_text(h, for_name)`, for the observation (fact or concerned);
  - `notice(world, v)`, giving the happenings `v` sees now;
  - `repair_at(world, place)`;
  - `lead_refusal(world, name)`;
  - `step(world) -> list[change]`: arrive, follow a leader or host, the visitor's hour, end
    when the time is over.
- `boat.py` (new, pure):
  - `LOOP`, the lake cells;
  - `row_refusal(world, name, with_)`;
  - `boat_step(world) -> list[change]`: boarding, moving, back;
  - `boat_text(world, name)`.
- `happening_runs.py` (new mixin `HappeningRuns`), runner glue:
  - `_open_happenings(day)`;
  - `_happenings()`, the step;
  - `_lead(v)`;
  - `_row(v, action)` and `_boat()`;
  - `whisper(name, text)`.
- `runner.py`:
  - `Village(MeetingRuns, HappeningRuns)`;
  - the day opening calls `_open_happenings`, and the step calls `_happenings()` and `_boat()`;
  - `_apply` handles `lead` and `row`;
  - `_decide` marks `after_whisper`;
  - `_upkeep` keeps the boat's talk;
  - `_walks` skips rowers;
  - bedtime brings the boat back;
  - `state()` gives `happenings`, `boat` and `keepsakes`;
  - `_load` accepts 7 → 8.
- `world.py`: VERSION 8 with an `upgrade` step.
- `work.py`:
  - work at a place with an open repair goes into the repair;
  - a basket there takes twice the steps;
  - `lake` joins GOODS (BASKET_STEPS halved for it).
- `trade.py`: `buy_refusal` accepts the peddler's curiosity at the square.
- `turn.py`:
  - `Lead` and `Row` models, with `parse_action` validating them;
  - the observation gets happening lines, the boat line and voice lines;
  - `RULES` gains the two answers, and the M14 text joins `OLD_RULES`.
- `intention.py`: kinds `lead` (go to the owner's door) and `row` (in the boat until `until`).
- `affordances.py`: lead, mend, trade for the curiosity, row.
- `chronicle.py`: "Today: …" from the day's happenings.
- `health.py`: the counts for happenings, dealt, boat trips, whispers and whispers followed.
- `evals/`:
  - fixtures gain `happenings` (and the boat via `built`);
  - scenarios gain the condition `boat_trip`;
  - six new checks and one scenario.
- `api.py`: `POST /village/villagers/{name}/whisper`.

### Frontend

- `lib/api.ts`: types for happenings, the boat, keepsakes, the health fields, the new event kinds
  and actions, and `whisper(name, text)`.
- `lib/village.ts` (+ test):
  - `happeningText`;
  - `turnLabel` for lead, row and "after a whisper";
  - `boatCells`.
- `components/village/pixels.tsx` (+ test): figures for the postman, visitor, animal and peddler;
  the repair mark; the boat with its rowers.
- `VillagerPanel.tsx`: a whisper box (200 characters, the answer shown) and the keepsakes.
- `HealthPanel` / `lib/health.ts`: the new numbers.

### Tests

- New `test_village_happenings.py` and `test_village_boat.py` for the pure modules.
- Extended: runner, turn, work, trade, world, chronicle, health, evals, api; `village.test.ts`,
  `pixels.test.ts`, `health.test.ts`.

## Project Structure

```text
backend/src/agent_lab/village/happenings.py, boat.py, happening_runs.py (new), runner.py,
    world.py, work.py, trade.py, turn.py, intention.py, affordances.py, chronicle.py, health.py,
    evals/fixtures.py, evals/scenarios.py, api.py
backend/evals/checks/*.json (6 new), backend/evals/scenarios/boat-trip.json
backend/tests/test_village_happenings.py, test_village_boat.py (new), and the extended tests
frontend/src/lib/api.ts, lib/village.ts, lib/health.ts (+ tests),
    components/village/pixels.tsx, VillagerPanel.tsx, HealthPanel.tsx
README.md, docs/village.md, docs/api.md, AGENTS.md
```

**Structure Decision**:
- The rules live in pure modules, and the runner applies them through a mixin.
- The frontend's drawing stays in `pixels.tsx`, with its logic in tested pure functions.

## Complexity Tracking

None. The mixin follows M14's meeting split, and no new agent or dependency is added.
