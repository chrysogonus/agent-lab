# Feature Specification: M6 — The Village (first slice)

**Feature Branch**: `main` (feature directory `006-village`)

**Created**: 2026-10-31

**Status**: Draft

**Input**: Agent Lab milestone M6, the first slice of the Phase 2 Village, prioritized before
MCP, Harness, Memory and RAG (now M7–M10): a small 2D village with four villagers of different
personalities (the mayor, a fisher, a farmer and the flower girl), each an Agent Lab agent,
acting in turns on a shared world clock, with every turn traced like any other run.

## Context

Since M1 the roadmap has ended in a "village": a 2D world of LLM villagers on the same runtime,
driven by a tick runner, with live-editable prompts and per-agent history. M1–M5 built that
runtime: traced agents with stable ids and config versions, a step-wise ReAct loop, a model
choice per agent (M4) and block agents (M5). The owner now wants to see agents live together.

A **villager** is a character (name, role, personality, home) played by an Agent Lab block
agent. The **world** is a small grid map with named places and a clock. On each **tick** every
villager observes its surroundings and chooses one action; the world applies the actions and the
clock advances. Each villager's choice is one traced run, so the existing graph, span and replay
views explain any decision.

All M1–M5 core contracts apply unchanged: every model and tool call is a span on a node of the
run's graph; graphs and `config_version` come from the server; secrets are redacted; servers
bind to 127.0.0.1; tests never call a real model.

## Clarifications

### Session 2026-10-31

- Q: Should the village keep ticking on the server while no browser tab shows it, or only while
  the Village view is open? → A: The server runs the ticks; the village pauses itself about 60
  seconds after the last Village view closes.
- Q: How should the map and villagers look in this slice? → A: Shapes drawn in code: colored
  tiles for grass, paths, water and places, labelled places, round villager figures in their own
  color with an initial, and speech bubbles. No image assets.
- Q: When a villager speaks, can it address one villager by name? → A: Yes, optionally; everyone
  nearby still hears it, marked with who it was for ("Hilde → Jonas: …").
- Q: What should the four villagers be called? → A: Mayor Hilde, Jonas the fisher, Greta the
  farmer, Lina the flower girl (distinct initials H, J, G, L for the map figures).

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Watch the village live (Priority: P1)

The owner opens the Village view, sees the map with its places and the four villagers at home,
and presses Start. Tick by tick the villagers move between places and talk; what they say
appears on the map. Pause stops after the current tick; Step runs exactly one tick.

**Why this priority**: seeing agents act together in one world is the point of the milestone.

**Independent Test**: with the scripted model answering each villager's turn, starting the
village for three ticks moves the villagers as scripted, shows their speech, advances the clock
by three ticks, and stores the world after each tick.

**Acceptance Scenarios**:

1. **Given** a new world, **When** the owner opens the Village view, **Then** the map shows the
   six places, the four villagers at their homes with their names, and the clock at the start
   of day one.
2. **Given** a paused world, **When** the owner presses Step, **Then** each villager takes one
   turn, the actions are applied together, and the clock advances by one tick.
3. **Given** a running world, **When** the owner presses Pause, **Then** the current tick
   finishes and no new tick starts.
4. **Given** a villager says something, optionally to a named villager, **When** the tick is
   applied, **Then** the words appear next to that villager on the map (with the addressee if
   any) and every villager nearby hears them, marked with who they were for, in its next
   observation.
5. **Given** the backend restarts, **When** the owner opens the Village view, **Then** the world
   is exactly as after its last completed tick, paused.

---

### User Story 2 - Four villagers with their own personalities (Priority: P2)

The four villagers behave like themselves: the mayor plans the harvest festival and seeks
people out, the fisher works at the pier and brings fish to market, the farmer works the fields
and worries about the weather, the flower girl tends the garden and carries news. Each
remembers what it recently saw, heard and did.

**Why this priority**: distinct personalities and short memory make the village worth watching
and show how prompts shape behavior.

**Independent Test**: each villager's observation contains its persona, its place, the time of
day, who is nearby, what it heard and its last events; actions outside the allowed set count as
waiting.

**Acceptance Scenarios**:

1. **Given** a villager's turn, **When** its agent is called, **Then** the observation lists its
   name, role and personality, the time of day, its place, the villagers and places nearby,
   what was said nearby since its last turn, and its last 10 events.
