# Feature Specification: M10 — Village Seasons

**Feature Branch**: `main` (feature directory `010-village-seasons`)

**Created**: 2026-11-01

**Status**: Draft

**Input**: "How can I bring more life into the village? I want to just let the village run and look
at it, then come back at some time and things are happening. Maybe we can introduce something
like dynamic changes around the village, maybe weather or growing of flowers or fields or trees
change color due to seasons." Follow-ups: the village keeps running while its tab is open; three
paces (slow, normal, fast); pace and model stay separate.

## Context

After M9 the villagers walk, talk, remember and learn, but the village itself never changes: every
day has the same light, the same green trees and the same fields, and whatever happened while the
owner looked away is gone except for the last few log lines. The owner wants to leave the village
tab open, come back later, and find that time has passed visibly and that they can catch up on
what happened.

All earlier contracts apply: every model call is a traced run of a block agent and the village
never calls the model directly; invalid answers change nothing and record why; tests use the
scripted fake model only; no new dependency; reduced-motion preferences are respected; the village
still pauses 60 seconds after the last viewer leaves.

The remaining roadmap moves back by one: M11 MCP, M12 Harness, M13 Agent memory for the lab's
other agents, M14 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who keeps the village open in a browser tab, glances at it now and
then and comes back after a while.

### User Story 1 - Three paces (Priority: P1)

The owner picks how fast the village runs from three paces instead of typing seconds: Slow for
leaving it on in the background, Normal as today, Fast to watch a day go by.

**Why this priority**: it decides how much happens while the owner looks away, and every later
story is felt through it; it is also the smallest change.

**Independent Test**: choosing each pace sets the length of a village step to 15, 5 or 2 seconds;
the villagers' models are the same before and after.

**Acceptance Scenarios**:

1. **Given** the village view, **When** the owner looks at the controls, **Then** they see Slow,
   Normal and Fast with the current pace marked, and no seconds field.
2. **Given** Normal, **When** the owner picks Slow, **Then** each 10-minute step takes 15 seconds,
   so a village day takes about 36 minutes; Normal takes 5 seconds (12 minutes a day) and Fast 2
   seconds (about 5 minutes a day).
3. **Given** a villager agent set to a particular model, **When** the owner changes the pace,
   **Then** the villager's next decision uses the same model as before.

---

### User Story 2 - The village chronicle (Priority: P1)

Each night, once everyone is asleep, a chronicler writes a short diary entry about the day: who
met whom, what was said and promised, what the weather did, how the fields and flowers are doing.
The owner reads the chronicle, newest first, to catch up on what happened while not looking.

**Why this priority**: without it, coming back after an hour shows only the present; the
chronicle is what turns "things happened" into something the owner can see.

**Independent Test**: with the scripted model, the chronicler runs once per village night as a
traced run; a valid answer becomes a chronicle entry for that day; the view lists entries newest
first and marks those written since the owner last opened the chronicle.

**Acceptance Scenarios**:

1. **Given** a village day in which villagers met and talked, **When** the last villager falls
   asleep, **Then** the chronicler runs once and its entry for that day appears in the chronicle
   with the day, season and weather.
2. **Given** the last day of autumn and Hilde still walking home after midnight, **When** she
   falls asleep on the first day of winter, **Then** the entry is for the last day of autumn, with
   that day's weather, and includes what happened after midnight until she fell asleep.
3. **Given** an invalid or empty chronicler answer, **When** the run finishes, **Then** no entry
   is added for that day and the reason is recorded on the run; the village keeps running.
4. **Given** three entries written since the owner last opened the chronicle, **When** the owner
   returns to the view, **Then** the chronicle shows that three entries are new.
5. **Given** the chronicle runs, **When** the owner opens it in the run list, **Then** each
   chronicle run is listed like the reflections, with its spans.

---

### User Story 3 - Seasons and weather (Priority: P2)

The village lives through a year of four 7-day seasons. Trees blossom in spring, are full green in
summer, turn gold and red in autumn and stand bare in winter; snow lies after snowfall. Days are
longer in summer and shorter in winter. Every day has one weather — sun, clouds, rain, storm, fog
or snow, fitting the season — that shows on the map. Villagers are told the date, season and
weather and may react to it.

**Why this priority**: it is the most visible change when the owner comes back, and growth and the
festival build on the calendar and the weather.

