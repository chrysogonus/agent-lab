# Feature Specification: M8 — Villager Memory

**Feature Branch**: `main` (feature directory `008-village-memory`)

**Created**: 2026-11-01

**Status**: Draft

**Input**: "Do memory now for the villagers. I want them to have some learnings over time and
maybe change their interactions based on that."

## Context

Since M7 the four villagers (Mayor Hilde, Jonas the fisher, Greta the farmer, Lina the flower
girl) live a day-night rhythm, meet face to face, talk, look for each other and keep a belief
about where the others are. What they remember is only their last 10 events: by the
afternoon Hilde has forgotten that Lina promised her sunflowers in the morning, and nobody
carries anything from one day into the next. The owner wants villagers that learn over time
and act differently because of what they learned.

This milestone gives each villager three kinds of memory, in the shape the lab's roadmap gave
agent memory (store, retrieve, reflect):

- **Memories**: lasting records of what happened to it (conversations, searches, meetings),
  kept across days.
- **Recall**: when a villager decides, the memories that matter most right now (who is next to
  it, who it is looking for, where it is, what is recent and important) are shown to it.
- **Reflection**: when a villager goes to sleep, it looks back on its day and writes down a few
  learnings ("Jonas trades fish only around midday") and its current view of each other
  villager ("Lina: cheerful, reliable, promised sunflowers"). Learnings and views are part of
  every decision from then on, so they shape how it behaves the next day.

All M6 and M7 contracts apply: every model call is a traced run of an agent, the village never
calls the model directly, invalid answers change nothing and record why, tests use the scripted
fake model only.

The milestone moves the remaining roadmap back by one: M9 MCP, M10 Harness, M11 Agent memory for
the lab's other agents, M12 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Villagers remember what happened (Priority: P1)

Each conversation, search and meeting leaves a lasting memory with the villager. When a
villager decides, it is reminded of the memories that matter now: when Hilde meets Lina in the
afternoon, she is reminded of their talk in the morning.

**Why this priority**: without lasting memory nothing can be learned; recall alone already
makes conversations more coherent.

**Independent Test**: with the scripted model, a conversation in the morning becomes a memory
of both villagers, and when they meet again hours later (long after it left their last 10
events), the memory is in both observations.

**Acceptance Scenarios**:

1. **Given** two villagers end a conversation, **When** it ends, **Then** each keeps one memory
   of it: the time, who it was with and what was said.
2. **Given** a villager found or missed someone, **When** that happens, **Then** it keeps a
   memory of it.
3. **Given** a villager is about to decide, **When** its observation is built, **Then** it
   shows up to 5 remembered things, preferring those about the villagers next to it, the
   villager it is looking for and the place it is at, then the important and recent ones.
4. **Given** many days pass, **When** memories pile up, **Then** each villager keeps at most 60,
   dropping the least important old ones first.

---

### User Story 2 - Learning at the end of the day (Priority: P2)

When a villager goes to bed, it reflects on the day: it writes up to 3 new learnings and
updates its view of each villager it dealt with. The next morning those learnings and views
are part of every decision, and its behavior changes with them, for example the mayor goes to
the market at midday because she learned Jonas is there then.

**Why this priority**: this is the "learnings over time" the owner asked for; it needs the
memories of US1.

**Independent Test**: with the scripted model, a villager that had a conversation reflects when
it falls asleep; the scripted learnings and views appear in its observations the next day; a
villager with an uneventful day does not reflect.

**Acceptance Scenarios**:

1. **Given** a villager had at least one memory today, **When** it falls asleep, **Then** one
   reflection runs (traced like any decision) with its persona, today's memories, its learnings
   so far and its current views.
2. **Given** a valid reflection answer, **When** it is applied, **Then** the new learnings are
   kept (at most 12 per villager, the oldest dropped first), the views of the named villagers
   are replaced, and the reflection is itself kept as an important memory.
3. **Given** an invalid reflection answer (not JSON, wrong shape, unknown villager), **When** it
   is applied, **Then** nothing changes except a recorded reason, as with decisions.
4. **Given** learnings and views exist, **When** the villager decides the next day, **Then** its
   observation lists its learnings and, next to where it thinks each villager is, what it
   thinks of them.

---

### User Story 3 - Seeing what a villager has learned (Priority: P3)

In a villager's panel the owner sees what it has learned (with the day it learned it), what it
thinks of each other villager, its lasting memories, and its reflections among its turns, each
opening in the usual run view.

**Why this priority**: the lab is about understanding behavior; the owner must be able to see
why a villager acts differently than yesterday.

**Independent Test**: the state exposes learnings, views and memories per villager; reflection
runs are listed with the villager's turns and labelled as reflections.

**Acceptance Scenarios**:

1. **Given** a villager has reflected, **When** the owner opens its panel, **Then** it shows
   "Has learned" with each learning and its day, and its views next to its beliefs.
2. **Given** a reflection ran, **When** the owner looks at the villager's turns, **Then** the
   reflection is listed ("reflects on day 1") and opens in the run view.
3. **Given** the owner edits the reflection agent's prompt, **When** the next reflection runs,
   **Then** it uses the edited prompt.

