# Feature Specification: M7 — Village Life

**Feature Branch**: `main` (feature directory `007-village-life`)

**Created**: 2026-10-31

**Status**: Draft

**Input**: Agent Lab milestone M7, building on M6 (`specs/006-village/`): a bigger map with a
home for each villager; villagers sleep at home at night and get up and go to bed at their own
times; they no longer all act and move at the same moment; they can talk only when standing
directly next to each other, meeting on purpose or by chance, and may or may not start a
conversation; they usually know where the others are; their M6 daily routines continue.

## Context

M6 gave the village four villagers (Mayor Hilde, Jonas the fisher, Greta the farmer, Lina the
flower girl) on a 20 × 15 map with six places, a shared 10-minute tick in which all four act at
once, and a "nearby" rule (same place, or within 3 cells) for hearing speech. The pixel-art view
followed. Watching it, the owner wants the village to feel more alive: villagers with homes and
a day-night rhythm, movement that is not in lockstep, and conversations that only happen when
two villagers actually meet.

All M6 contracts apply unchanged: each villager turn is an ordinary traced run of its block
agent, tagged with the world time it belongs to; the village never calls the model directly;
an answer that is not a valid action makes the villager wait, with the reason recorded; the
server runs the village, the owner can start, pause, step, reset and change the pace, and the
village pauses itself when nobody watches or every turn keeps failing; tests use the scripted
fake model only.

This milestone moves the remaining roadmap back by one: M8 MCP, M9 Harness, M10 Agent memory,
M11 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - A day and a night in a bigger village (Priority: P1)

The owner opens the Village view and sees a larger village: the six places and four small
houses, one per villager near its work. It is early morning; everyone is asleep at home. As the
clock runs, Jonas gets up first and walks to the pier, the others follow at their own times.
In the evening they head home one by one and go to bed; the view shows who is asleep. Once
everyone sleeps, the night passes quickly until the first villager wakes.

**Why this priority**: homes and a day-night rhythm are the frame for everything else, and the
bigger map is needed to fit the homes.

**Independent Test**: with the scripted model, running the village from the start of day 1
into day 2 shows each villager leaving home within a step of its wake-up time, being home and
asleep from its bedtime until its next wake-up time, and taking no turns while asleep.

**Acceptance Scenarios**:

1. **Given** a new world, **When** the owner opens the Village view, **Then** the map shows the
   six places, four homes labelled with their owner's name, and every villager asleep in its
   home before the first wake-up time.
2. **Given** a villager's wake-up time arrives, **When** the village runs, **Then** that
   villager wakes, its next turn says it has just woken at home, and it may leave.
3. **Given** a villager's bedtime arrives while it is away, **When** the village runs, **Then**
   it walks home without further decisions, goes to sleep on arrival, and its events record
   both.
4. **Given** a villager is asleep, **When** time passes, **Then** it takes no turns, others who
   reach its door cannot talk to it, and the view marks it asleep.
5. **Given** every villager is asleep, **When** the village runs, **Then** time advances without
   waiting the set interval until the next wake-up time.

---

### User Story 2 - Villagers that move at their own pace (Priority: P2)

On the map, villagers no longer jump all at once. Each one walks and decides on its own
rhythm, so at any moment one may be walking, another deciding, another talking.

**Why this priority**: lockstep movement is the most visible thing that makes the village feel
mechanical.

**Independent Test**: with the scripted model, over one village hour the moments at which the
four villagers move and decide are not all the same, and no villager ever moves more than one
cell at a time.

**Acceptance Scenarios**:

1. **Given** four awake villagers, **When** the village runs for one village hour, **Then** the
   view shows their moves and decisions at different moments, not four at once.
2. **Given** a villager has decided to go somewhere, **When** it walks, **Then** it moves one
   cell at a time along walkable cells by a shortest path, without a model decision per step,
   and decides again when it arrives or something happens on the way (someone next to it
   speaks to it, or it reaches the villager it was looking for).
