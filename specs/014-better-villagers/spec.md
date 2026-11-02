# Feature Specification: M14 — Better Villagers

**Feature Branch**: `main` (feature directory `014-better-villagers`)

**Created**: 2026-11-02

**Status**: Draft

**Input**: After M13 the owner asked what comes next; the recommendation was to improve the three
weakest behaviours M13 measured, and to show each improvement with M13's instruments against its
baseline (`specs/013-measuring-the-village/tasks.md`, "Manual check results").

## Context

M13 measured the villagers on the real model. The baseline below covers the owner's days 43–61,
which hold 3,077 decisions:

- **Waits**: 45% of all decisions were waits.
- **Working in the wrong place**:
  - 188 refusals "there is no work for you here" (6.1 per 100 decisions);
  - at a building site holding saplings, the villager built 0 times in 40;
  - at her own fields in the morning, Greta worked 11 times in 40.
- **Reaching each other**:
  - 225 refusals "<villager> is not next to you" (7.3 per 100 decisions);
  - 43 refusals "already next to you";
  - 62 refusals "<villager>'s hands are full";
  - in the talk scenario, the pair that met never talked in 3 of 5 runs.
- **Leaving a talk**:
  - 188 refusals "you are talking with <villager>; say goodbye first" (6.1 per 100 decisions);
  - called to the meeting while talking, the villager left properly in 27 of 40 checks.
- **Stale memory**: villagers planned "for the festival" in summer, and 9 of 18 chronicles named
  weather the day did not have.

The villagers decide from scratch every turn. Each milestone so far added hints to their prompts
to steer them. This milestone makes three changes in how they behave rather than in what they
are told:

- **They hold intentions.** A villager keeps an intention until the intention is done, given up
  or replaced.
- **They reach each other.** Finding someone gets them next to that person, and they know who
  actually is.
- **They leave talks.** A villager with somewhere to be leaves a talk.

Their memory also fades with age and leans towards what fits the season.

All earlier contracts apply:
- every model call is a traced run of a block agent;
- invalid answers change nothing and record why;
- tests use the scripted fake model only;
- no new dependency;
- reduced motion is respected;
- the owner's village is backed up before the world changes.

The roadmap after M14:
- M15 Daily happenings and boat trips;
- M16 MCP;
- M17 the evaluation harness for the lab's other agents;
- M18 Agent memory for the lab's other agents;
- M19 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who watches the village and compares its health, checks and
scenarios with the M13 baseline.

### User Story 1 - Intentions (Priority: P1)

A villager decides what it sets out to do, and that becomes its **intention**. Examples:

- build at the site;
- work the fields until noon;
- take the load to the site;
- see Greta.

While the intention lasts, every turn shows it, together with the next step towards it. The
village keeps a villager on its intention where no new decision is needed: it walks there, starts
working on arrival, and keeps working until the time comes.

An intention ends in one of three ways:

- **Done**: the load is set down, the time is up, or the villager has met the person.
- **Given up**: the villager says so, or it can no longer be done (the site is gone, the person
  is asleep).
- **Replaced**: the villager chooses something else.

Every intention, and how it ended, is recorded.

**Why this priority**: most of the wasted turns come from villagers losing track of what they
were doing. An intention also replaces several of the hints that M11 and M12 added.

**Independent Test**: with the scripted model:

- a villager that says it intends to build at the site walks there, starts building, and goes on
  until its loads are used up, with no further decision needed;
- an intention that cannot be done ends with the reason;
- a new intention replaces the old one.

**Acceptance Scenarios**:

1. **Given** a villager answering with an intention (to work, to build, to bring a load, to see
   someone), **When** the answer is applied, **Then** the intention is stored with its
   target and, where given, its end time, and the first step is taken.
2. **Given** a villager with an intention, **When** it reaches the place, **Then** the next step
   (working, setting down, talking) happens without another model call where the step is
   certain, and the villager is asked only when something happens.
3. **Given** a villager working on an intention "until noon", **When** noon comes, **Then** the
   intention is done and the villager is asked what next.
4. **Given** an intention that can no longer be done, **When** that is noticed, **Then** it ends
   as "given up" with the reason, and the villager is told.
5. **Given** the villager panel, **When** the owner opens a villager, **Then** they see its
   intention, and its turns show when intentions began and ended.

---

### User Story 2 - Reaching each other (Priority: P1)

- **Finding** someone ends next to them, or with "not there" and where they were last seen. When
  the person moves, the seeker follows them while they are in sight.
- **Who is next to you**: every turn says exactly who is next to the villager, separately from
  who is merely in sight.
- **Handing things over**: a villager no longer tries to hand its goods to whoever happens to be
  near. Giving to someone happens only when that person is the goal of the villager's intention,
  or asked for the goods.

