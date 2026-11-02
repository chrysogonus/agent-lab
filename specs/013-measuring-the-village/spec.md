# Feature Specification: M13 — Measuring the Village

**Feature Branch**: `main` (feature directory `013-measuring-the-village`)

**Created**: 2026-11-02

**Status**: Draft

**Input**: After M12 the owner asked what could be improved in the villagers' behaviour, movement
and interactions, and how to test whether the behaviour is as expected or desired. The owner
chose the recommendation: make the behaviour measurable first, then change it.

## Context

The M12 checks on the real model showed how little a single run says:

- **Results varied widely.** With the same code and starting world, six-day runs ranged from
  nothing done to a finished project.
- **Behaviour came from hints.** Six rounds of prompt hints were needed before the village
  finished a project, and each round was judged by reading logs by hand.
- **Much effort was wasted.**
  - 39–45% of all villager decisions were waits.
  - About 60 refusals per run came from villagers trying to walk away in the middle of a talk.
  - 56–62 refusals per run were attempts to work where there is no work.
  - 17–30 refusals per run were attempts to hand things to Hilde while her hands were full.
- **Stale memories and invented weather persist.** Villagers planned "for the festival" in
  summer, and chronicles named storms and snow that never came.

This milestone gives the owner three instruments, so the next milestone (M14 Better villagers:
intentions instead of hints, walking while talking, memory that fades with age and season) can
show whether a change helps:

1. **Village health**: numbers for every village day, computed from what is already recorded.
2. **Turn checks**: single situations given to the real model many times, each with the answer
   that is wanted, giving a pass rate.
3. **Scenarios**: short slices of village life from a fixed start on the real model, run several
   times, each with a condition that should hold at the end, giving a pass rate.

Results are kept, so a run before a prompt or model change can be compared with one after.

All earlier contracts apply:

- Every model call is a traced run of a block agent; the village never calls the model directly.
- The automated tests use the scripted fake model only. Turn checks and scenarios on the real
  model are separate and never part of the quality gates.
- No new dependency.
- The owner's village is never touched by a scenario: scenarios run on copies.

The roadmap moves back by one:
- M14 Better villagers;
- M15 Daily happenings and boat trips;
- M16 MCP;
- M17 the evaluation harness for the lab's other agents;
- M18 Agent memory for the lab's other agents;
- M19 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who changes prompts, rules and models, and wants to know whether
the villagers then behave better or worse.

### User Story 1 - Village health per day (Priority: P1)

For every village day, the owner sees a set of numbers about how the villagers behaved, next to
the chronicle: how many decisions they made and how many were waits, why actions were refused,
how long conversations lasted, how well villagers kept their plans, how meetings and building
went, and whether anyone was stuck. The numbers come from what the village already records, for
the owner's village and for any copy run as a scenario.

**Why this priority**: it costs no extra model calls, works on the live village and every past
day, and makes every later change visible.

**Independent Test**: with scripted days (fake model), the health of each day matches counts
made by hand from the same runs and world: decisions, waits, refusals by reason, conversation
lengths, repeated lines, plan adherence, meeting attendance, trades, loads and their times,
baskets passed back, weather slips, villagers stuck, model calls.

**Acceptance Scenarios**:

1. **Given** a village day that has ended, **When** the owner opens village health, **Then**
   they see that day's numbers (listed in FR-002), and each number links to the turns it counts
   where that makes sense (for example the refusals of one reason).
2. **Given** several days, **When** the owner looks at village health over time, **Then** they
   see each number per day, so a change on one day stands out.
3. **Given** the day in progress, **When** the owner opens village health, **Then** they see
   the numbers so far, marked as not final.
4. **Given** a scenario run on a copy, **When** it ends, **Then** the same numbers are computed
   for its days and kept with the scenario's result.

---

### User Story 2 - Turn checks (Priority: P1)

The owner keeps a list of situations, each a villager's (or Hilde's, or the planner's)
prompt, either taken from a recorded turn or written by hand. Each situation states the kind of
answer that is wanted: "carrying a needed load at the building site → sets it down"; "talking
when called to the meeting → says goodbye and goes to the town hall"; "spoken to by Greta →
answers Greta". One command gives every situation to the real model several times and reports
how often the answer was the wanted kind, per situation and overall.

**Why this priority**: it is the cheapest way to see whether a prompt or model change moves a
known weakness, it runs in minutes, and the recorded turns of M11 and M12 already hold the
situations.

**Independent Test**: with the scripted fake model standing in for the real one, running the
checks counts passes and failures correctly for each kind of expectation, keeps the result, and
compares it with an earlier result.

**Acceptance Scenarios**:

1. **Given** a recorded turn, **When** the owner adds it as a turn check with a wanted kind of
   answer, **Then** the check holds the exact prompt of that turn, the agent it was asked of,
   and the expectation.
2. **Given** the list of checks, **When** the owner runs them (each, for example, 10 times),
   **Then** each check reports its pass rate and the answers that failed with why, and every
   attempt is an ordinary traced run.
