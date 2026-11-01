# Feature Specification: M11 — Plans and Purpose

**Feature Branch**: `main` (feature directory `011-plans-and-purpose`)

**Created**: 2026-11-01

**Status**: Draft

**Input**: "What can you learn from this so we can improve and upgrade the village and the
villagers?" — after comparing Agent Lab with Stanford's Generative Agents, a16z AI Town,
DeepMind Concordia, Microsoft TinyTroupe and Altera Project Sid. The owner chose the
recommendation: daily plans, facts kept apart from claims, no repeated lines, and festival
deliveries with a work action. Later the owner added: "more people can work on the field or the
flower shop or go fishing" — work done together adds up.

## Context

The M10 checks on the real model showed four weaknesses:

- Villagers only react to triggers and fall back on fixed routines, so their days drift; the
  festival needed an extra announcement before they went to the square.
- On a sunny day the villagers talked each other into a storm, and the chronicler reported it as
  fact.
- Hilde asked Jonas the same question three times in one conversation.
- Hilde has wanted fish, vegetables and flowers for her festival since M6, but nothing comes of
  it, and tending a field means only standing on it.

Generative Agents plans each agent's day ahead; Concordia separates what an agent claims from
what happens. This milestone brings both ideas to the village in its own way, and gives the
villagers' work a result the festival shows.

All earlier contracts apply: every model call is a traced run of a block agent and the village
never calls the model directly; invalid answers change nothing and record why; tests use the
scripted fake model only; no new dependency; reduced motion is respected; the village still
pauses 60 seconds after the last viewer leaves.

The roadmap moves back by three: M12 Building together (painting houses, planting trees, market
stands, new buildings from a catalogue that take several days, boat trips), M13 Daily happenings
(a different event each day: the postman, a visiting friend, a travelling merchant, …; and
whispers to villagers), M14 MCP, M15 Harness (including daily village health metrics), M16 Agent
memory for the lab's other agents, M17 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who watches the village, reads its chronicle and opens villager
turns to see why they acted.

### User Story 1 - Daily plans (Priority: P1)

When a villager wakes, it writes a short plan for its day: a few entries, each a time, where to
be or whom to see, and why. The plan is part of everything it is told that day, with the entry
for the current time marked. After a long conversation it may revise the plan. The owner sees
each villager's plan in its panel, and the chronicler sees the plans.

**Why this priority**: purposeful days are the biggest change in what the owner sees; plans make
villagers seek each other and come to the festival on their own.

**Independent Test**: with the scripted model, a waking villager's plan run produces a plan that
appears, with the current entry marked, in each of its observations that day; a revision after a
long conversation replaces it; an invalid plan leaves the villager on its routine with the
reason recorded.

**Acceptance Scenarios**:

1. **Given** a villager waking, **When** it wakes, **Then** one plan run starts for it, and a
   valid answer becomes its plan for the day: 2 to 6 entries, each with a time, a place or a
   villager, and a purpose.
2. **Given** a villager with a plan, **When** it decides, **Then** its observation lists the
   plan and marks the entry whose time has come and the next one.
3. **Given** a villager that just finished a conversation of at least 4 lines, **When** the
   conversation ends, **Then** it revises its plan, at most twice a day; the revision sees what
   was said.
4. **Given** an invalid plan answer, **When** the run finishes, **Then** the villager keeps its
   previous plan (or none) and its routine, and the reason is recorded on the run.
5. **Given** the villager panel, **When** the owner opens a villager, **Then** they see its plan
   for today with the current entry marked; the plan runs are listed among its turns.

---

### User Story 2 - Facts apart from claims (Priority: P1)

What a villager knows for sure (the date, the weather, what it sees, where it is) is told apart
from what others said, which is marked as claims. The villagers' rules say to trust what they see
over what they hear. The chronicler is told that what villagers say are claims, and that only
the facts it is given are events.

**Why this priority**: a village that invents storms and reports them as history breaks the
owner's trust in the chronicle; it is cheap to fix.

**Independent Test**: the observation has a facts part and a claims part; the villagers' rules
contain the new sentence, and stored agents holding the M9 rules text get it; the chronicle
prompt marks speech as claims.

**Acceptance Scenarios**:

1. **Given** a villager deciding, **When** its observation is built, **Then** it opens with what
   it knows for sure (date, time, weather, where it is, who is next to it and in sight, how the
   places it knows are doing) and lists heard lines and heard whereabouts under what others said.
2. **Given** the villagers' agents, **When** the village loads, **Then** every villager agent
   whose prompt still holds the previous rules text gets the new rules, including "Trust what you
   see over what you hear; the weather you are told is the real weather."
3. **Given** a day record, **When** the chronicle prompt is built, **Then** conversation lines are
   marked as said by a villager, and the chronicler is told never to report a claim as an event.

---

### User Story 3 - No repeated lines (Priority: P2)

A villager is shown what it said lately, and a line that repeats one of its own last three lines
is refused: it waits with the reason "you already said that".

**Why this priority**: repetition makes conversations tedious to read; a small, testable rule.