**Independent Test**: the calendar follows from the village day; the weather of a day is the same
every time that day is reached; the observation names date, season and weather; screenshots show
each season and each weather.

**Acceptance Scenarios**:

1. **Given** day 1, **When** the village starts, **Then** it is day 1 of spring; day 8 is day 1 of
   summer, day 15 autumn, day 22 winter, and day 29 spring again in year 2.
2. **Given** a day of the year, **When** the village reaches it, **Then** its weather is one the
   season allows (no snow in summer), and reaching the same day again after a reset gives the same
   weather.
3. **Given** a rainy day, **When** the map shows, **Then** rain falls, the light is grey and
   puddles lie on the paths; storms add lightning flashes, fog veils the map, snow falls and covers
   the ground.
4. **Given** autumn, **When** the map shows, **Then** trees are gold and red; in winter they are
   bare and lamps light earlier in the evening.
5. **Given** a villager deciding, **When** its observation is built, **Then** it says the date,
   season and today's weather, e.g. "Day 3 of autumn, year 1. Rain all day."
6. **Given** reduced motion, **When** it rains or snows, **Then** the weather shows without
   movement.

---

### User Story 4 - Fields and flowers that grow from work (Priority: P2)

The fields grow through the year only while Greta tends them, and rain helps; the flower garden
blooms while Lina waters it or rain falls and wilts when it is left dry. Both rest in winter. The
stages show on the map, so a tended field and a neglected one look different, and the villagers
know how their places are doing.

**Why this priority**: it makes the villagers' work leave lasting marks on the map, the strongest
sign that time passed while the owner was away.

**Independent Test**: with the scripted model, a year in which Greta spends every day at the fields
brings them to ripe and harvested in autumn; a year in which nobody goes leaves them resting. A
garden nobody visits wilts after 2 dry days and recovers on a rainy day; a garden another villager
visits for an hour on dry days keeps blooming.

**Acceptance Scenarios**:

1. **Given** spring and resting fields, **When** Greta spends at least one village hour awake at
   the fields on a day, **Then** at the end of that day the fields count as tended and move toward
   the next stage (tilled, sown, sprouting, growing, ripe); a tended rainy day counts double.
2. **Given** fields that are sprouting or growing, **When** nobody tends them for 2 days in a row,
   **Then** weeds show on the map and Greta is told the fields are neglected; a tended day clears
   them.
3. **Given** ripe fields in autumn, **When** Greta tends them, **Then** they are harvested; ripe
   fields not harvested by the first day of winter are lost and rest.
4. **Given** the flower garden from spring to autumn, **When** Lina spends at least one village hour
   awake there or it rains, **Then** that day counts as watered; 2 watered days bring buds to
   bloom; 2 dry days in a row make blooms wilt; a watered day revives them.
5. **Given** a villager at a place or with it in sight, **When** its observation is built, **Then**
   it says the place's state ("The fields are sprouting; nobody tended them yesterday."); Greta and
   Lina are always told the state of their own place.
6. **Given** winter, **When** the first day of winter comes, **Then** fields and garden rest and
   tending does nothing until spring.

---

### User Story 5 - The harvest festival (Priority: P3)

On the last day of autumn the village holds Hilde's harvest festival. The square is decorated,
villagers are told the festival is coming in the days before and that it is today on the day, and
in the evening the square is where everyone is expected. Those who are there remember it.

**Why this priority**: it gives Hilde's long-running plan a payoff and the year a high point, but
needs the calendar first.

**Independent Test**: with the scripted model, the festival falls on day 7 of autumn of every year;
that day the square is decorated, the observation announces it and names the square as everyone's
usual place in the evening; villagers on the square that evening get a festival memory.

**Acceptance Scenarios**:

1. **Given** autumn, **When** a villager decides on days 1 to 6, **Then** it is told the harvest
   festival is in N days on the square.
2. **Given** day 7 of autumn, **When** the map shows, **Then** the square has bunting and lanterns
   all day, lit in the evening.