3. **Given** a slow model answer for one villager, **When** others are ready, **Then** the
   others keep walking and deciding; only the waiting villager stands still.

---

### User Story 3 - Meeting and talking face to face (Priority: P3)

Villagers can only talk to someone standing directly next to them. The mayor, needing flowers
for the festival, goes looking for Lina; she thinks Lina is at the garden, finds her gone, and
walks on to the square where she finds her. Another time, Greta and Jonas pass each other on
the path to the market and stop for a chat — or nod and walk on.

**Why this priority**: conversations are the heart of the village; the adjacency rule makes
meetings meaningful and gives searching a purpose.

**Independent Test**: with the scripted model, speech reaches only the villager it is said to
when they stand next to each other; a villager not next to anyone cannot talk; two villagers
who become neighbours are both told so on their next decision and may start, continue or end
a conversation.

**Acceptance Scenarios**:

1. **Given** two awake villagers on neighbouring cells, **When** one says something to the
   other, **Then** the other hears it on its next decision, and nobody else does.
2. **Given** a villager with no awake neighbour, **When** it answers with speech, **Then** it
   waits, with the reason "nobody next to you".
3. **Given** two villagers' paths bring them next to each other, **When** either decides next,
   **Then** its observation says who is next to it, and it may greet them, start talking, or
   walk on.
4. **Given** two villagers are talking, **When** one replies, **Then** both stay where they are
   while the conversation lasts; it ends when either says goodbye, walks away, or after 10
   lines in a row between the two.
5. **Given** a villager decides to find another villager, **When** it walks, **Then** it heads
   for where it believes that villager is; if it arrives and the other is not there, its
   events say so and it decides where to look next.

---

### User Story 4 - Knowing where the others are (Priority: P4)

Each villager has an idea of where the others are: from the village's known routines, from
whom it saw lately, and from what it heard. That idea can be out of date.

**Why this priority**: deliberate meetings need a belief about where people are; out-of-date
beliefs make searching and chance meetings interesting.

**Independent Test**: each observation lists, for every other villager, where the villager
believes them to be and how it knows (seen at a time, heard from someone, or their usual
routine); seeing someone updates it; it is not updated when the other moves out of sight.

**Acceptance Scenarios**:

1. **Given** a villager sees another within sight, **When** it decides next, **Then** its
   observation says where it saw them and when.
2. **Given** a villager hears "Lina is at the square" from someone it talks to, **When** it
   decides next, **Then** it believes Lina is at the square, heard from that villager.
3. **Given** a villager has not seen or heard about someone today, **When** it decides, **Then**
   its observation gives that villager's usual whereabouts for the time of day, marked as
   their routine.

### Edge Cases

- Two villagers stand on the same cell → they count as next to each other; cells still hold
  any number of villagers.
- Three villagers stand together → each speech goes to one addressee (or, with no addressee,
  to every awake neighbour); a conversation is between pairs, so a third may join by speaking.
- A villager speaks to someone who stepped away before the line was delivered → the line is
  lost, the speaker's events say the other had walked off.
- A villager is mid-conversation when its bedtime comes → it says nothing more, walks home and
  sleeps; the other is told it left.
- A villager is talking or deciding when the owner presses Pause → the current turns finish,
  then nothing else happens.
- Step while paused → advances the village by one step of time (10 village minutes, the M6
  tick), running every decision that falls in it.
- A villager's agent was deleted → it stands still (or sleeps) and waits until the owner
  resets, as in M6.
- Reset → everyone asleep at home, memories and beliefs cleared, the clock back at the start
  of day 1; past turns stay in the database.
- A stored M6 world (old map) on first start → the village starts fresh on the new map, saying
  so once; old turns stay.
- Every decision fails 3 times in a row across all awake villagers → the village pauses itself
  and says why.

## Requirements *(mandatory)*

### Functional Requirements

**Map and homes**

- **FR-001**: The world MUST be a grid map larger than M6's, about 32 × 22 cells, with the six
  M6 places, walkable paths, water that cannot be entered, and four homes, one per villager,
  each next to that villager's work place and drawn as a small house with its owner's name.