### Edge Cases

- A villager falls asleep while its reflection from the day before has not finished → the new
  one waits; reflections of one villager never overlap.
- The village is paused while a reflection runs → it finishes and applies; Pause does not cancel
  it.
- Reset → memories, learnings and views are cleared with the rest of the world; past runs stay.
- A stored M7 world → it keeps going; villagers start with no memories, learnings or views.
- A reflection names a villager that does not exist or itself → the whole answer is invalid.
- A learning or view is very long → it is cut to 200 characters.
- The reflection agent was deleted → reflections fail with a reason until the owner resets
  (as with villager agents).
- Every decision fails but reflections succeed (or the other way round) → only decisions count
  for the failure self-pause.

## Requirements *(mandatory)*

### Functional Requirements

**Memories**

- **FR-001**: Each villager MUST keep lasting memories, each with its time, kind (conversation,
  found, missed, met, reflection), the villagers and place it is about, a short text and an
  importance from 1 to 5. Conversations MUST be remembered by both villagers when they end,
  with what was said (cut to 400 characters); found and missed when they happen; a first
  meeting of the day with someone as a low-importance memory.
- **FR-002**: Memories MUST be kept across days and survive restarts; at most 60 per villager,
  dropping the lowest-scored old memory when full (reflections are never dropped before other
  kinds of the same age).

**Recall**

- **FR-003**: Each decision's observation MUST include up to 5 memories chosen by a score of
  relevance (mentions the villagers next to it, the one it looks for or talks with, or its
  current place), importance and recency, newest last, each with its day and time.

**Reflection**

- **FR-004**: When a villager falls asleep after a day with at least one memory, the village
  MUST run one reflection: a traced run of the village's reflection agent (a block agent created
  with the villagers' agents, listed with the owner's agents and editable) with the villager's
  name, persona, today's memories, its learnings and its views as the prompt, tagged with the
  villager and the step.
- **FR-005**: The reflection's answer MUST be one JSON object
  `{"learnings": [up to 3 texts], "views": {villager: text}}`; valid answers add the learnings
  (at most 12 kept per villager), replace the named views and add the reflection as a memory of
  importance 5; anything else changes nothing and records the reason with the run.
- **FR-006**: Each decision's observation MUST list the villager's learnings and, for each other
  villager, its current view next to the belief about where they are.
- **FR-007**: Reflections MUST NOT block steps or decisions, MUST NOT overlap for one villager,
  and MUST NOT count towards the failure self-pause.

**Persistence and controls**

- **FR-008**: Memories, learnings and views MUST be stored with the world; Reset MUST clear them;
  a stored M7 world MUST load with empty memories, learnings and views instead of starting fresh.

**UI**

- **FR-009**: A villager's panel MUST show "Has learned" (learnings with their day), its views
  of the others next to its beliefs, and its lasting memories (newest first, at most 10 shown
  with a way to see all), and its turns list MUST label reflections.

**Quality**

- **FR-010**: Tests MUST use the scripted fake model only and cover: memories from conversations,
  finds, misses and meetings; the memory limit; recall ranking; reflection on falling asleep (and
  none after an uneventful day); valid and invalid reflection answers; learnings and views in the
  next day's observation; no overlapping reflections; reflections excluded from the failure
  self-pause; persistence, reset and loading an M7 world.
- **FR-011**: All quality gates MUST pass; every requirement maps to a test or an explicit manual
  check in `tasks.md`.

### Key Entities

- **Memory**: villager, time (step), kind, about (villagers), place, text, importance.
- **Learning**: villager, the day it was learned, text.
- **View**: villager, about whom, text, the day it was formed.
- **Reflection**: a run of the reflection agent for one villager and one day, with its prompt and
  parsed answer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a scripted day, 100% of ended conversations, finds and misses become memories
  of the villagers involved.
- **SC-002**: A memory of a conversation from the morning is shown to both villagers when they
  meet again that afternoon (scripted).
- **SC-003**: Every villager with a memory that day reflects exactly once when it falls asleep;
  villagers without one do not (scripted).
- **SC-004**: Learnings and views from a reflection appear in 100% of the villager's
  observations the next day (scripted).
- **SC-005**: Over 10 scripted days, no villager holds more than 60 memories or 12 learnings,
  and the world stays loadable after each step.
- **SC-006**: On the real model, after two village days at least one villager states a learning
  about another villager, and at least one decision on day 2 visibly follows a learning or view
  from day 1 (manual check).

## Assumptions

- Recall uses words, not meaning: a memory is relevant when it names a villager or place that
  matters now; no embedding model or new dependency is needed.
- Reflection happens once per villager per night, at falling asleep; there is no reflection
  during the day.
- One shared reflection agent serves all four villagers (the prompt carries the persona), so
  "My agents" gains one entry, not four.
- Importance is fixed per kind (conversation 3, found 2, missed 2, met 1, reflection 5), not
  rated by the model.
- Personas are not rewritten by reflection; learnings and views are added next to them.
- The last-10-events list stays as M7 (short-term), alongside lasting memories.
