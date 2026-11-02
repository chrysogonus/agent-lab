---
description: "Task list for M14 — Better Villagers"
---

# Tasks: M14 — Better Villagers

**Input**: `specs/014-better-villagers/` (plan.md, spec.md, research.md, data-model.md,
contracts/villager-answers.md, quickstart.md)

**Tests**: requested by the spec (FR-017). `FakeLLM` only, and the failing test is written
first. Runner tests pass `move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **Your village stays safe.** Stop `make dev` and back up `backend/data/agent_lab.db` (sqlite
  backup API) before the store, world or runner change. The world-version bump, `upgrade` and
  `_load` change in one write (memory note `dev-reload-resets-village`).
- **Rules change in steps.** The rules advertise only what the parser accepts. Each change to
  `RULES` moves the replaced text into `OLD_RULES`, starting with the M12 text as
  `_M12_SITE_RULES`.
- **Certain steps cost no model call.** They are walking, starting work on arrival, setting down
  a needed load at the site, and saying a stored line. Every intention start and end is an event
  plus a day-record note.
- **The M13 checks stay as they are.** The 14 M13 checks are never edited; they are the
  baseline.

---

## Phase 1: Setup — split the runner (behaviour unchanged)

- [X] T001 Move the meeting runs out of backend/src/agent_lab/village/runner.py into new
  backend/src/agent_lab/village/meeting_runs.py, as `class MeetingRuns`, a mixin that `Village`
  inherits.
  - Methods to move: `_meeting`, `_call_to_meeting`, `_open_meeting`, `_end_meeting`,
    `_start_meeting_run`, `_meeting_call`, `_asked_again`, `_still`, `_propose`, `_vote`,
    `_decide_meeting`, `_decided`, `_assign`, and the `_meeting_state` static.
  - The mixin declares the attributes it uses (`world`, `store`, `meetings`, `secrets`,
    `resetting`) for pyright, plus stubs for the runner methods it calls (`_run`, `_event`,
    `_note`, `_remember`, `_villager`, `_trigger`, `_publish`).
  - No test changes. `make check` must pass unchanged, and `runner.py` ends at about 1,275 lines.
  - Done with the code-simplification skill.
  - Requirement: plan, constitution I.

## Phase 2: Foundational — world version 7 and what you can do here

- [X] T002 World version 7.
  - backend/src/agent_lab/village/world.py:
    - `VERSION = 7`;
    - per villager `intention: None` and `requests: []`;
    - `upgrade()` 6 → 7 with an explicit step.
  - runner.py:
    - `_load` accepts versions 2–6;
    - Reset clears both new fields;
    - `state()` sends `intention` (`{kind, place, villager, until: "HH:MM" | null, purpose,
      since: "HH:MM"}` or null) and leaves out `requests`.
  - Tests in test_village_world.py: the new shape, and a v6 world upgrading with the fields
    empty.
  - Tests in test_village_runner.py:
    - a v6 world loads and keeps going;
    - Reset clears the fields;
    - the state shape.
  - Requirement: FR-016.
- [X] T003 [P] New backend/src/agent_lab/village/affordances.py (research §2): `can_do(world,
  name) -> list[tuple[dict, str]]`. It returns at most 6 entries, in this order:
  - `work` (when `work_refusal` is None);
  - `build` (at or away from a site holding loads);
  - `bring` (carrying a load the project still needs);
  - `buy` per goods in stock (when `buy_refusal` is None);
  - `give` without a name (stalls or site, when `give_refusal` is None);
  - `say` to each awake villager next to you.

  Each entry's JSON is exactly what the parser accepts, and its why is short ("the site holds 2
  saplings"). Tests in new backend/tests/test_village_affordances.py:
  - each entry appears exactly when its refusal is None;
  - the order and the cap;
  - every listed JSON passes `parse_action` against the same world.

  Requirements: FR-002, FR-008 (support).

## Phase 3: User Story 1 — Intentions (P1) 🎯 MVP

- [X] T004 [P] [US1] New backend/src/agent_lab/village/intention.py (research §1, data-model.md
  "Intention steps").
  - `KINDS = ("go", "work", "build", "bring", "see")`.
  - `start(world, name, action) -> intention`, where `until` is a minute of the day and
    `purpose` is "cut to 120".
  - `next_step(world, v) -> dict`, giving walk, start_work, set_down, say, done, given_up or
    none. The rules:
    - go: done on arrival;
    - work: walk to the place, then start_work; done when `until` comes;
    - build: walk to the site, then start_work at the site; done at `until`; given up when the
      project is gone, or when the site holds no loads and the villager carries none it needs;
    - bring: walk to the site, then set_down, then done;
    - see: walk to the target; say when next to them and a line is stored; done when next to
      them; given up when they are asleep, out of sight from the last place seen, or not there.
  - `intention_text(intention)`: "You are set on: build at the building site until 15:00 (to
    plant the trees). Next: walk there."
  - `ended_text(name, intention, why)`.

  Tests in new backend/tests/test_village_intention.py: every kind through every step on
  fixture worlds (`build_world`), each end with its reason, and `until` before and after.
  Requirements: FR-001, FR-002, FR-003.
- [X] T005 [US1] backend/src/agent_lab/village/turn.py: the answers.
  - `Work` gains `place` and `until`; new `Build {until}` and `Bring`; `Find` gains `say`.
  - `parse_action` validates them:
    - places with `place_named`;
    - "until" as `HH:MM`, later than now;
    - build needs a project;
    - bring needs a carried load the project still needs ("you carry nothing the building site
      needs");
    - work with a place is valid when that place could be worked (`work_refusal` against a copy
      of the villager placed there);
    - say is cut to `SPEECH_SHOWN`.
  - The parsed action carries `"intention"` (from `intention.start`).

  Tests in test_village_turn.py: every new answer, valid and refused with its reason.
  Requirement: FR-001.
- [X] T006 [US1] runner.py:
  - `_apply` starts the intention for move, work, build, bring and find. A previous one ends as
    "replaced", with the event `intention_ended` and a note. The start gets the event
    `intended` and the note "Greta set out to build at the building site until 15:00."
  - In `_advance`, after the moves and before the work and build steps, `next_step` runs for
    each awake villager with an intention:
    - walk sets the goal;
    - start_work sets `working`;
    - set_down applies the existing give at the site;
    - say applies `_say`;
    - done and given_up end the intention, with an event, a note and the trigger
      `intention_ended`.
  - `_due`: no idle re-decision while an intention lasts.
  - `_walk`: "arrived" triggers only when the arrival ends the intention.
  - Bedtime ends the intention ("the day is over").
  - The decision's `village_action` carries `intention`.

  Tests in test_village_runner.py, all scripted:
  - build: a single answer takes Greta to the site, starts building and works in loads with no
    further model calls until something happens;
  - work until noon ends at noon, with a decision;
  - bring sets the load down on arrival;
  - see with a line says it on arrival;
  - replace, given up and bedtime;
  - fewer decision calls over a scripted hour than without the intention.

  Requirements: FR-001–FR-003.
- [X] T007 [US1] The observation and the rules (turn.py, plan.py):
  - the observation gets the intention line, "You are not set on anything.", and "What you can
    do here:" from `can_do` (JSON and why);
  - remove from the observation the hints `delivery_text`, the site hints in
    `build.project_text` (keep its project and share lines) and the buy hint, keeping the
    planner's autumn line;
  - `RULES` gains work with place and until, build, bring, find with say, and "you keep doing
    what you set out to do until it is done; you are asked when something happens";
  - the M12 text joins `OLD_RULES`;
  - adjust the M11 and M12 tests that asserted the removed hints, so they assert the
    affordance entries instead.

  Tests:
  - test_village_turn.py: the sections, and the hints gone;
  - test_village_runner.py: the rules refresh from the M12 text.

  Requirements: FR-004, FR-015.
- [X] T008 [US1] Frontend:
  - frontend/src/lib/api.ts: `Villager.intention`; the `VillageAction` work (place, until),
    build, bring and find (say), with `intention`; event kinds `intended` and `intention_ended`.
  - lib/village.ts:
    - `intentionText(intention)` ("Building at the site until 15:00");
    - `stateText` uses the intention when there is one;
    - `turnLabel` for build and bring, and for move, work and find showing the intention.
  - VillagerPanel.tsx: a "Set on" line under Today's plan.

  Tests in village.test.ts. Requirement: FR-004.
- [X] T009 [P] [US1] backend/evals/checks/intention-keeps-building.json: Greta building at the
  site with 2 saplings, the intention "build until 15:00", a "met" trigger with Lina next to her.
  The expectation is `{"not": [{"action": "move"}, {"action": "find"}]}`. Plus its ideal answer
  in the shipped-check test. Requirement: FR-014.

## Phase 4: User Story 2 — Reaching each other (P1)

- [X] T010 [US2] turn.py and runner.py:
  - a say to an awake villager in sight but not next to the speaker becomes `{"action": "find",
    "villager", "say", "intention"}`;
  - a find of someone next to you becomes a wait "<name> is right next to you; talk to her"
    (not counted as a refusal of the move kind);
  - a find whose person leaves sight ends the see intention as given up: "you lost sight of
    Greta near the market".

  Tests in test_village_turn.py and test_village_runner.py, including following someone who
  walks on and ending next to them. Requirements: FR-005, FR-006.
- [X] T011 [US2] The give rule and requests:
  - runner `_say` notes a request on the hearer when the speaker's line names goods ("fish",
    "wood", …): `{from, goods, tick}`, kept for 6 steps;
  - `give_refusal` with a name refuses unless the receiver is the giver's see target, or
    requested those goods within 6 steps. The reason says what the goods are for: "your wood
    belongs at the building site", "your fish is for the festival stalls or for someone who
    asks", "Hilde did not ask for it".

  Tests in test_village_work.py and test_village_runner.py:
  - a give after a request;
  - a give to the see target;
  - a refusal with each reason;
  - a request kept for 6 steps and then forgotten.

  Requirement: FR-007.
- [X] T012 [US2] turn.py: "Next to you: Greta." and "In sight: Hilde (4 steps away)." give names,
  not titles. Test in test_village_turn.py. Requirement: FR-008.
- [X] T013 [P] [US2] backend/evals/checks/say-to-someone-in-sight.json: Jonas, with Greta 3 steps
  away and in sight, and a plan entry "see Greta: ask for vegetables". The expectation is
  `{"action": {"action": "find", "villager": "Greta"}}`, which a say to Greta also passes once
  T010 turns it into a find. Requirement: FR-014.

## Phase 5: User Story 3 — Leaving a talk (P2)

- [X] T014 [US3] turn.py and runner.py (research §4):
  - while talking, an answer that starts an intention elsewhere becomes a goodbye carrying that
    intention (`{"action": "goodbye", "text": null, "intention": …}`), and the runner ends the
    talk and takes the first step;
  - `_walks`: a villager with an intention walks while talking, and the talk ends when they walk
    apart;
  - remove `_to_meeting`; bedtime sets a go-home intention instead of its special case;
  - two talkers whose intentions go to the same place walk on together.

  Tests in test_village_runner.py:
  - the existing bedtime-walk and meeting-walk tests pass unchanged;
  - a move while talking leaves with a goodbye and never refuses;
  - a villager without an intention stays;
  - two villagers going to the market keep talking as they walk.

  Requirements: FR-009, FR-010.
- [X] T015 [P] [US3] backend/evals/checks/leave-talk-for-intention.json: Lina talking with Jonas
  at 10:55, with the plan entry "11:00 flower garden" (she is at the market). The expectation is
  `{"not": [{"action": "wait"}, {"action": "say"}]}`. Requirement: FR-014.

## Phase 6: User Story 4 — Memory that fades and fits the season (P3)

- [X] T016 [US4] backend/src/agent_lab/village/memory.py:
  - `score(memory, tick, names, place)` subtracts 3 when the memory's season (from its tick) is
    not the current one and `names` does not intersect its `about`;
  - `IMPORTANCE["summary"] = 4`.

  Tests in test_village_memory.py:
  - an autumn festival memory ranks below yesterday's of equal importance in summer;
  - a memory about someone at hand is not lowered.

  Requirement: FR-011.
- [X] T017 [US4] The summary.
  - `reflection_prompt` adds "Your older reflections:" when more than 5 reflections are older
    than 3 days, and asks for a `"summary"` field.
  - `parse_reflection` accepts `summary` (up to 400 characters).
  - The runner's `_reflect` replaces those reflections with one `summary` memory.
  - `REFLECT` gets one sentence about the field, with `OLD_REFLECT = (the M8 text,)`, and
    `_refresh_reflection` mirrors `_refresh_planner`.

  Tests: test_village_memory.py (the prompt, parsing) and test_village_runner.py (the fold, the
  refresh, an edited agent left alone). Requirement: FR-012.
- [X] T018 [P] [US4] backend/src/agent_lab/village/chronicle.py: `chronicle_prompt` appends
  "(talk, not the day's weather)" to notes whose text names weather the day did not have
  (`weather_slips(note, weather(day))`). Test in test_village_chronicle.py. Requirement:
  FR-013.
- [X] T019 [US4] backend/src/agent_lab/village/evals/checks.py: a new expectation
  `{"excludes": [words]}`, passing when the raw answer names none of them (case ignored). Also
  backend/evals/checks/summer-plan-without-festival.json: the planner, Greta, on summer day 66,
  with memories of last autumn's festival. The expectation is
  `{"excludes": ["festival"]}`. Tests in test_village_evals.py: the expectation, and the shipped
  check with an ideal answer. Requirement: FR-014.

## Phase 7: Polish

- [X] T020 Docs:
  - README.md: intentions and "what you can do here"; M14 done in the roadmap.
  - docs/village.md:
    - How a villager decides: the new answers and intentions;
    - Measuring: the new checks;
    - What's next: M15.
  - docs/api.md: the villager's `intention`.
  - AGENTS.md: `meeting_runs.py`, `intention.py` and `affordances.py` in the layout; the current
    feature.
- [X] T021 `make check`, then quickstart.md on the real model:
  - the checks at 20 repeats, compared with the M13 result;
  - the scenarios;
  - three village days on a scratch copy, with `evals health`;
  - the seasons of recalled memories in the prompts;
  - chronicle weather slips.

  Results go in a "Manual check results" section at the end of
  specs/014-better-villagers/tasks.md (SC-001–SC-006).

## Dependencies

| Task | Needs |
|---|---|
| T001 | – |
| T002 | T001 |
| T003 | T002 (uses the v7 world in tests); can be written alongside T002 |
| T004 | T002 |
| T005 | T004 |
| T006 | T005 |
| T007 | T003, T006 |
| T008 | T007 |
| T009 | T007 |
| T010 | T006 |
| T011 | T010 |
| T012 | – (after T007's observation change) |
| T013 | T010 |
| T014 | T006 |
| T015 | T014 |
| T016 | – (after Phase 2) |
| T017 | T016 |
| T018 | – (after Phase 2) |
| T019 | T017 |
| T020, T021 | last |

Stories in order:
- US1 is the base.
- US2 needs US1's see intention.
- US3 needs US1's intentions.
- US4 is independent of US2 and US3.

## Parallel opportunities

- T003 (affordances) alongside T004 (the intention module): different files, both pure.
- T016 and T018 (memory, chronicle) alongside US1–US3.
- The check files T009, T013 and T015 once their behaviour exists.

## Implementation strategy

- **MVP:** Phase 1–3. Intentions and "what you can do here" are where most refusals and waits
  should drop.
- **Then:** reaching each other, leaving talks, memory.
- **Last:** T021 measures everything against the M13 baseline, with the same instruments.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | test_village_intention.py; test_village_turn.py (new answers) |
| FR-002 | test_village_intention.py (steps); test_village_runner.py (no model calls for certain steps) |
| FR-003 | test_village_runner.py (done, given up, replaced, bedtime; events and notes) |
| FR-004 | test_village_turn.py (intention line, affordances); village.test.ts |
| FR-005, FR-006 | test_village_runner.py (follow, lost sight); test_village_turn.py (say from afar) |
| FR-007 | test_village_work.py, test_village_runner.py (requests, see target, reasons) |
| FR-008 | test_village_turn.py (names next to you and in sight); test_village_affordances.py |
| FR-009, FR-010 | test_village_runner.py (goodbye instead of refusal, walk together, bedtime and meeting tests) |
| FR-011 | test_village_memory.py (season weight) |
| FR-012 | test_village_memory.py, test_village_runner.py (summary fold, refresh) |
| FR-013 | test_village_chronicle.py |
| FR-014 | test_village_evals.py (new checks load and can be passed; `excludes`) |
| FR-015 | test_village_runner.py (rules refresh from M12) |
| FR-016 | test_village_world.py, test_village_runner.py (v6 loads, Reset) |
| FR-017 | all of the above; `make check` (T021) |

| SC | Check |
|---|---|
| SC-001, SC-006 | quickstart step 1 (real model, compare with M13) |
| SC-002 | quickstart step 2 |
| SC-003, SC-004, SC-005 | quickstart step 3 |

## Manual check results (2026-11-02, vLLM `qwen3.5-9b`, thinking off)

The owner's village was backed up (`agent_lab.db.bak-before-m14`), then upgraded to world version 7
by restarting `make dev` (day 67, 05:20, paused; nothing lost). The checks run against its
refreshed agents.

**Turn checks** (SC-001, SC-006). Run of record `58ee35f159d7`, 20 repeats each, compared with the
two M13 runs `c5183d25de1b` (A) and `9423c8be75d6` (B):

| Check | M13 A | M13 B | M14 | Compare |
|---|---|---|---|---|
| answer-when-spoken-to | 19/20 | 19/20 | 19/20 | no clear change |
| build-with-loads | 0/20 | 0/20 | 4/20 | no clear change (7/20, "better", in an earlier M14 run) |
| buy-saplings | 19/20 | 17/20 | 20/20 | no clear change |
| find-the-one-to-see | 15/20 | 14/20 | 14/20 | no clear change |
| load-at-site | 16/20 | 17/20 | 7/20 | **worse**, see below |
| load-away | 20/20 | 20/20 | 2/20 | **worse**, see below |
| meeting-call-far | 20/20 | 20/20 | 19/20 | no clear change |
| meeting-call-talking | 15/20 | 12/20 | 15/20 | no clear change |
| not-to-hilde | 20/20 | 20/20 | 20/20 | no clear change |
| plan-valid | 20/20 | 20/20 | 20/20 | no clear change |
| proposals-valid (frozen) | 17/20 | 19/20 | 18/20 | no clear change |
| stalls-in-autumn | 19/20 | 20/20 | 13/20 | worse than B only |
| work-at-own-place | 7/20 | 4/20 | 20/20 | **better** |
| work-plan-buys | 15/20 | 11/20 | 11/20 | no clear change |
| intention-keeps-building (new) | | | 20/20 | |
| say-to-someone-in-sight (new) | | | 15/20 | |
| leave-talk-for-intention (new) | | | 10/20 | below the 15/20 aimed for |
| summer-plan-without-festival (new) | | | 20/20 | |

- **The M13 load checks fail on M14's own answers.** The M13 checks stay unchanged, and they ask
  for M12's answer shapes. In `load-at-site`, 11 failures answer `build` (parsed as work at the
  site) and 1 answers `bring`; both set the load down at the site, so 19/20 do the right thing.
  In `load-away`, 14 failures answer `bring`, which takes the load there, so 16/20 do the right
  thing.
- **The first M14 run found three regressions, fixed before the run of record:**
  - at the site, the observation said "between places", because the removed hint had been the
    only line naming the site;
  - with the M11 autumn hint gone, villagers no longer set baskets out (`stalls-in-autumn` 4/20,
    now 13/20 with "the festival stalls still lack fish: set yours out now");
  - nothing offered finding the one a plan entry names (`find-the-one-to-see` 5/20, now 14/20).
  Talkers due elsewhere by their plan are now offered the leaving goodbye
  (`leave-talk-for-intention` 3/20, now 10/20).
- **Variance between runs is large**: `stalls-in-autumn` read 16, 12, 10 and 13 in four M14 runs.

**SC-001** is met for `work-at-own-place` only; `build-with-loads` (0 → 4 to 7) and
`meeting-call-talking` (15 and 12 → 15) are not clearly better. **SC-006** is not met as
measured: two M13 checks read worse, mostly because they accept only M12's answers, and
`stalls-in-autumn` is worse than one M13 run. Of the new checks, two reach 15/20 and two do not.

**Scenarios** (SC-002), 5 repeats each on fresh copies; the owner's village row checksum was the
same before and after (`a9975bc4`):

| Scenario | M13 | M14 run 1 | M14 run 2 |
|---|---|---|---|
| load-reaches-site | 5/5 | 0/5, miscounted | 5/5 |
| meeting-attendance | 5/5 | 5/5 | 4/5 |
| talk-then-go | 0/5 | 5/5 | 2/5 |

In run 1 Lina bought, brought and set the saplings down by 10:50 every time, but the condition
only counted `give` answers; it now reads the day's notes too (as does village health's
`loads_set_down`, and `load_minutes` from the trail). In the failed talk-then-go runs, Jonas met
Greta and left for the pier at once, as his plan said, so they never talked. Together
talk-then-go holds 7/10.

**Three village days** (SC-003 to SC-005) on a copy of the owner's database, days 67 to 69 (377 s
on vLLM), against the owner's days 43 to 66:

| Per 100 decisions | M13 | M14 |
|---|---|---|
| "there is no work for you here" | 6.0 | 1.5 |
| "<villager> is not next to you" | 7.0 | 3.7 |
| "you are talking with …; say goodbye first" | 6.9 | 0 |
| "<villager>'s hands are full" | 2.4 | 1.7 |
| waits | 44.3% | 28.4% |
| model calls per day | 155 to 206 | 162 to 172 |

- **SC-003**: the first and third refusals halve; "not next to you" falls by 47%, just short of
  half.
- **SC-004**: waits are well under 35%, and calls stay within the baseline's range.
- **SC-005**:
  - Out-of-season memories in plan prompts fell from 124 of 200 shown (days 64 to 66) to 4 of
    192.
  - None of the three chronicles named other weather; on the baseline days, 11 of 24 did.
  - The word "festival" is still in every plan prompt. It now comes from this summer's own
    learnings ("Hilde needs my fish … for the festival"): Hilde's persona plans a harvest
    festival year-round. That is for a persona change, not for memory.

**Found, not fixed**:
- `test_the_trail_keeps_28_days_and_reset_clears_it` (M13) failed once in `make check`
  (`born` not later after a Reset); it passed 6 of 6 reruns. Suspected cause, not confirmed:
  two `time.time()` calls returning the same value.
- Small models still answer `{"action": "walk"}`, `"go"` or `"home"` a few times a day.
- A few answers give "until" equal to the current time, and these are refused.

## After the cleanup (2026-11-02)

The cleanup changed four things:
- Hilde's persona no longer plans the festival all year; in autumn, her turns and plans say she
  organises it.
- "walk", "go" and "home" answers are read as a move.
- An `"until"` equal to now means no end time.
- New checks `load-at-site-m14` and `load-away-m14` use `"any_of"`, so M14's answers count too.

Your village's stored agents got the new persona on load. Two runs of 20 repeats
(`e33ccb2358cb`, `da6dc657e1a5`):

| Check | Run 1 | Run 2 |
|---|---|---|
| load-at-site-m14 | 18/20 | 16/20 |
| load-away-m14 | 15/20 | 16/20 |
| leave-talk-for-intention | 8/20 | 14/20 |
| stalls-in-autumn | 17/20 | 14/20 |
| build-with-loads | 8/20 | 4/20 |
| work-at-own-place | 16/20 | 19/20 |
| meeting-call-talking | 16/20 | 14/20 |
| overall | 70% | 69% |

The M13 trail test's flaky `born` comparison now starts from a fixed old value.