- **FR-002**: Each home MUST have a door cell; a villager at home is inside it (shown at the
  door when awake there, hidden or marked asleep when sleeping). Villagers do not enter other
  villagers' homes.

**Day and night**

- **FR-003**: Each villager MUST have its own wake-up time and bedtime, part of its character:
  Jonas 05:00–21:00, Greta 05:30–21:30, Lina 06:30–22:00, Hilde 07:30–23:00.
- **FR-004**: The clock MUST start on day 1 at 04:30 with everyone asleep at home. A villager
  wakes at its wake-up time; at its bedtime it walks home without further decisions and falls
  asleep on arrival. A sleeping villager takes no turns and cannot be spoken to.
- **FR-005**: While every villager sleeps, the village MUST advance time without waiting the
  set interval until the next wake-up time.

**Time and pace**

- **FR-006**: The clock MUST advance in steps of 10 village minutes, as in M6. Walking MUST move
  a villager one cell per step along a shortest walkable path without a model decision; walkers
  MUST NOT all move at the same moment within a step, so the view shows moves spread over the
  step.
- **FR-007**: A villager MUST decide (take a turn) only when it needs to: when it wakes, when it
  arrives, when it has nothing to do, when a villager next to it speaks to it or newly comes
  next to it, or when it reaches or misses the villager it was looking for. Each villager
  decides on its own, without waiting for the others; decisions of different villagers MAY run
  at the same time.
- **FR-008**: A villager whose decision is still running MUST stand still; the others MUST go
  on walking and deciding. Steps never overlap: a step ends only when the decisions it started
  have finished.

**Meeting and talking**

- **FR-009**: Two villagers are next to each other when they stand on the same cell or on
  neighbouring cells (including diagonals). Only awake villagers next to each other can talk.
- **FR-010**: A villager's actions MUST be: go to a named place or home, find a named villager,
  say a text to one villager next to it (or to every awake neighbour when no addressee is
  given), end the conversation (say goodbye), or wait. Speech with no awake neighbour, to a
  villager not next to it, or to an unknown villager MUST count as waiting, with the reason.
- **FR-011**: A villager spoken to MUST decide next with the words in its observation. While a
  conversation lasts, both villagers MUST stay put; it ends when either says goodbye, starts
  walking, falls asleep, or after 10 lines in a row between the same two, and both record how
  it ended.
- **FR-012**: When two villagers newly come next to each other, both MUST be told on their next
  decision; each may greet, start a conversation, or carry on. Nothing forces them to talk.
- **FR-013**: "Find a villager" MUST walk towards where the villager believes the other is, and
  re-aim when it sees the other on the way; on arriving without finding them it records that
  and decides again.

**Knowing where others are**

- **FR-014**: Each villager MUST keep, for every other villager, a belief: a place or cell, when
  it was formed, and how (seen, heard from a named villager, or usual routine). Seeing someone
  within 6 cells MUST update the belief; hearing a place named for someone in speech addressed
  to it MUST update it as heard; with no sighting or hearsay that day the belief MUST be that
  villager's usual whereabouts for the time of day.
- **FR-015**: Each observation MUST list the villager's beliefs about the others, who is next to
  it and awake, who it sees within 6 cells, what was said to it since its last decision, its
  conversation state, its wake-up time and bedtime, and its last 10 events.

**Routines and persona**

- **FR-016**: The villagers' personas and daily routines from M6 MUST continue (work places by
  time of day, the mayor's harvest festival, trading at the market), extended with their home
  and their sleeping hours.

**Controls, persistence, tracing (M6 carried over)**

- **FR-017**: The world (positions, sleep, conversations, beliefs, clock) MUST be stored after
  every step and survive restarts, resuming paused. Reset MUST return to the starting state.
  Start, pause, step (one 10-minute step), the interval between steps (1–30 seconds, default 5),
  and both automatic pauses (60 seconds without a viewer; 3 steps in a row in which every
  decision failed) MUST work as in M6.