2. **Given** a villager answers "move to the market", **When** ticks pass, **Then** it walks one
   cell per tick along the paths until it arrives, and its events record the arrival.
3. **Given** a villager's answer is not a valid action (unreadable, unknown place, empty
   speech, an addressee who is not a villager), **When** the tick is applied, **Then** that
   villager waits, and the reason is shown with its turn.
4. **Given** the mayor's personality, **When** the village runs for a day on the real model,
   **Then** the mayor mentions the festival to at least one other villager (manual check).

---

### User Story 3 - Look inside a villager (Priority: P3)

The owner clicks a villager to see its persona, its current goal and place, its recent events
and its turns; opening a turn shows the usual run view (graph, spans, prompt and answer).
Editing the villager's agent in the builder changes its behavior from the next tick.

**Why this priority**: the lab's purpose is understanding behavior; one click from a villager
to the exact model call behind its action keeps the village a learning tool.

**Independent Test**: a villager's turns are stored as runs linked to the world and tick; the
village's turns stay out of the main past-runs list; an edit of the villager's agent between
two ticks shows up as a new `config_version` on its next turn.

**Acceptance Scenarios**:

1. **Given** the village has run, **When** the owner clicks a villager, **Then** a panel shows
   its name, role, personality, place, last action and last 10 events, and its turns newest
   first.
2. **Given** a villager's turn in that panel, **When** the owner opens it, **Then** the run view
   shows that turn's graph, spans, observation and answer, live while the turn runs.
3. **Given** the owner edits a villager's agent (prompt, model, blocks) and saves, **When** the
   next tick runs, **Then** that villager's turn uses the new config and records the new
   `config_version`; earlier turns keep theirs.
4. **Given** hundreds of village turns, **When** the owner opens the main past-runs list,
   **Then** village turns are not listed there.

### Edge Cases

- A villager's turn fails (model error, timeout) → that villager waits this tick; the error is
  on its turn's span and marked on the map; the other villagers' actions still apply.
- Every turn of a tick fails (e.g. the local model is down) → the tick still advances with
  everyone waiting; after 3 such ticks in a row the village pauses itself and says why.
- Two villagers want the same cell → both may stand there; cells hold any number of villagers.
- A villager is told to move to the place it is already at → it waits.
- A speech is very long → it is cut to 200 characters on the map and in what others hear; the
  full answer stays in the trace.
- The owner deletes a villager's agent → the village shows the villager as unable to act and it
  waits each tick until the owner resets the world.
- The owner resets the world → villagers go home, memory and clock start over; past turns stay
  in the database.
- Ticks take longer than the set interval (slow model) → the next tick starts when the current
  one has finished; ticks never overlap.
- The owner closes the last Village view while the village runs → it keeps running for 60
  seconds, then pauses after the current tick; reopening within the 60 seconds keeps it
  running.

## Requirements *(mandatory)*

### Functional Requirements

**World**

- **FR-001**: The village MUST have one world: a grid map of 20 × 15 cells with six named places
  (town hall, square, market, pier, fields, flower garden), walkable paths between them, water
  that cannot be entered, and a clock that starts at day 1, 06:00 and advances 10 minutes per
  tick; the time of day (morning, midday, afternoon, evening, night) follows from the clock.
- **FR-002**: The world MUST be stored after every completed tick and survive restarts; the
  owner MUST be able to reset it to its starting state.

**Villagers**

- **FR-003**: The village MUST start with four villagers: Mayor Hilde (town hall), Jonas the
  fisher (pier), Greta the farmer (fields) and Lina the flower girl (flower garden), each with a
  personality, a home place and a daily rhythm described in its persona. Their initials (H, J, G, L)
  label their figures on the map.
- **FR-004**: Each villager MUST be played by its own Agent Lab block agent, created the first
  time the village starts and listed with the owner's agents; it uses that agent's model
  setting (M4).
- **FR-005**: Each villager MUST remember its last 10 events (arrived, heard, said, waited and
  why), shown to it in every observation.

**Ticks and actions**

- **FR-006**: On each tick every villager MUST receive an observation (persona, time, place,
  nearby villagers and places, speech heard since its last turn, last events) and answer with
  one action: move to a named place, say a text (optionally to one named villager; everyone
  nearby hears it, marked with the addressee), or wait.