3. **Given** the festival evening (18:00 until each villager's bedtime), **When** a villager
   decides, **Then** it is told the festival is on now and the square is where the village expects
   it.
4. **Given** a villager awake on the square during the festival evening, **When** the evening ends,
   **Then** it has an important memory of the festival, naming who else was there.

### Edge Cases

- The village pauses (no viewer, owner pause) in the middle of a day → time stands still; the
  day's tending, the chronicle and the weather continue when it resumes, so nothing is skipped or
  doubled.
- Step pressed at the moment everyone falls asleep → Step waits for the chronicler, as it waits for
  reflections.
- The chronicler fails (model unreachable, invalid answer) → no entry for that day, the reason is
  on the run, and the failure does not count toward pausing the village.
- A day where little happened → the chronicle still writes an entry from the weather, the places
  and the villagers' movements.
- The chronicle grows over many days → the most recent 28 entries (one village year) are kept.
- Reset → back to day 1 of spring with resting fields, budding flowers and an empty chronicle.
- A village saved by M9 → it keeps going: its current day maps to a season and the places start
  in the stage that season would normally reach.
- A stored step length matching no pace (for example 7 seconds) → no pace is marked until the
  owner picks one; the village keeps that step length until then.
- Storm on the festival day → the festival day's weather is drawn from sun and clouds only.
- A villager tends its place while it is dark or asleep → only awake time counts.
- A villager other than Greta or Lina spends time at the fields or garden → it counts as tending
  too (neighbours help).
- Many weather particles on a slow machine → rain and snow use a few dozen drops or flakes at most.

## Requirements *(mandatory)*

### Functional Requirements

**Pace**

- **FR-001**: The view MUST offer three paces — Slow (15 seconds per 10-minute step), Normal
  (5 seconds) and Fast (2 seconds) — instead of a seconds field, and mark the current one.
- **FR-002**: Changing the pace MUST NOT change which model any villager, the reflection agent or
  the chronicler uses.

**Chronicle**

- **FR-003**: The village MUST keep a record of each day's happenings (meetings, conversations
  with their lines, searches found or missed, goodbyes, weather, place changes) for the chronicle,
  independent of the short visible log.
- **FR-004**: Once per village day, when the last villager falls asleep, the village MUST run a
  shared "Village chronicler" block agent as an ordinary traced run with the day's record; a valid
  answer becomes that day's chronicle entry (a short title and a diary text). The day an entry is
  for is the calendar day on which the villagers' day began (the first one woke), with that day's
  season and weather, even if the last villager falls asleep after midnight; the record runs from
  that first waking until the last villager is asleep. An invalid answer
  adds nothing and records the reason on the run.
- **FR-005**: Chronicle runs MUST behave like reflections: they never count as villager decisions
  or toward the failure pause, Step and Reset wait for them, and they are tagged with the village
  step.
- **FR-006**: The view MUST show the chronicle newest first, each entry with its day, season and
  weather, and mark entries written since the owner last opened the chronicle in this browser.

**Calendar and weather**

- **FR-007**: The village MUST have a calendar of four seasons (spring, summer, autumn, winter) of
  7 days each, starting on day 1 of spring, derived from the village day.
- **FR-008**: Each day MUST have exactly one weather (sun, clouds, rain, storm, fog or snow), drawn
  from the kinds its season allows and the same each time that day is reached.
- **FR-009**: The map MUST show the season (tree colours, blossom, bare trees, snow cover after
  snowfall) and the weather (rain and puddles, storm flashes, fog, falling snow, grey light), and
  the light MUST follow the season's sunrise and sunset, with lamps and windows lit when dark.
- **FR-010**: Each villager's observation MUST state the date, season and weather.

**Growth**

- **FR-011**: The fields MUST go through resting, tilled, sown, sprouting, growing, ripe and
  harvested; they advance only on days they are tended (awake villagers there for at least one
  village hour in total), with rain or storm doubling a tended day's progress; ripe fields are
  harvested on the next tended autumn day; unharvested ripe fields are lost when winter starts.
- **FR-012**: The flower garden MUST go through resting, budding, blooming and wilting; a day is
  watered if awake villagers are there for at least one village hour in total or it rains or
  storms; 2 watered days bring budding to blooming, 2 dry days in a row bring blooming to wilting,
  a watered day brings wilting back to blooming.
- **FR-013**: Fields that are sprouting, growing or ripe and untended for 2 days in a row MUST be
  marked neglected until the next tended day.
