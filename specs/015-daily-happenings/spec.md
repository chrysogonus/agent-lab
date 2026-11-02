# Feature Specification: M15 — Daily Happenings and Boat Trips

**Feature Branch**: `main` (feature directory `015-daily-happenings`)

**Created**: 2026-11-02

**Status**: Draft

**Input**: "M15 Daily happenings and boat trips: something different happens in the village every
day, so days stop looking alike, and the boat the village built gets used." The input lists
three parts:
- daily happenings (the postman, a visitor, a lost animal, a repair, a peddler);
- boat trips once the rowing boat is built;
- whispers from the owner.

It also asks that earlier contracts are kept and that every new behaviour is measured.

## Context

After M14 the villagers keep at what they set out to do, but every day follows the same shape:
they wake, work at their places, trade, talk briefly and go to bed. The only variety comes from
the weather, the trader's stock, the three-day meeting and the seasons. The chronicle reads much
the same from day to day.

The village catalogue holds a rowing boat (M12). Once built, it only lies at the pier.

The owner can watch the village but cannot take part in it.

This milestone adds three things:
- **Daily happenings**: one or two small events each village day that the villagers notice,
  talk about and deal with in their ordinary decisions.
- **Boat trips**: the built boat goes out on the lake, alone or in pairs.
- **Whispers**: the owner can whisper a line to one villager, which it takes as hearsay.

All earlier contracts apply:
- every model call is a traced run of a block agent;
- invalid answers change nothing and record why;
- tests use the scripted fake model only;
- no new dependency;
- reduced motion is respected;
- the owner's village is backed up before the world changes.

The M14 parts stay in use:
- villagers act through intentions and "what you can do here";
- M13's instruments measure the change, with new checks.

The roadmap after M15:
- M16 MCP;
- M17 the evaluation harness for the lab's other agents;
- M18 agent memory for the lab's other agents;
- M19 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who watches the village, reads its chronicle and measures it.

### User Story 1 - Daily happenings (Priority: P1)