3. **Given** a result from before a change, **When** the owner runs the checks again after it,
   **Then** they see, per check, the pass rate before and after.
4. **Given** the automated tests, **When** they run, **Then** no turn check calls a real model.

---

### User Story 3 - Scenarios (Priority: P2)

The owner keeps a list of scenarios. Each one is:

- a fixed starting village (the day, the time, where everyone is, what they carry, what is
  being built);
- a horizon, a few village hours to a few village days;
- a condition that should hold, for example:
  - "at least three villagers attend the meeting, starting from 16:00 on a meeting day";
  - "a load bought at 10:00 lies at the building site by 12:00";
  - "two villagers who meet talk at most 6 lines and then go about their day".

One command runs each scenario several times on the real model, each time on a fresh copy, and
reports how often the condition held, with the village health of every run.

**Why this priority**: it shows behaviour that unfolds over hours, which turn checks cannot,
but it is slower and costs many model calls.

**Independent Test**: with the scripted fake model, a scenario starts from its fixed village on
a fresh copy, runs to its horizon without waiting in real time, evaluates its condition, keeps
the result with the health numbers, and leaves the owner's village untouched.

**Acceptance Scenarios**:

1. **Given** a scenario, **When** it runs, **Then** it runs on a fresh copy, from the same
   start every time, to its horizon, and the owner's village is not changed.
2. **Given** several runs of a scenario, **When** they end, **Then** the owner sees how many held
   the condition, and for each run why it held or failed, its health numbers and its chronicle.
3. **Given** a result from before a change, **When** the scenarios run again after it, **Then**
   the owner sees the pass rates before and after.

### Edge Cases

- **A day with no decisions.** The village was paused all day → the day shows no numbers rather
  than zeros that look like a result.
- **Days before M13.** The village keeps only its current state, villagers' last ten events and
  the decision prompts, so where everyone was between decisions cannot be rebuilt for days before
  M13. For those days village health shows what the stored runs and day records support
  (decisions, waits, refusals, lines, trades, meetings, model calls) and marks the rest, plan
  adherence and time stuck among them, as unavailable, never as zero.
- **A failing model call.** A run that failed counts as a failed call, not as a wait or a
  refusal; a turn check whose run failed counts as a failure with the reason "the run failed".
- **Turn checks after a prompt change.** A check kept as a recorded prompt asks yesterday's
  prompt again and cannot see a change to how prompts are built (such as the M12 hints). Checks
  built from a world fixture build their prompt with today's code every time, so they test such
  a change; every result records which kind each check was.
- **A scenario that ends early.** The model server goes down, or the village pauses after failed
  steps → that run is marked as not finished and does not count towards the pass rate.
- **Comparing different settings.** Results compared across different models or numbers of
  repeats show which model, settings and repeats each used.
- **Reset.** Resetting the owner's village keeps the stored check and scenario results; village
  health starts again from day 1.

## Requirements *(mandatory)*

### Functional Requirements

**Village health**

- **FR-001**: The village MUST, from M13 on, keep a compact day trail: for every step, each
  villager's place (or cell), state and what it carries, kept for at least the days the chronicle
  keeps. The system MUST compute, for every village day, a health record from the stored runs,
  the day records and the day trail, for the owner's village and for every scenario copy; a
  number whose source is missing for a day is marked unavailable.
- **FR-002**: The health record MUST include:
  - decisions, and the share that were waits;
  - refusals per reason;
  - the number of conversations and their lengths in lines;
  - lines refused as repeated;
  - plan adherence: the share of plan entries a villager was at, or with, within an hour of its
    time;
  - meeting attendance, votes and how the meeting ended;
  - trades;
  - loads set down and loads worked in, with the time from buying to setting down;
  - baskets given straight back;
  - chronicle entries that named weather the day did not have;
  - villagers in one state for more than an hour while awake;
  - model calls by kind (decisions, plans, reflections, chronicle, meeting runs) and failed calls.
- **FR-003**: The owner MUST be able to see each day's health record and the records over time
  in the village view, with the current day marked as not final, and open the turns behind a
  refusal reason.

**Turn checks**