- **FR-014**: Each place's stage and neglect MUST show on the map, and a villager at the place,
  with it in sight, or working there MUST be told its state.
- **FR-015**: On the first day of winter both places MUST rest; spring starts the fields at resting
  and the garden at budding.

**Festival**

- **FR-016**: Day 7 of autumn MUST be the harvest festival: the square is decorated all day and lit
  in the evening; on autumn days 1–6 villagers are told how many days remain; on the festival day
  they are told it is today, and from 18:00 the square is every awake villager's usual place.
- **FR-017**: Villagers awake on the square during the festival evening MUST receive an important
  festival memory naming who else was there.

**State and quality**

- **FR-018**: A village saved by M9 MUST keep going with its day mapped onto the calendar and its
  places set to the stage their season normally reaches; Reset MUST start at day 1 of spring.
- **FR-019**: Every new animation MUST stop under reduced motion; decorations and weather MUST NOT
  block clicks on villagers.
- **FR-020**: Tests MUST use the scripted fake model only and cover: the paces, the calendar, the
  weather's reproducibility and season rules, growth with and without tending and with rain,
  neglect, harvest and loss, the garden's watering and wilting, the observation lines, the
  chronicle (valid, invalid, once per night, not a failure), the festival announcements, usual
  place and memory, and loading an M9 village.
- **FR-021**: All quality gates MUST pass; every requirement maps to a test or a manual check in
  `tasks.md`.

### Key Entities

- **Pace**: Slow, Normal or Fast; a step length of 15, 5 or 2 seconds.
- **Calendar date** (derived): year, season, day of season (1–7), festival or not.
- **Weather**: one kind per village day.
- **Place growth**: for the fields and the flower garden — stage, progress toward the next stage,
  days since last tended or watered, neglected or not.
- **Day record**: the happenings from the first villager waking until the last one is asleep,
  with that day's date and weather, kept until the chronicle is written.
- **Chronicle entry**: day, season, weather, title, text, the run that wrote it.
- **Festival memory**: a villager memory of the festival evening and who was there.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At each pace, a scripted village advances one 10-minute step every 15, 5 or 2
  seconds (within 10%), and the villagers' models are unchanged.
- **SC-002**: Over a scripted 28-day year, every day has exactly one allowed weather, all four
  seasons occur in order, the festival occurs exactly once, and a second run of the same year
  produces the same weather on every day.
- **SC-003**: In a scripted year where the fields are tended every day they are harvested before
  the festival; where they are never tended they never get past resting; a garden left dry for 2
  days wilts and recovers after one watered day.
- **SC-004**: Over 7 scripted days, exactly one chronicle run happens per night, every valid
  answer becomes exactly one entry, and invalid answers add none.
- **SC-005**: Screenshots of each season and each weather kind, the festival square and each
  growth stage show the described looks (manual check).
- **SC-006**: On the real model at Fast pace over two village days, every chronicle entry mentions
  at least one event that happened that day, and at least one villager refers to the weather or
  season in speech or reasoning (manual check).
- **SC-007**: On the real model, starting from the day before the festival, at least three of the
  four villagers are on the square during the festival evening (manual check).

## Assumptions

- Seasons of 7 days make a year of 28 village days: about 5½ hours at Normal pace, 2¼ hours at
  Fast and 17 hours at Slow.
- Weather per season (rough shares): spring sun, clouds, rain; summer mostly sun, some clouds,
  rare storms; autumn clouds, rain, fog, storms; winter clouds, snow, fog, some sun. The festival
  day has sun or clouds.
- Sunrise and sunset per season: spring 06:00–20:00, summer 05:00–21:30, autumn 06:30–19:00,
  winter 08:00–17:00. Villagers' waking and sleeping hours stay as they are.
- Snow covers the ground on a snowy day and the day after.
- Fields need roughly 14 progress points from tilled to ripe (tilling and sowing one tended day
  each), so steady tending with some rain ripens them by early autumn; the exact numbers are a
  planning detail tuned so SC-003 holds.
- Growth state is one state per place, drawn over the whole place, not per cell.
- Villagers decide for themselves how to react to weather and the festival; the village only tells
  them and sets the festival's usual place, it never forces moves.
- "New" chronicle entries are tracked per browser; nothing is stored about the owner on the server.
- The chronicle entry is short: a title of a few words and a few sentences of diary text.
