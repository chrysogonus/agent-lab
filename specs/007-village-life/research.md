# Research: M7 — Village Life

Decisions inside the existing stack; no new dependencies.

## 1. Steps and decisions are separate

- **Decision**: M6's tick (four turns, then everything applied together) becomes two parts.
  The **step** (every interval, under the step lock) advances the clock 10 minutes, applies the
  sleep schedule, moves the walkers and starts the decisions that are due. A **decision** is an
  asyncio task per villager (at most one each) that runs the villager's turn exactly as in M6
  (`new_run` + `execute_run`, tagged with the step it started in) and applies its action as soon
  as it finishes, then starts any decision that action triggered (an addressee is spoken to).
- **Why**: walking no longer needs the model (SC-005); villagers decide at different moments
  because model answers take different times and triggers differ; a slow answer only freezes its
  own villager (FR-008). Decisions are applied synchronously on the event loop (no `await`
  between reading and writing the world), so they need no lock against the step.
- **Step and Pause**: Step (paused only) runs one step and awaits the decisions it started;
  decisions triggered by those decisions are not started while paused, so Step always ends.
  Pause stops the loop; decisions in flight finish and apply, nothing new starts.
- **Reset**: takes the step lock, marks the village as resetting, awaits decisions in flight
  (their results are discarded), then builds the new world.
- **Failure self-pause**: each finished decision records success or failure; at the end of every
  step, if at least one decision finished since the last step and all of them failed,
  `failed_ticks` grows, otherwise it resets when any succeeded; at 3 the village pauses (FR-017).
- **Alternatives**: keep the synchronous tick and only animate moves at different times
  (cosmetic; still four model calls per tick); a fixed rotation of one villager per tick (slow,
  and conversations would crawl).

## 2. Staggered moves

- **Decision**: in each step the walkers move one at a time in an order rotated by the step
  number; the runner publishes the state after each move and sleeps `gap` between moves, where
  `gap = interval / (walkers + 1)` in the running loop and a fixed 0.25 s in Step. A
  `move_gap` constructor argument (tests pass 0) overrides it.
- **Why**: the view (which already animates position changes) shows moves spread over the step
  (FR-006); end positions are identical to moving everyone at once.

## 3. Triggers (when a villager decides)

- **Decision**: a villager carries `triggers` (reasons since its last decision). A decision
  starts for an awake villager not going to bed and without a decision in flight when it has a
  trigger, or when it is idle (no goal, not walking) and 3 steps (30 minutes) passed since its
  last decision. Triggers: `woke`, `arrived`, `met` (an awake villager became adjacent),
  `spoken to`, `found`, `missed`, `conversation ended`. A walking villager has no idle trigger.
- **Why**: FR-007; 30 minutes keeps an idle villager from going silent for hours without a
  model call every step.

## 4. Sleep

- **Decision**: wake-up and bedtime per character (FR-003) in minutes of the day. Each step:
  an asleep villager whose wake-up time has come wakes at its door (trigger `woke`, yesterday's
  beliefs cleared); an awake villager past its bedtime gets the goal `home` with `bedtime`
  set: it walks without decisions, its conversations end ("went home to bed"), a decision in
  flight is discarded on completion; on reaching its door it falls asleep (events `bedtime`,
  `slept`). Asleep villagers are not adjacent to anyone and take no turns.
- **Fast night**: while every villager sleeps, the loop sleeps 0.2 s per step instead of the
  interval (a 6-hour night ≈ 36 steps ≈ 7 s, SC-004).
- **Clock**: step `t` → minutes = 270 + 10·t (day 1, 04:30, everyone asleep).

## 5. Meeting and conversations

- **Adjacent**: same cell or one of the 8 neighbours (Chebyshev distance ≤ 1), both awake.
- **Met**: after each step and after each applied move, every newly adjacent pair (not adjacent
  at the end of the previous check) gives both a `met` trigger and event. Nothing forces speech.
- **Speech**: `say` with `to` needs that villager adjacent and awake; without `to` it goes to
  every awake neighbour; with none, or to someone not adjacent → `wait` with the reason. A line
  goes into each hearer's inbox, events and the world's speech log (last 8 lines), and the
  hearer gets `spoken to`.
- **Conversation**: a pair record created by the first line between two villagers. While any
  conversation includes a villager, it does not walk. It ends when either says `goodbye`, takes
  `move` or `find`, goes to bed, the two are no longer adjacent, 3 steps pass without a line,
  or the pair reaches 10 lines; both get a `conversation ended` event with the reason. After
  10 lines the pair is "talked out": speech between them is `wait` ("you have talked a long time
  with X; say goodbye or go on") until they are apart.

## 6. Finding someone and beliefs

- **Beliefs**: per villager, per other: `{where, cell, tick, source, from}` with `source` one of
  `seen` (within 6 cells: the cell, and the place if any), `heard` (a heard line mentions the
  other's name and exactly one place label or "home": that place, from the speaker). Missing
  beliefs fall back to the routine: the character's usual place for the current hour (or home
  outside its waking hours). Beliefs are cleared when the villager wakes (a new day).
- **Find**: the goal targets the believed cell (seen) or the believed place's cells (heard,
  routine), or the door of the other's home. Each step the target follows the other while it is
  seen. Adjacent to the other → goal done, `found`. Reached the target without being adjacent →
  `missed` with what it found ("Lina is not at the flower garden", "Hilde is asleep").
- **Alternatives**: telling every villager where everyone is (no searching); free-text location
  extraction by a model (an extra call and nondeterministic).

## 7. The map

- **Decision**: 32 × 22 cells as text rows in `world.py`. New non-walkable cells: `B` town hall
  building (drawn there, no longer on the row above), houses `h` (Hilde, near the town hall),
  `j` (Jonas, by the pier), `g` (Greta, by the fields), `l` (Lina, by the garden), each 3 × 2
  cells with its door the cell below the middle of its bottom row; `t` trees and `i` lamps.
  Tests check size, characters, reachability of every place and door from every other, the
  doors' walkability and the pier at the water.

## 8. Persistence

- **Decision**: the world JSON gains `version: 2`, `conversations`, `log` and per-villager
  `asleep`, `bedtime`, `goal`, `triggers`, `last_decided`, `beliefs`, `neighbours`. Decisions in
  flight are not stored; after a restart the world loads paused and those villagers simply
  decide again on the next trigger. A stored world without `version: 2` is replaced by a new
  one with `paused_reason` "the village moved to a bigger map and started fresh".

## 9. Streaming and view

- **Decision**: `{"type": "state"}` after every move, step, applied decision and control change;
  `{"type": "decision_started", "villager", "run_id"}` as a decision starts (the panel lists it
  live). The view keeps animating position changes, so the staggered publishes look like
  villagers walking at their own times. Sleeping villagers are not drawn; their house shows "Zz".