- **FR-018**: Each decision MUST be one traced run of the villager's block agent, tagged with
  the step it belongs to; village runs stay out of the main past-runs list and are listed per
  villager in the Village view. Edits of a villager's agent apply from its next decision.

**UI**

- **FR-019**: The Village view MUST show the bigger map with homes, every villager's state
  (asleep, walking, deciding, talking, idle) on the map and in the list, speech as it happens
  (in the dialog box, newest at the bottom), and who is talking with whom. Moves MUST appear at
  different moments, not all at once. It MUST stay keyboard operable and fit a laptop screen.
- **FR-020**: A villager's panel MUST additionally show its sleeping hours and its current
  beliefs about where the others are.

**Quality**

- **FR-021**: Tests MUST use the scripted fake model only and cover: the map and homes, waking
  and bedtimes, no turns while asleep, the fast night, staggered moves, decisions only when
  needed, a slow decision not blocking others, adjacency for speech, conversation start, length
  limit and ending, finding a villager (found and missed), beliefs (seen, heard, routine),
  persistence, reset, starting fresh from an M6 world, and the auto-pauses.
- **FR-022**: All quality gates MUST pass; every requirement maps to a test or an explicit
  manual check in `tasks.md`.

### Key Entities

- **World**: the map (cells, places, homes, water), the clock (step number, time), its state
  (running or paused, interval), the villagers, the ongoing conversations.
- **Home**: owner, cells, door cell.
- **Villager**: name, role, personality, home, work place, wake-up time, bedtime, the agent
  that plays it, position, state (asleep, walking, deciding, talking, idle), current goal
  (a place, home, or a villager to find), beliefs, last 10 events.
- **Belief**: about whom, where (place or cell), when, source (seen, heard from whom, routine).
- **Conversation**: the two villagers, its lines so far, how it ended.
- **Event**: time, kind (woke, slept, set off, arrived, met, saw, heard, said, missed, waited,
  conversation ended), text, and the villagers involved.
- **Turn**: a run of a villager's agent for one decision, with its observation and parsed action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over one scripted village day, each villager leaves home within one step of its
  wake-up time and is asleep at home from its bedtime plus the walk home until its next
  wake-up time.
- **SC-002**: Over 100 scripted steps, villagers never move more than one cell per step, always
  stand on walkable cells, and no step has all walking villagers moving at the same moment.
- **SC-003**: 100% of tested speeches reach exactly the villagers next to the speaker they were
  meant for; 0% reach anyone not next to the speaker.
- **SC-004**: While all villagers sleep, a village night passes in under 15 seconds of wall time
  at the default interval.
- **SC-005**: Compared with M6, walking villagers cause no model calls per step: over one
  scripted village day, decisions happen only on the triggers of FR-007.
- **SC-006**: On the real model, within one village day, at least two conversations of 3 or
  more lines take place, at least one of them after a villager deliberately went to find the
  other, and the mayor raises the festival in one of them (manual check).

## Assumptions

- The four villagers, their personas and the six places stay as in M6; the map is redrawn
  larger with the same places plus homes (no map editor).
- Homes sit next to work places: the mayor's house near the town hall, the fisher's hut near
  the pier, the farmhouse by the fields, the flower girl's cottage by the garden.
- Sleeping hours are fixed per villager (FR-003), not chosen by the model; the model only sees
  them, so routines stay reliable.
- Villagers see others within 6 cells (for beliefs and noticing), but talk only when next to
  each other.
- "Usual whereabouts" come from each villager's routine as written in its persona, summarised
  per time of day (e.g. Jonas: pier in the early morning, market at midday).
- The stagger of moves within a step is decided by the village, not by the model, and does not
  change where villagers end up; with the model's answer times varying, decisions spread out
  naturally.
- A conversation line counts as one decision of the speaker; the listener answers on its own
  next decision.
- The pixel-art style of the current view carries over; homes and new tiles are drawn in code
  the same way, with no new dependency.
- A stored M6 world is not migrated; the village starts fresh on the new map.
