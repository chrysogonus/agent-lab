# Feature Specification: M9 — Village Motion and Look

**Feature Branch**: `main` (feature directory `009-village-motion`)

**Created**: 2026-11-01

**Status**: Draft

**Input**: "Now I want an upgrade on the movements of the villagers. They are kind of slow. Also
make the whole world even more visually stunning and beautiful. Also when they talk to each
other and are in a conversation they stay still. Only if they are done with the conversation
they move away from each other. What do you think? Also make their idle animations more
interesting."

## Context

After M7 and M8 the villagers live, meet, talk, remember and learn, but watching them is slow:
a villager walks one cell per 10-minute step, so crossing the village takes minutes, and each
move is a jump from cell to cell. A villager in a conversation can still decide to walk off
mid-sentence. Standing villagers do nothing visible. The owner wants livelier movement, polite
conversations, idle animations with character and a more beautiful world.

All earlier contracts apply: every model call is a traced run of an agent; invalid answers
change nothing and record why; tests use the scripted fake model only; no new dependency;
reduced-motion preferences are respected.

The remaining roadmap moves back by one: M10 MCP, M11 Harness, M12 Agent memory for the lab's
other agents, M13 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, watching the village on a laptop.

### User Story 1 - Livelier movement (Priority: P1)

Villagers walk three times as far per step and glide smoothly from cell to cell, with a walking
animation, instead of jumping one cell every few seconds.

**Why this priority**: slowness is the owner's first complaint and the most visible.

**Independent Test**: with the scripted model, a walking villager advances up to three cells per
step, one cell at a time, interleaved with other walkers; on screen, villagers glide between
cells and their legs move while walking.

**Acceptance Scenarios**:

1. **Given** a villager walking to a place more than three cells away, **When** a step passes,
   **Then** it is three cells closer, having passed through each cell in turn.
2. **Given** several walkers, **When** a step passes, **Then** their single-cell moves are
   interleaved and published one at a time, never two at once.
3. **Given** a walker passes next to another villager on its way, **When** it is next to them
   during the step, **Then** both are told they met, as before, even if it walks on.
4. **Given** the view, **When** a villager moves one cell, **Then** it glides there in a straight
   line and its walking animation plays; with reduced motion it moves without animation.

---

### User Story 2 - Conversations hold until goodbye (Priority: P1)

Two villagers in a conversation stay where they are until one of them says goodbye. A villager
that wants to leave says goodbye and may name where it goes next; it sets off right after.

**Why this priority**: the owner asked for it explicitly; walking off mid-conversation reads as
rude and confuses the other villager.

**Independent Test**: with the scripted model, a villager in a conversation that answers "move"
or "find" waits with the reason "say goodbye first"; a goodbye with a place ends the
conversation and the villager walks there from the next step.

**Acceptance Scenarios**:

1. **Given** a conversation, **When** either villager answers move or find, **Then** it waits
   with the reason "you are talking with Lina; say goodbye first" and nobody moves.
2. **Given** a conversation, **When** a villager answers goodbye with a place or a villager to
   find, **Then** the conversation ends, the other is told who said goodbye, and the leaver sets
   off for that place or villager.
3. **Given** a conversation, **When** a villager answers goodbye without a destination, **Then**
   the conversation ends and the villager stays.
4. **Given** a conversation falls silent for 30 minutes, ends after 10 lines, or bedtime comes,
   **Then** it ends as before, so nobody is stuck.

---

### User Story 3 - Idle animations with character (Priority: P2)

Standing villagers breathe, blink and look around now and then. At their own work place they do
their work: Jonas fishes from the pier, Greta hoes the field, Lina waters the flowers, Hilde
studies her papers at the town hall. Talking villagers face each other with small gestures;
thinking villagers show a thought bubble.

**Why this priority**: it gives each villager a visible personality while waiting.

**Independent Test**: the view logic picks the idle activity from the villager's state and
place (work at its work place, talking, thinking, plain idle, walking); each activity has its
drawing and animation.

**Acceptance Scenarios**:

1. **Given** Jonas idle at the pier, **When** the view draws him, **Then** he holds a fishing
   rod whose line bobs in the water.
2. **Given** Greta idle in the fields, Lina in the flower garden or Hilde at the town hall,
   **When** the view draws them, **Then** they show their own work animation (hoe, watering can,
   papers).
3. **Given** an idle villager elsewhere, **When** time passes, **Then** it breathes, blinks and
   glances left and right at its own rhythm, not in sync with the others.
4. **Given** reduced motion, **When** the view draws idle villagers, **Then** they show their
   props without movement.

---

### User Story 4 - A more beautiful world (Priority: P3)

The village gets depth and life: soft shadows under houses and trees, smoke from chimneys of
houses whose owner is home and awake, butterflies over the flower garden by day, rings on the
lake where fish jump, a sky light that warms in the morning, glows at sunset and deepens at
night, and fireflies near the water at night.