Each village day brings one or two happenings, chosen from the day itself so the same day always
brings the same ones (like the weather and the trader's stock):

- **A letter**: the postman brings a letter to one villager's home in the morning. It holds news
  from outside (a cousin's wedding, prices in town, a storm at sea). The villager learns of it at
  home and may pass the news on.
- **A visitor**: a friend or relative of one villager arrives in the early afternoon and stays
  until evening. The host is told and spends time with them; others who meet the host meet the
  visitor too.
- **A lost animal**: a goat or a dog wanders into the village at some place. Whoever finds it
  can lead it back to the villager it belongs to.
- **A repair**: something breaks (the fence at the fields, the boards of the pier). Until someone
  works an hour at it, that place gives its goods more slowly.
- **A peddler**: a peddler stands at the square for a few hours with one unusual thing (a lantern,
  a fiddle, a book of songs). It trades it for a basket, as the trader does for building goods.

Each happening shows on the map:
- the postman walking;
- the visitor beside the host;
- the animal where it stands;
- a mark on the broken thing;
- the peddler at the square.

Villagers learn of a happening in three ways:
- by being there (they see it);
- by being the one it concerns (the letter, the visitor);
- by being told.

They react through their normal decisions, for example finding the owner of the goat, working
at the broken fence, or passing on the letter's news. A happening ends when it is dealt with (the
goat is home, the fence is fixed, the curiosity is traded) or when its time is over (the visitor
leaves, the peddler moves on). Every happening and how it ended is recorded, and the chronicle
tells of it.

**Why this priority**: it is the point of the milestone: days that differ from one another,
giving the villagers something to talk about and to do together.

**Independent Test**: with the scripted model:

- a day's happenings are the same each time that day comes;
- each kind appears, is seen by a villager there, can be dealt with, and ends with the reason;
- the day record and the chronicle prompt name it.

**Acceptance Scenarios**:

1. **Given** a new village day, **When** the first villager wakes, **Then** the day's happenings
   are set: one or two, of different kinds, each with its place, time and the villager it
   concerns (where there is one).
2. **Given** a lost goat at the market, **When** a villager next to it chooses to lead it home,
   **Then** the goat follows that villager to its owner's house, the happening ends as dealt
   with, and both villagers remember it.
3. **Given** a broken pier, **When** villagers fish there before it is mended, **Then** a basket
   takes longer, and an hour of work at the boards mends them.
4. **Given** a letter for Lina, **When** Lina is at home after the postman came, **Then** she is
   told its news, and what she says about it later is a claim for those who hear it.
5. **Given** a peddler at the square, **When** a villager carrying a basket trades for the
   curiosity, **Then** the villager keeps it as a keepsake (remembered and shown in its panel).
   It does not take up the villager's hands.
6. **Given** a happening nobody dealt with, **When** its time is over, **Then** it ends as
   "passed" and the chronicle may say so.

---

### User Story 2 - Boat trips (Priority: P2)

Once the rowing boat is built, a villager at the pier can take it out on the lake for about an
hour, alone or with one villager standing next to it who agrees.

- On the lake, fishing gives a basket of fish twice as fast as at the pier.
- A trip together is a conversation that does not fall silent until they are back.
- Both remember the trip.
- The boat is drawn moving on the lake, with whoever is in it.
- It returns to the pier at the end of the trip, or earlier at bedtime.

There is one boat: while it is out, nobody else can take it. Without the boat, or in a storm,
there are no trips.

**Why this priority**: the village built the boat in M12; using it gives built things a purpose.
It depends on a project that may not be built yet, so it ranks after the happenings.

**Independent Test**: with the scripted model:

- a villager at the pier takes the boat, rows out, fishes, and comes back after the trip;
- a second villager next to the first comes along when it agrees;
- there are no trips without the boat or in a storm.

**Acceptance Scenarios**:

1. **Given** the boat is built and Jonas is at the pier, **When** he sets out on a trip, **Then**
   he is on the lake for about an hour and back at the pier afterwards.
2. **Given** Jonas asks Greta, next to him at the pier, to come along, **When** Greta agrees,
   **Then** both go, their conversation lasts the trip, and both remember it.
3. **Given** the boat is out, **When** another villager tries to take it, **Then** that is
   refused with the reason.
4. **Given** the boat is not built, or a storm, **When** a villager tries to take a trip,
   **Then** it is refused with the reason, and the boat is not offered in "what you can do here".
5. **Given** a villager fishing from the boat, **When** half an hour has passed, **Then** it has a
   basket of fish (an hour at the pier).

---

### User Story 3 - Whispers (Priority: P3)

The owner can whisper a short line to one villager from its panel: a nudge ("Greta looks
tired"), a rumour ("they say the trader brings saplings tomorrow") or a wish ("visit Lina
today").

- The villager receives it as something "a voice" told it, marked as a claim like anything heard.
- It is asked what to do, as when someone speaks to it.
- The whisper shows in the villager's events and turns, so the owner sees what followed.
- A villager asleep hears the whisper when it wakes.
- Whispers are short, and a villager receives at most a few a day.
- Village health counts the day's whispers and how many were followed by a decision that did
  something other than wait.

**Why this priority**: it lets the owner take part and test ideas. It is small and depends on
nothing else.

**Independent Test**: with the scripted model:

- a whisper reaches the villager, triggers a decision, and shows in its events, its turn's
  prompt and the day's health;
- a whisper to a sleeping villager waits for the morning;
- too long a whisper, or too many in a day, is refused with the reason.

**Acceptance Scenarios**:

1. **Given** Greta awake, **When** the owner whispers "Lina wants to see you", **Then** Greta's
   next prompt has it among what she was told, marked as a voice's claim, and she decides.
2. **Given** Jonas asleep, **When** the owner whispers to him, **Then** he hears it on waking.
3. **Given** a villager who already heard the day's whispers, **When** the owner whispers again,
   **Then** the owner is told the limit is reached, and nothing changes.
4. **Given** a day with whispers, **When** the owner opens village health, **Then** the day shows
   how many whispers there were and how many were followed by an action.

---

### Edge Cases

- **A day with the festival or a meeting**: happenings still come. They are placed so they do
  not clash with the festival evening or the 17:00 meeting.
- **The one a happening concerns is busy or asleep**: a letter waits at home, and a visitor waits
  at the host's door until the host comes; it leaves in the evening either way.
- **Two villagers try to deal with the same happening**: the first succeeds; the second is told
  it is already dealt with.
- **The lost animal's owner is the one who finds it**: it can lead it home itself.
- **A repair at the place the boat leaves from**: a broken pier still lets the boat go out.
- **A trip at bedtime**: the boat comes back early, and both go home.
- **Reset**: happenings, trips, keepsakes and whispers are cleared like everything else.
- **A village saved by M14**: it keeps going, and its next new day gets happenings.
- **Whisper text**: the text is the owner's own, kept to the length limit. It never reaches
  another villager directly; only what the villager itself says does.

## Requirements *(mandatory)*

### Functional Requirements

**Daily happenings**

- **FR-001**: Each village day MUST have one or two happenings of different kinds, chosen
  reproducibly from the day, from five kinds:
  - a letter;
  - a visitor;
  - a lost animal;
  - a repair;
  - a peddler.
  Each has a place, a time window and, where it applies, the villager it concerns.
- **FR-002**: A happening MUST be noticed by villagers who are there, or whom it concerns, or who
  are told. It MUST appear in their observation as a fact when seen and as a claim when heard,
  and on the map.
- **FR-003**: Villagers MUST be able to deal with a happening through their decisions, with
  "what you can do here" offering the action when it is possible:
  - lead the animal home;
  - work at the broken thing;
  - trade for the curiosity;
  - spend time with the visitor;
  - read the letter at home.
- **FR-004**: A happening MUST end as dealt with (by whom) or as passed when its time is over.
  Its start and end are recorded in the day record. The chronicle prompt names the day's
  happenings as events.
- **FR-005**: A broken thing MUST slow the place's goods until it is mended. A keepsake MUST be
  remembered and shown in the villager's panel without taking up its hands.

**Boat trips**

- **FR-006**: When the rowing boat is built and the weather allows it, a villager at the pier
  MUST be able to take the boat out for about an hour, alone or with one villager next to it who
  agrees in its own decision.
- **FR-007**: On the lake, fishing MUST fill a basket in half the time it takes at the pier. A
  conversation in the boat MUST NOT end by falling silent during the trip, and both villagers
  MUST remember the trip.
- **FR-008**: There MUST be one boat at a time. Trips MUST be refused with a reason when there is
  no boat, the boat is out, or there is a storm. The boat MUST come back by bedtime.
- **FR-009**: The map MUST show the boat on the lake with whoever is in it, moving during the
  trip.

**Whispers**

- **FR-010**: The owner MUST be able to whisper a line of at most 200 characters to one villager
  from its panel. A villager receives at most 3 whispers per village day; more are refused with
  the reason.
- **FR-011**: A whisper MUST reach the villager as a claim from "a voice" among what it was told,
  and MUST trigger a decision. A sleeping villager MUST receive it on waking.
- **FR-012**: Whispers MUST be recorded in the villager's events and the day record. Village
  health MUST count per day the whispers and those followed by a decision other than wait.

**Measuring and keeping things working**

- **FR-013**: M13's instruments MUST be extended:
  - a turn check for each happening kind (5);
  - a turn check for taking the boat;
  - a scenario with the boat built, in which a trip happens;
  - village health counting each day's happenings, the share dealt with, boat trips and
    whispers.
- **FR-014**: The villager rules MUST describe the new answers. Stored agents still holding the
  M14 rules text get the new text on load; owners' edits stay.
- **FR-015**: A village saved by M14 MUST keep going, with happenings from its next new day on.
  Reset MUST clear happenings, trips, keepsakes and whispers.
- **FR-016**: Tests MUST use the scripted fake model only and cover every requirement above; all
  quality gates MUST pass, and every requirement maps to a test or a manual check in `tasks.md`.

### Key Entities

- **Happening**: one per kind per day at most. Holds:
  - its kind, place and time window;
  - the villager it concerns, if any;
  - its state (coming, here, dealt with by someone, passed);
  - its details (the letter's news, the visitor's name, the animal, the broken thing, the
    curiosity).
- **Keepsake**: something a villager traded the peddler for. Remembered and shown, not carried.
- **Boat trip**: who is in the boat, when it left, when it comes back.
- **Whisper**: the owner's line to one villager, when it was whispered and when it was heard.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Measured with the M13 instruments on the same model and settings as M14, on a copy of the
owner's village unless said otherwise.

- **SC-001**: Over 7 village days:
  - every day has at least one happening;
  - at least 60% of happenings are dealt with or talked about by a villager before they end;
  - the chronicle names the day's happening on at least 5 of the 7 days.
- **SC-002**: The new turn checks (one per happening kind, and taking the boat) each pass at
  least 14 of 20.
- **SC-003**: In the boat scenario, a boat trip happens in at least 4 of 5 runs, and in at least
  2 of 5 runs it is a trip together.
- **SC-004**: A whisper is followed by a decision within the same village step or the next in
  every case, and the owner can find that decision from the whisper in under 10 seconds.
- **SC-005**: The M14 numbers do not get worse:
  - waits stay at or below 35% of decisions;
  - model calls per village day stay within 20% of the M14 days (162–172);
  - none of the M14 checks is marked worse in a comparison.
- **SC-006**: On a 7-day read, no two consecutive chronicle entries share a title, and at least 5
  of 7 chronicle entries tell of something other than work, trade and the weather.

## Assumptions

- **Chosen from the day**: happenings are reproducible per day, like the weather. Replaying or
  copying a village gives the same happenings on the same days.
- **No new agents for happenings**: the postman, visitors, animals and the peddler are not model
  agents. They are figures and texts the village moves by fixed rules, so happenings add no model
  calls beyond the villagers' own decisions.
- **Small catalogue**: each kind draws from a short fixed list:
  - letters' news;
  - visitors' names and who they visit;
  - animals and their owners;
  - things that break;
  - curiosities.
  The lists are written for the four villagers.
- **The boat needs building**: the owner's village has not built the boat yet. Trips are tested
  on a fixture with the boat built, and appear in the owner's village once it is built.
- **Agreement in its own decision**: a companion joins a trip only by its own answer, never
  because another villager decided for it.
- **Whispers are local**: the owner is the only one who can whisper. A whisper is the owner's
  text placed in one prompt, marked as a claim and cut to the limit, like any line heard.
- **Weather**: only a storm stops trips. Rain and fog do not.