**Independent Test**: with the scripted model, a say that repeats one of the villager's last three
lines (ignoring case, spaces and punctuation) becomes a wait with that reason; the observation
lists its last lines.

**Acceptance Scenarios**:

1. **Given** a villager that said "Where are the fish?", **When** it answers say "where are the
   fish", **Then** it waits with the reason "you already said that" and nobody hears it.
2. **Given** a villager deciding, **When** its observation is built, **Then** it lists the
   villager's last three lines under "What you said lately".
3. **Given** a goodbye whose text repeats an earlier line, **When** it is applied, **Then** the
   goodbye still ends the conversation, without the repeated text.

---

### User Story 4 - Work and festival deliveries (Priority: P2)

Villagers work on purpose. A villager at the fields or the flower garden can work there (it
tends them; only working counts now, standing does not). Jonas fishing at the pier catches fish,
Greta takes vegetables from ripe or harvested fields, and Lina picks flowers from a blooming
garden; each carries one basket at a time. Villagers can work together: anyone can work the
fields or the garden alongside others, or fish with Jonas while he works at the pier, and the
work of everyone there adds up, so a place is tended and baskets come sooner. A villager can give its basket to someone next to it,
or set it out on the festival stalls while standing on the square. The square shows what has
been delivered, the villagers are told what the festival still lacks, and the festival and the
chronicle show what made it.

**Why this priority**: it gives a summer of work and Hilde's plan a visible result; it needs the
calendar and growth from M10.

**Independent Test**: with the scripted model, working at each place for a village hour produces
the right basket (or none when the place has nothing to give), give moves it to the villager next
to the giver or onto the stalls, and the festival supplies are listed and drawn; tending counts
only steps spent working.

**Acceptance Scenarios**:

1. **Given** a villager at the fields or the flower garden, **When** it answers work, **Then** it
   works there until it decides something else, and only steps spent working count as tending.
2. **Given** Jonas working at the pier for a village hour, **When** the hour passes, **Then** he
   carries a basket of fish; Greta working at ripe or harvested fields gets vegetables, Lina
   working at a blooming garden gets flowers; nothing comes from a place with nothing to give.
3. **Given** a villager carrying a basket next to another with empty hands, **When** it answers
   give to that villager, **Then** the basket moves to them and both are told.
4. **Given** a villager carrying a basket on the square, **When** it answers give without anyone,
   **Then** the goods go onto the festival stalls, which show them on the map.
5. **Given** autumn, **When** a villager decides, **Then** it is told what the festival stalls
   hold and still lack (fish, vegetables, flowers); on the festival evening the stalls are full
   or show the gaps, and the chronicle and the festival memories name what was there.
6. **Given** an invalid work or give (wrong place, empty hands, full hands, nobody there, the
   other asleep), **When** it is applied, **Then** the villager waits with the reason.
7. **Given** Greta and Lina both working at the fields, **When** half a village hour passes,
   **Then** their work adds up to a village hour: the fields count as tended that day and one
   basket goes to whichever of them has empty hands.
8. **Given** Jonas working at the pier, **When** another villager there answers work, **Then** it
   fishes with him and its work adds to his; without Jonas working there, work at the pier is
   refused with the reason.

### Edge Cases

- A villager wakes while a plan run from yesterday is still in flight → the old result is
  dropped; one plan per villager per day.
- A plan names a place or villager that does not exist → that entry is dropped; a plan left with
  fewer than 2 entries is invalid.
- A plan entry's time is before the villager wakes or after it goes to bed → kept, marked as past
  or later; the village never forces it.
- A villager revises its plan twice and talks long again → no third revision that day.
- A repeated line inside a goodbye → the goodbye happens without the text.
- Work while talking → allowed: villagers talk while they work (working together depends on
  it); saying something does not stop the work, only walking off does.
- A villager carrying a basket goes to bed → it keeps the basket overnight.
- Goods set out on the stalls before autumn → they stay until the festival is over, then the
  stalls are cleared for the next year.
- Fish, vegetables and flowers can also be given to anyone (e.g. traded at the market); only the
  stalls on the square count for the festival.
- Several villagers work on one place and more than one has empty hands → the basket goes to the
  one who worked there longest since its last basket; nobody with empty hands → the work is kept
  and the basket comes once someone there has empty hands.
- Jonas stops working at the pier while others fish with him → they keep fishing until they
  decide something else; only starting needs Jonas there.
- Reset → no plans, empty hands, empty stalls.
- A village saved by M10 → loads with no plans, empty hands and empty stalls.

## Requirements *(mandatory)*

### Functional Requirements

**Plans**

- **FR-001**: When a villager wakes, the village MUST run a shared "Village planner" block agent
  for it as an ordinary traced run tagged with the villager, given its persona, sleeping hours,
  routine, learnings, views, recent memories, today's date, weather and festival news, and the
  state of the places; a valid answer becomes its plan for the day: 2 to 6 entries of a time,
  a place or a villager, and a purpose of at most 120 characters.
- **FR-002**: Each observation of a villager with a plan MUST list the plan and mark the current
  and the next entry.
