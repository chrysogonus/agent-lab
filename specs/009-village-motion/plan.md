# Implementation Plan: M9 — Village Motion and Look

**Branch**: `main` (feature directory `009-village-motion`) | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-village-motion/spec.md`

## Summary

Backend: walkers advance up to 3 cells per step in interleaved rounds (one published single-cell
move at a time, checks after each); move and find are refused while talking; goodbye takes an
optional `place` or `villager` and sets off after ending the conversation; the villagers' rules
say so, and stored villager agents whose prompt still holds the previous rules text get the new
text on load. Frontend: straight linear glides, a two-frame walk cycle, per-villager idle
rhythms (breathing, blinking, glancing), work animations with props at each villager's work
place, and world decorations (shadows, chimney smoke, butterflies, lake rings, fireflies, a sky
gradient per time of day), all CSS-animated and still under reduced motion.

## Technical Context

**Language/Version**: Python 3.12, TypeScript / Next.js 16 · **Dependencies**: unchanged ·
**Storage**: unchanged (world version 3) · **Testing**: pytest with `FakeLLM`, vitest ·
**Constraints**: no image assets, CSS animation only, reduced motion respected, decorations
never intercept clicks

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Movement rounds and the action change in the existing modules; art in code |
| II. Observable by default | Pass | Decisions unchanged as traced runs; refused moves record their reason |
| III. Secure local defaults | Pass | The goodbye destination is validated like move and find |
| IV. Smallest change | Pass | No new module, endpoint or dependency |
| V. Gates + traceability | Pass | FR → test map in `tasks.md` |

## Design

### Backend (`village/`)

- `runner.py`: `CELLS_PER_STEP = 3`; `_advance` moves walkers in rounds (round 1: each walker one
  cell, round 2, round 3), `_look` and a publish after each move, `gap = interval / (moves + 1)`
  in the loop (estimated as walkers × 3), 0.1 s in Step; `_apply` for goodbye with a destination;
  `_refresh_rules()` on load (research §3).
- `turn.py`: `Goodbye` gains `place` and `villager`; move and find while talking → wait; rules
  text with the goodbye destination; `PREVIOUS_RULES` (the M7 text) for the refresh.
- `state()`: villagers gain `work` (their work place key).

### Frontend

- `lib/village.ts`: `activity(villager)`, `rhythm(name)` (a stable per-villager offset),
  `PERIOD_SKY`; `PERIOD_TINT` goes.
- `components/village/pixels.tsx`: walk frames, eyes drawn apart for blinking and glancing, props
  (rod, hoe, watering can, papers), shadows, smoke, butterflies, rings, fireflies, sky gradient.
- `VillageView.tsx`: activities and props per figure, decorations per period and owner state.
- `globals.css`: keyframes for walk, breathe, blink, glance, props and decorations; all off under
  `prefers-reduced-motion`.

## Project Structure

```text
backend/src/agent_lab/village/turn.py, runner.py
backend/tests/test_village_turn.py, test_village_runner.py
frontend/src/lib/village.ts (+ test), components/village/pixels.tsx, VillageView.tsx,
frontend/src/app/globals.css
README.md
```

## Complexity Tracking

None.