- **FR-004**: A turn check MUST consist of:
  - the agent asked (a villager, the planner or the meeting agent);
  - its situation, in one of two kinds: a **world fixture** (a village state and whose turn it
    is, from which the prompt is built with today's code on every run) or a **frozen prompt**
    (the exact prompt of a recorded turn or a written one, asked as it is);
  - a name;
  - the wanted kind of answer. That is one of: an action, possibly with its target (for example
    give, goodbye with the town hall as its place, say to a named villager); a valid answer of
    the right shape for the planner and the meeting; or a list of answers that are not wanted.
- **FR-005**: The owner MUST be able to create a frozen-prompt check from a recorded turn,
  keeping its exact prompt and agent, and to write either kind by hand. The shipped checks that
  guard prompt behaviour (FR-012) MUST be world fixtures, so a change to the prompts is tested.
- **FR-006**: Running the checks MUST give each one to its agent on the real model a chosen
  number of times. Each attempt is an ordinary traced run, marked as a check. The result reports,
  per check and overall, the passes out of the attempts with the range a rate from that many
  attempts can honestly claim (a 95% interval), every failed answer with why it failed, and
  whether the check was a world fixture or a frozen prompt.
- **FR-007**: Check results MUST be kept with the date, the model and its settings, and the
  number of repeats, and the owner MUST be able to compare two results check by check; the
  comparison marks a check as changed only when the two rates differ by more than chance
  explains for their numbers of attempts, and otherwise as "no clear change".

**Scenarios**

- **FR-008**: A scenario MUST consist of:
  - a name;
  - a starting village: the day, the time, and each villager's place, state and what it carries,
    plus the project, the trader and the meeting where they matter;
  - a horizon in village time;
  - a condition over the run's events and final state.
- **FR-009**: Running a scenario MUST start each run from a fresh copy of the owner's agents and
  the scenario's starting village, run at the fastest pace without real-time waiting where
  possible, never change the owner's village, and stop at the horizon.
- **FR-010**: A scenario result MUST report, for each run, whether the condition held and why,
  the health records of its days and its chronicle, and the pass rate over all runs. Unfinished
  runs are shown and not counted.
- **FR-011**: Scenario results MUST be kept and compared like check results (FR-007).
- **FR-012**: The milestone MUST ship with the turn checks and scenarios named in the user
  stories:
  - at least 12 turn checks, drawn from the M11 and M12 manual checks;
  - at least 3 scenarios: meeting attendance from 16:00, a bought load reaching the site, and a
    meeting pair that talks briefly and moves on.

**State and quality**

- **FR-013**: Turn checks and scenarios MUST run from the command line. Their runs MUST be
  listed apart from the owner's villagers' turns, so they do not mix with the village's own
  history.
- **FR-014**: The automated tests MUST use the scripted fake model only and cover:
  - every health number on scripted days;
  - each kind of expectation passing and failing;
  - creating a check from a recorded turn;
  - a world-fixture check building its prompt with today's code;
  - the day trail kept each step, and numbers marked unavailable without it;
  - the 95% range and a comparison that marks only changes beyond chance;
  - a scenario run on a copy that leaves the owner's village unchanged;
  - an unfinished run;
  - comparing two results;
  - a day with no decisions;
  - days recorded before M13.
- **FR-015**: All quality gates MUST pass; every requirement maps to a test or a manual check in
  `tasks.md`.

### Key Entities

- **Day health**: per village (the owner's or a scenario copy) per day. Holds the numbers of
  FR-002 and whether the day is final.
- **Turn check**: a name, the agent, its situation (a world fixture or a frozen prompt, and
  where that came from) and the expectation.
- **Day trail**: per village per step, each villager's place or cell, state and what it
  carries; the source for plan adherence and time stuck.
- **Check result**: when the checks ran, the model and settings, the repeats, and per check the
  passes, the failures and their answers.
- **Scenario**: a name, the starting village, the horizon and the condition.
- **Scenario result**: when it ran, the model and settings, and per run whether it held and why,
  whether it finished, its day health and its chronicle.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For scripted days, every health number equals the count made by hand from the same
  runs and world.
- **SC-002**: On the owner's village, the health of a past day appears in under 2 seconds.
- **SC-003**: The shipped turn checks (at least 12) run 10 times each on the real model in under
  15 minutes and report a pass rate per check (manual check).
- **SC-004**: The shipped scenarios run 5 times each on the real model, and report pass rates and
  every run's health (manual check). The owner's village state is unchanged before and
  after.
- **SC-005**: Every check result shows passes out of attempts with its 95% range, and a
  comparison of two results marks a check as changed only beyond chance. Comparing two runs of
  the unchanged checks on the real model, at 20 attempts each, marks at most 2 of the shipped
  checks as changed (manual check; the expected number by chance alone is under 1).
- **SC-006**: Using the health of the owner's recent days and the shipped checks and scenarios,
  the owner can name the three weakest behaviours with numbers. This is the baseline M14
  improves on (manual check, recorded in `tasks.md`).

## Assumptions

- **No new runs for health.** Village health is computed from runs and village state that are
  already stored; it adds no model calls.
- **Repeats are the owner's choice.** Turn checks and scenarios run on whichever model the
  agents use. The number of repeats is chosen per run, defaulting to 10 for checks and 5 for
  scenarios; with so few attempts only large differences are clear, which the result says.
- **Scenario copies.** A scenario copy holds the owner's agents (with their current prompts)
  and the scenario's starting village; memories and learnings come from the starting village,
  not from the owner's village.
- **Fixed conditions.** Conditions and expectations are fixed checks written with the scenario
  or check. Judging free text (in character, coherent, faithful) with a stronger judge model
  and a rubric is left for later.
- **Where results show.** Results are shown on the command line and kept. Only village health
  appears in the village view in this milestone.