- **FR-007**: The turns of a tick MUST run concurrently; all actions MUST be applied together
  after every turn has finished, then the clock advances. Ticks MUST NOT overlap.
- **FR-008**: An answer that is not a valid action MUST count as waiting, with the reason
  recorded in the villager's events and turn.
- **FR-009**: Moving MUST take one cell per tick along walkable cells, by a shortest path, until
  the villager arrives.
- **FR-010**: The server MUST run the ticks, so reloading or opening a second Village view does
  not disturb them. The owner MUST be able to start, pause, step one tick and set the interval
  between ticks (1–30 seconds, default 5). A running village MUST pause itself after 3 ticks in a
  row in which every turn failed, and 60 seconds after the last open Village view has closed;
  the view says why it paused.

**Tracing**

- **FR-011**: Each villager turn MUST be one traced run of the villager's agent, recording the
  world tick it belongs to; the observation is its prompt and the action its answer.
- **FR-012**: Village turns MUST NOT appear in the main past-runs list; they MUST be listed per
  villager in the Village view and open in the usual run view.
- **FR-013**: An edit of a villager's agent MUST apply from the next tick and be visible as a new
  `config_version` on that villager's turns.

**UI**

- **FR-014**: The Village view MUST show the map with its places, the villagers with their names
  and current speech, the clock, the controls and the tick state (running, paused, ticking); it
  MUST be keyboard operable and readable on a laptop screen. The map is drawn from shapes:
  colored tiles (grass, path, water, place), place labels, one round figure per villager in its
  own color with its initial, and a speech bubble for what it said this tick; no image assets.
- **FR-015**: Clicking a villager MUST open its panel (persona, place, last action, last 10
  events, turns).

**Quality**

- **FR-016**: Tests MUST use the scripted fake model only; they MUST cover observations, each
  action and invalid answers, movement, speech reaching the right villagers, concurrency of
  turns, persistence and reset, the auto-pause, and that village turns stay out of the main
  list.
- **FR-017**: All quality gates MUST pass; every requirement maps to a test or an explicit
  manual check in `tasks.md`.

### Key Entities

- **World**: the map (cells, places, water), the clock (tick number, time), its state (running
  or paused, interval) and the villagers' positions; stored per completed tick.
- **Place**: name, cells it covers.
- **Villager**: name, role, personality, home place, the agent that plays it, position, current
  destination, last 10 events.
- **Event**: tick, kind (arrived, heard, said, waited), text, and for speech the speaker and
  the addressee if any.
- **Turn**: a run of a villager's agent for one tick, with its observation and parsed action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From opening the Village view, the owner sees all four villagers act in the first
  tick within 30 seconds on the local model.
- **SC-002**: 100 consecutive scripted ticks complete with every villager always on a walkable
  cell and never moving more than one cell per tick.
- **SC-003**: 100% of villager turns in the test suite are traced runs whose spans lie on their
  graph and which record their tick.
- **SC-004**: 100% of tested invalid answers (unreadable, unknown place, empty speech, model
  error) make the villager wait with the reason recorded.
- **SC-005**: After a restart the world resumes exactly where its last completed tick left it.
- **SC-006**: On the real model, within the first 36 ticks (six village hours) at least two
  villagers talk to each other, and the mayor mentions the festival (manual check).

## Future Scope (not planned in M6)

- Pixel-art tiles and character sprites, fork-and-compare worlds, per-villager stats,
  inventories and trading, a map editor, adding or removing villagers, world actions as tools
  (with M7 MCP), real memory (M9: store, retrieve, reflect), budgets per tick (M8 Harness).
- Roadmap after M6: **M7 MCP**, **M8 Harness**, **M9 Agent memory**, **M10 RAG**.

## Assumptions

- One world at a time; the four villagers are fixed in this slice (their agents are editable).
- Villagers act only through their one action per tick; nothing they say changes the world
  beyond being heard.
- "Nearby" means in the same place; outside places a villager sees and hears only those within
  3 cells.
- The festival is part of the mayor's persona, not a scripted event.
- The map is fixed (defined with the world), not edited in the UI.
- Tick turns use the local model unless the owner sets another model on a villager's agent; with
  four villagers and the default interval, the local server handles a tick's four concurrent
  turns.
- The 2D map is drawn without a new library (plan decision); no dependency is added.