**Why this priority**: "not next to you" is the single most common refusal (7.3 per 100
decisions), and meeting someone is how villagers talk, trade and plan together.

**Independent Test**: with the scripted model:

- a find ends next to the person, even when the person walks on while in sight;
- a say to someone not next to the villager is turned into finding them first, rather than
  refused;
- a give to a villager who neither asked nor is the intention's goal is refused with a reason
  that names what the goods are for.

**Acceptance Scenarios**:

1. **Given** a villager finding someone who walks away while in sight, **When** the steps pass,
   **Then** the seeker follows them and ends next to them.
2. **Given** a villager answering say to someone in sight but not next to it, **When** the answer
   is applied, **Then** it sets off to find that person and says the line on arrival.
3. **Given** a villager carrying a load the project needs, next to Hilde, **When** it answers
   give to Hilde, **Then** it waits with "your load belongs at the building site", unless Hilde
   asked for it.
4. **Given** every turn, **When** the observation is built, **Then** it lists who is next to the
   villager and who is only in sight, by name, in separate lines.

---

### User Story 3 - Leaving a talk (Priority: P2)

A villager with an intention that takes it elsewhere leaves its talk by itself, saying goodbye
in its own words. The same happens when its time comes, at bedtime, or when it is called to the
meeting. The special rules for bedtime and the meeting become this one rule.

A villager without anywhere to be keeps talking as before. Two villagers whose intentions point
the same way walk on together while talking.

**Why this priority**: 188 refusals came from villagers trying to walk off in the middle of a
talk. It builds on intentions (US1).

**Independent Test**: with the scripted model:

- a villager talking when its intention's time comes says goodbye and goes;
- a villager without an intention stays;
- two villagers going the same way keep talking as they walk.

**Acceptance Scenarios**:

1. **Given** a talking villager whose intention starts now elsewhere, **When** it next decides,
   **Then** a move or find is turned into a goodbye followed by setting off, never a refusal.
2. **Given** bedtime or the meeting call during a talk, **When** the time comes, **Then** the
   villager says goodbye and goes. The earlier special cases are removed, and their tests still
   pass.
3. **Given** two talking villagers going to the same place, **When** one sets off, **Then** both
   walk on, and the talk goes on until they part.

---

### User Story 4 - Memory that fades and fits the season (Priority: P3)

When a memory is recalled, its age and the season it came from count:

- old memories fade;
- memories from another season count for less, unless they are about the people at hand;
- reflections older than a few days are folded into a short summary.

Plans and decisions in summer no longer revolve around last autumn's festival. Talk of weather
that is not the day's is marked as talk, so the chronicle does not report it as weather.

**Why this priority**: it improves what villagers think about rather than what they do, and its
effect shows over days, not single turns.

**Independent Test**: with scripted memories:

- in summer, a festival memory from the previous autumn ranks below a recent one of equal
  importance;
- reflections older than a few days are summarised;
- the chronicle prompt marks weather talk as claims.

**Acceptance Scenarios**:

1. **Given** memories of equal importance from last autumn and from yesterday, **When** a
   villager decides in summer, **Then** yesterday's ranks higher.
2. **Given** more than a few days of reflections, **When** the village day ends, **Then** the
   older ones are kept as one summary and the recent ones as they are.
3. **Given** a day record with villagers talking about a storm on a sunny day, **When** the
   chronicle is written, **Then** the prompt names the storm as talk, not weather.

### Edge Cases

- **An intention without a place**: "see Greta" while Greta's place is unknown → the villager
  goes where it believes she is. If she is not there, the intention ends as "not found", with
  where she was last seen.
- **Two intentions at once**: a new intention replaces the old one. The old one is recorded as
  replaced.
- **An intention across a night**: intentions end at bedtime as "the day is over". The next
  morning's plan starts fresh.
- **Following someone out of sight**: the find ends as "lost sight of them", with where they
  were last seen.
- **A say turned into a find**: the line is said on arrival only if the person is still awake
  and not talking with someone else; otherwise it is dropped and the villager is told.
- **Asked for goods**: a villager may give to someone who asked for those goods in the last hour,
  even when that is not its intention.
- **Owner-edited agents**: the new rules reach stored agents only where they still hold the
  earlier rules text, as in every milestone.
- **An M13 village**: an M13 village loads with no intentions. Its memories stay; the summary is
  made the next night.

## Requirements *(mandatory)*

### Functional Requirements

**Intentions**

- **FR-001**: A villager's answer MUST be able to state an intention: build at the site, work
  where it is or at a named place, bring its load to the site, see a named villager, or go to a
  place. An intention may have an end time, and has a short purpose. An invalid intention is
  refused with the reason, as any action is.