- **FR-003**: A villager MUST revise its plan after a conversation of at least 4 lines ends, at
  most twice a day, with the conversation in the prompt; plan runs never count as decisions or
  toward the failure pause, and Step and Reset wait for them.
- **FR-004**: The villager panel MUST show today's plan with the current entry marked; plan runs
  appear among the villager's turns.

**Facts and claims**

- **FR-005**: The observation MUST put what the villager knows for sure before what others said,
  and mark heard lines and heard whereabouts as claims.
- **FR-006**: The villagers' rules MUST say to trust what they see over what they hear and that
  the weather they are told is the real weather; stored agents still holding the previous rules
  text get the new text on load, others are left alone.
- **FR-007**: The chronicle prompt MUST mark conversation lines as claims and tell the chronicler
  never to report a claim as an event.

**Repetition**

- **FR-008**: A say whose text repeats one of the villager's own last three lines (ignoring case,
  spaces and punctuation) MUST become a wait with the reason "you already said that"; a goodbye
  with such text keeps the goodbye without the text.
- **FR-009**: The observation MUST list the villager's last three lines.

**Work and deliveries**

- **FR-010**: A new action work MUST be valid at the fields and the flower garden for anyone, and
  at the pier for Jonas or for anyone while Jonas works there; the villager keeps working until it
  decides something else or leaves; tending counts only working steps, and the working steps of
  everyone on a place add up (two villagers working half an hour tend it like one working an
  hour).
- **FR-011**: Every village hour of work added up at a place MUST give a basket to a villager
  working there with empty hands (the one who worked there longest since its last basket): fish at
  the pier, vegetables at ripe or harvested fields, flowers at a blooming garden; nothing
  otherwise; at most one basket per villager.
- **FR-012**: A new action give MUST move the giver's basket to a named awake villager next to it
  with empty hands, or, without a name while on the square, onto the festival stalls; both sides
  are told and it is noted in the day record.
- **FR-013**: In autumn, villagers MUST be told what the stalls hold and lack; the map MUST show
  carried baskets and the goods on the stalls; the festival evening's memories and the chronicle
  MUST name the goods that were there; the stalls are cleared when winter starts.
- **FR-014**: The villagers' rules MUST describe work and give; invalid work or give (wrong place,
  empty or full hands, nobody there, the other asleep) MUST become a wait with the reason.

**State and quality**

- **FR-015**: A village saved by M10 MUST keep going with no plans, empty hands and empty stalls;
  Reset clears plans, baskets and stalls and keeps the planner agent.
- **FR-016**: Tests MUST use the scripted fake model only and cover: plan on waking, valid and
  invalid plans, the marked entries, revisions and their limit, the facts and claims parts, the
  rules refresh, the chronicle's claim marking, repeated lines refused, work and tending, shared work
  adding up (tending and baskets), fishing with Jonas, baskets from each place and none from empty
  ones, give to a villager and to the stalls, every invalid
  work and give, the stalls in observations, the festival with and without goods, loading an M10
  village.
- **FR-017**: All quality gates MUST pass; every requirement maps to a test or a manual check in
  `tasks.md`.

### Key Entities

- **Plan**: per villager per day — entries (time, place or villager, purpose), revisions used.
- **Basket**: per villager — fish, vegetables, flowers or empty.
- **Festival stalls**: per year — the goods set out (fish, vegetables, flowers).
- **Working**: per villager — the place it works at until it does something else, and the steps
  worked there since its last basket.
- **Work done**: per place per day — the working steps of everyone there, added up, for tending
  and baskets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In scripted days, every villager with a valid plan answer has a plan from waking
  until bed, every one of its observations that day lists it, and no plan is revised more than
  twice a day.
- **SC-002**: In scripted conversations, 100% of says repeating one of the speaker's last three
  lines are refused and never heard.
- **SC-003**: In a scripted autumn where Jonas, Greta and Lina work their places and set their
  baskets out on the square, the festival stalls hold all three goods by the festival; with no
  deliveries they hold none; standing without working never tends a place; two villagers working
  together tend a place and fill a basket in half the time one needs.
- **SC-004**: On the real model over two village days at Fast pace, at least three of the four
  villagers are at their plan's first place or with its villager within an hour of its time on
  at least one day, and no chronicle entry reports a weather other than the day's (manual check).
- **SC-005**: On the real model, starting at autumn day 1 with ripe fields and a blooming garden,
  at least two of the three goods are on the stalls by the festival evening (manual check).
- **SC-006**: In the real-model runs, repeated lines refused are counted and reported; no
  villager's heard lines contain the same line twice within any three of its own lines in a row
  (manual check).

## Assumptions

- Plans use a shared "Village planner" agent like the reflections, not each villager's own
  agent, so the villagers' decision prompts stay as they are; it costs one run per villager per
  day plus at most two revisions.
- A plan entry is a time and either a place or a villager; the village never moves anyone to
  follow it.
- Repetition is checked against the speaker's own last three lines only, whoever they were said
  to.
- One basket per villager, one kind of goods; goods do not spoil; there is no money or price.
- Hilde has no goods of her own; she can carry what others give her and set it out.
- Tending by working replaces tending by standing from M10; the growth rules stay the same.