**Why this priority**: the owner asked for a more stunning world; it builds on the existing
pixel art.

**Independent Test**: each element appears under its condition (time of day, owner at home,
reduced motion), checked with screenshots of morning, midday, sunset and night.

**Acceptance Scenarios**:

1. **Given** day, **When** the map shows, **Then** houses and trees cast soft shadows and
   butterflies flutter over the flower garden.
2. **Given** a villager awake at its door, **When** the map shows, **Then** its chimney smokes.
3. **Given** the evening, **When** the map shows, **Then** the light turns warm and dusky from top
   to bottom; at night fireflies glow near the lake and lamps and windows light up.
4. **Given** reduced motion, **When** the map shows, **Then** decorations stay still.

### Edge Cases

- A walker reaches its goal after one or two cells → it stops there and arrives within the step.
- A walker is stopped mid-step (a decision starts or someone speaks to it) → it stops at the cell
  it reached.
- A goodbye names an unknown place or villager → the goodbye still ends the conversation; the
  destination is ignored with a reason in the villager's events.
- A goodbye with a destination while not in a conversation → behaves as move or find.
- Many animated elements on a slow machine → decorations stay few (a handful of butterflies,
  rings and fireflies) and use CSS animation only.

## Requirements *(mandatory)*

### Functional Requirements

**Movement**

- **FR-001**: A walking villager MUST advance up to 3 cells per step, one cell at a time along a
  shortest walkable path, stopping early when it arrives or is stopped.
- **FR-002**: Within a step, single-cell moves of different walkers MUST be interleaved (round by
  round) and published one at a time, spread over the step; meetings, sightings and searches MUST
  be checked after every single-cell move.
- **FR-003**: The view MUST animate each single-cell move as a straight glide and show a walking
  animation (legs, bob) while a villager walks; with reduced motion, positions change without
  animation.

**Conversations**

- **FR-004**: While a villager is in a conversation, move and find MUST become waiting with the
  reason "you are talking with <names>; say goodbye first".
- **FR-005**: Goodbye MUST accept an optional destination (`place` or `villager`); it ends the
  villager's conversations and then sets off as move or find would; an invalid destination is
  ignored with a reason recorded in its events.
- **FR-006**: The agent rules MUST say that a villager stays while talking and says goodbye, with
  where it goes next, to leave.

**Idle animations**

- **FR-007**: The view MUST choose one activity per villager: walking, talking, thinking, working
  (idle at its own work place) or idle; working shows the villager's prop (Jonas rod and line,
  Greta hoe, Lina watering can, Hilde papers) with its animation.
- **FR-008**: Idle villagers MUST breathe, blink and glance around with a per-villager rhythm so
  they are not in sync.

**World**

- **FR-009**: The map MUST show soft shadows under houses and trees, chimney smoke for houses whose
  owner is awake at its door, butterflies over the flower garden by day, occasional rings on the
  lake, fireflies near the water at night, and a sky light that changes with the time of day
  (morning warmth, midday clear, sunset glow from the top, deep night).
- **FR-010**: Every ambient animation MUST stop under reduced motion; decorations MUST NOT block
  clicks on villagers.

**Quality**

- **FR-011**: Tests MUST use the scripted fake model only and cover: up to 3 cells per step,
  interleaved single-cell publishes, early arrival, meetings during multi-cell moves, move and
  find refused while talking, goodbye with and without a destination, invalid destinations;
  vitest covers the activity choice and the per-villager rhythm.
- **FR-012**: All quality gates MUST pass; every requirement maps to a test or a manual check
  (screenshots) in `tasks.md`.

### Key Entities

- **Goodbye** (action): text (optional), place or villager (optional).
- **Activity** (view only): walking, talking, thinking, working, idle; derived from state and
  place.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Crossing the village from the fields to the pier takes at most a third of the steps
  it took in M8 (scripted).
- **SC-002**: Over 100 scripted steps, no published state moves a villager more than one cell or
  more than one villager, and no step moves a villager more than 3 cells.
- **SC-003**: In scripted conversations, 100% of move and find answers during a conversation
  become waits with "say goodbye first"; 100% of goodbyes with a destination set the villager off.
- **SC-004**: Screenshots of morning, midday, sunset and night show shadows, smoke, butterflies,
  lake rings, fireflies and the changing light under their conditions (manual check).
- **SC-005**: On the real model, at least one conversation in a village day ends with a goodbye
  that names a destination, and no villager leaves a conversation without one (manual check).

## Assumptions

- Three cells per step (about 30 m a minute) feels lively without making conversations rare;
  the interval between steps stays 5 seconds by default.
- Villagers keep facing the viewer (front sprites); walking is shown by legs and bob, not by
  turning.
- Decorations are drawn in code in the existing pixel style; no image assets, no new dependency.