- **FR-002**: While a villager has an intention, the village MUST take each certain step towards
  it without a model call: walk to the place, start working there, set a needed load down at
  the site, and talk on meeting the person. The villager MUST be asked only when something
  happens, or when the next step needs a choice.
- **FR-003**: An intention MUST end as done, given up (by the villager, or because it can no
  longer be done) or replaced. Each start and end, with its reason, is recorded in the
  villager's events and the day record.
- **FR-004**: Every observation MUST show the villager's intention and its next step. The
  villager panel MUST show the intention, and the turn list MUST show intentions as they
  started and ended.

**Reaching each other**

- **FR-005**: Find MUST follow the person while they are in sight, end next to them, or end with
  "lost sight of them" or "not there" and the last place seen.
- **FR-006**: A say to an awake villager in sight but not next to the speaker MUST become a find
  that says the line on arrival.
- **FR-007**: A give to a named villager MUST be refused unless that villager is the goal of the
  giver's intention, or asked for those goods in the last hour. The reason says what the goods
  are for (the building site, the festival stalls).
- **FR-008**: The observation MUST name who is next to the villager and who is only in sight, in
  separate lines.

**Leaving a talk**

- **FR-009**: A talking villager whose intention, time, bedtime or meeting call takes it
  elsewhere MUST leave with a goodbye and set off. Its move or find is turned into that goodbye
  rather than refused. The bedtime and meeting special cases are replaced by this rule.
- **FR-010**: Two talking villagers going to the same place MUST walk on together, and their talk
  goes on.

**Memory**

- **FR-011**: Recall MUST weigh a memory's age and season. A memory from another season counts
  for less unless it is about someone at hand.
- **FR-012**: Reflections older than a few days MUST be folded into one summary per villager by
  the reflection agent at night (one more run at most per villager per night). The recent ones
  are kept as they are.
- **FR-013**: The chronicle prompt MUST mark weather talk in the day's notes as claims.

**Measuring the change**

- **FR-014**: M13's turn checks and scenarios MUST be extended to cover each new behaviour, with
  at least one check per user story. The checks of M13 keep running unchanged as the comparison
  baseline.
- **FR-015**: The villager rules MUST describe intentions; stored agents still holding the M12
  rules text get the new text on load.
- **FR-016**: A village saved by M13 MUST keep going with no intentions. Reset clears the
  intentions.
- **FR-017**: Tests MUST use the scripted fake model only and cover every requirement above; all
  quality gates MUST pass, and every requirement maps to a test or a manual check in `tasks.md`.

### Key Entities

- **Intention**: per villager. Holds:
  - the kind (work, build, bring, see, go) and its target (a place, the site, a villager);
  - an optional end time;
  - a purpose;
  - when it began;
  - its next step;
  - how it ended and why.
- **Request**: a villager's ask for goods from another ("Jonas, can I have fish?"). Kept for an
  hour, so the asked one may give.
- **Memory summary**: per villager, what older reflections said, in a few sentences.

## Success Criteria *(mandatory)*

### Measurable Outcomes

All are measured with M13's instruments against the M13 baseline, on the same model and settings.

- **SC-001**: These checks are marked **better** (beyond chance) against the M13 result at 20
  repeats: `build-with-loads` (0/40), `work-at-own-place` (11/40) and `meeting-call-talking`
  (27/40). No M13 check is marked **worse**.
- **SC-002**: The `talk-then-go` scenario holds in at least 3 of 5 runs (0/5 at baseline). The
  other two M13 scenarios still hold in at least 4 of 5.
- **SC-003**: Over three village days at Fast on a scratch copy of the owner's village, each of
  these refusals is at most half its baseline rate per 100 decisions: "there is no work for you
  here" (6.1), "<villager> is not next to you" (7.3), "you are talking with <villager>; say
  goodbye first" (6.1).
- **SC-004**: Over the same three days, waits are at most 35% of decisions (45% at baseline), and
  model calls per village day are no more than at baseline.
- **SC-005**: On those days, no summer or winter plan or decision prompt is dominated by festival
  memories: at most 1 of the 8 recalled memories is from another season. At most 1 of 3
  chronicles names weather the day did not have.
- **SC-006**: The new checks (one per user story at least) pass in at least 15 of 20 attempts on
  the real model.

## Assumptions

- **One intention at a time**: a villager holds at most one intention, and the daily plan stays
  as it is. An intention is the current step of the day, not a second plan.
- **Intentions are part of the answer**: the decision's answer gains an optional intention, so
  the same agent decides and intends, with no extra model call.
- **No model calls for certain steps**: walking, starting work and setting down are certain
  steps.
- **Follow while in sight**: following uses the same sight as today (6 cells).
- **The summary is a reflection**: the summary is written by the reflection agent in its nightly
  run, with no new agent.
- **Same instruments**: success is measured with the M13 instruments unchanged, so the numbers
  compare with the baseline.
