---
description: "Task list for M15 — Daily Happenings and Boat Trips"
---

# Tasks: M15 — Daily Happenings and Boat Trips

**Input**: `specs/015-daily-happenings/` (plan.md, spec.md, research.md, data-model.md,
contracts/interfaces.md, quickstart.md)

**Tests**: requested by the spec (FR-016). `FakeLLM` only, and the failing test is written
first. Runner tests pass `move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **Your village stays safe.** Stop `make dev` and back up `backend/data/agent_lab.db` (sqlite
  backup API) before the store, world or runner change. The world-version bump, `upgrade` and
  `_load` change in one write (memory note `dev-reload-resets-village`).
- **Rules change in steps.** The rules advertise only what the parser accepts. Each change to
  `RULES` moves the replaced text into `OLD_RULES`, starting with the M14 text as `_M14_RULES`.
- **No model calls for happenings or the boat.** Happenings and the boat move by fixed rules.
  Every happening start and end, trip and whisper is an event plus a day-record note.
- **The earlier checks stay as they are.** The M13 and M14 checks are never edited; they are the
  baseline.

---

## Phase 1: Setup — the mixin

- [X] T001 Create backend/src/agent_lab/village/happening_runs.py with an empty `class
  HappeningRuns`, a mixin declaring what it uses from `Village`, and make `Village(MeetingRuns,
  HappeningRuns)` in backend/src/agent_lab/village/runner.py.
  - Attributes: `world`, `store`, `resetting`.
  - Stubs: `_event`, `_note`, `_trigger`, `_remember`, `_villager`, `_publish`, `_aim`,
    `_end_intention`, `_say`.
  - No behaviour change; `make check` passes unchanged.
  - Requirement: plan, constitution I.

## Phase 2: Foundational — world version 8

- [X] T002 World version 8.
  - backend/src/agent_lab/village/world.py:
    - `VERSION = 8`;
    - `happenings: []`, `boat: None` and `harvest.lake: 0`;
    - per villager `keepsakes: []` and `whispers: []`;
    - `upgrade()` 7 → 8.
  - runner.py:
    - `_load` accepts 2–7;
    - Reset clears all of it;
    - `state()` sends `happenings`, `boat` and the villagers' `keepsakes`, and leaves out
      `whispers`.
  - Tests in test_village_world.py: the shape, a v7 world upgraded.
  - Tests in test_village_runner.py: a v7 world loads and keeps going; Reset; the state.
  - Requirement: FR-015.

## Phase 3: User Story 1 — Daily happenings (P1) 🎯 MVP

- [X] T003 [P] [US1] New backend/src/agent_lab/village/happenings.py (research §1–§3,
  data-model.md "Happening").
  - `CATALOGUE`: per kind, short fixed lists written for the four villagers:
    - letters' news, 2–3 per villager;
    - visitors with name, relation and host;
    - animals with their owners;
    - repairs at the fields, the pier or the flower garden;
    - curiosities.
  - `day_happenings(day)`:
    - `random.Random(f"happenings {day}")`;
    - one happening, or two with a 40% chance, never two of a kind;
    - windows as in research §1: letter 08:00 at the addressee's door, visitor 13:00–19:00,
      animal 09:00–19:00, repair from waking to the end of the day, peddler 10:00–15:00 at the
      square;
    - nothing but the visitor past 16:30 on a meeting day, and no peddler on the festival day.
  - `step(world, minute) -> list[change]`:
    - coming → here at start;
    - an animal follows its leader, and a visitor its host once met (`with_host` += 1 while
      next to the host);
    - here → passed at end, or at the day's end;
    - dealt: a letter when its addressee stands at its door; a visitor after 6 steps with the
      host.
  - `noticed(world, v)`: the happenings `v` sees now and has not been told of.
  - `happening_text(h, name)`: the fact as seen, or as the concerned one is told.
  - `lead_refusal(world, name)`.
  - `repair_at(world, place)`.

  Tests in new backend/tests/test_village_happenings.py:
  - the same day gives the same happenings, and 200 days each give 1–2 of different kinds;
  - the meeting and festival rules;
  - every kind through every state;
  - noticing within sight only, once each.

  Requirements: FR-001, FR-002, FR-004.
- [X] T004 [US1] work.py and trade.py.
  - Work at a place with an open repair goes into its `work` first; 6 steps mend it (dealt by
    the longest worker).
  - While it is open, a basket there takes `2 * BASKET_STEPS`.
  - `buy_refusal`, with the peddler here at the square, accepts its curiosity for a basket. The
    villager gains a keepsake `{name, day}` and loses the basket; the hands stay empty.

  Tests in test_village_work.py and test_village_trade.py. Requirements: FR-003, FR-005.
- [X] T005 [US1] turn.py and intention.py.
  - New `Lead` answer, `{"action": "lead"}`, refused unless an animal is next to the villager
    and nobody leads it yet ("nobody leads it" / "Jonas already leads it").
  - The intention kind `lead` goes to the owner's door. It is done when there, or when the
    owner is next to the villager.
  - The observation gets:
    - "Happening here: …" facts for what the villager sees;
    - concerned lines ("A letter waits for you at home.");
    - its keepsakes in the facts ("You keep: a lantern.").
  - `RULES` gains `lead`, and the M14 text joins `OLD_RULES`.

  Tests in test_village_turn.py and test_village_intention.py. Requirements: FR-002, FR-003,
  FR-014.
- [X] T006 [US1] affordances.py:
  - `{"action": "lead"}`: "Greta's goat is next to you; take it home";
  - `{"action": "work"}` at a broken place: "mend the boards of the pier";
  - `{"action": "buy", "goods": "lantern"}`: "the peddler trades it for your basket".

  Tests in test_village_affordances.py; every listed answer passes `parse_action`. Requirement:
  FR-003.
- [X] T007 [US1] happening_runs.py and runner.py:
  - `_open_happenings(day)` sets the day's list when the day record opens (yesterday's goes);
  - `_happenings()` in `_advance`, after the moves and before work, applies `step` and
    `noticed`:
    - events `happening`, with the trigger `happening` for the seen;
    - the concerned are told at start (trigger);
    - notes at start and end ("A goat wandered to the market.", "Lina led Greta's goat home.",
      "The peddler left the square; nobody traded.");
    - memories for whoever dealt with it (kind `happening` importance 3, `keepsake` importance
      3);
  - `_apply` handles `lead` (an intention with the animal following);
  - the letter's news becomes an event and a memory for its addressee when read.

  Tests in test_village_runner.py, scripted:
  - a goat led home by one answer;
  - a fence mended by work;
  - a curiosity traded;
  - a letter read at home with its news in the next prompt;
  - a visitor following the host and leaving at 19:00;
  - a happening passing unhandled.

  Requirements: FR-001–FR-005.
- [X] T008 [P] [US1] chronicle.py: `chronicle_prompt` opens the events with "Today: …", naming the
  day's happenings and how they ended. Test in test_village_chronicle.py. Requirement: FR-004.
- [X] T009 [US1] Frontend:
  - lib/api.ts: `Happening`, `keepsakes`, event kinds `happening`, the `lead` action;
  - lib/village.ts: `happeningText`, `turnLabel` for lead;
  - components/village/pixels.tsx: figures for the postman (during the letter's half hour), the
    visitor (next to the host or at the door), the animal, the peddler, and a mark on a broken
    place;
  - VillagerPanel.tsx: the keepsakes.

  Tests in village.test.ts and pixels.test.ts (figure positions as pure functions). Requirement:
  FR-002.
- [X] T010 [P] [US1] Five checks in backend/evals/checks/:
  - `animal-lead`;
  - `repair-mend`;
  - `peddler-curiosity`;
  - `letter-pass-on`;
  - `visitor-host`.

  Fixtures gain a `happenings` key (backend/src/agent_lab/village/evals/fixtures.py: kind,
  place, concerns, details, state `here`). Each check gets an ideal answer in
  test_village_evals.py. Requirement: FR-013.

## Phase 4: User Story 2 — Boat trips (P2)

- [X] T011 [P] [US2] New backend/src/agent_lab/village/boat.py (research §5, data-model.md
  "Boat trip").
  - `LOOP`: lake cells from the pier and back, all water.
  - `row_refusal(world, name, with_)`. Refused when:
    - the boat is not built: "the village has no boat";
    - it is out: "the boat is out with Jonas";
    - there is a storm: "no boat trips in a storm";
    - the villager is not at the pier: "the boat lies at the pier";
    - `with_` is not next to it.
  - `boat_step(world, minute)`:
    - boarding waits 2 steps for the one invited;
    - out moves one LOOP cell a step;
    - back at `back` or the bedtime of the first rower to sleep.
  - `boat_text(world, name)`.

  Tests in new backend/tests/test_village_boat.py. Requirements: FR-006, FR-008.
- [X] T012 [US2] turn.py, intention.py and work.py.
  - `Row {with?, until?}`. Validate `with` as an adjacent awake villager. `until` follows the
    M14 rules, and the trip lasts an hour without it. An invited villager answering `row`
    while the boat is boarding joins.
  - The intention kind `row` lasts until the trip ends.
  - `lake` in GOODS (fish) with `BASKET_STEPS // 2`, worked from the boat.
  - Affordances: `{"action": "row"}` at the pier when it would be accepted, and `"with"` the
    villager next to it.

  Tests in test_village_turn.py, test_village_work.py and test_village_affordances.py.
  Requirements: FR-006, FR-007.
- [X] T013 [US2] happening_runs.py and runner.py.
  - `_row` and `_boat()`:
    - boarding, then out, with the rowers placed on the boat's cell, not walking (`_walks`);
    - back to the pier cells with notes and memories (kind `boat` importance 4: "A boat trip on
      the lake with Greta.");
    - events `rowed` / `invited` and the trigger `invited`.
  - `_upkeep` keeps a talk between rowers from falling silent while out.
  - Bedtime brings the boat back first.

  Tests in test_village_runner.py, scripted:
  - a trip alone, out and back after an hour;
  - a trip together after an invitation and its acceptance;
  - an invitation not taken (the boat leaves alone);
  - a second villager refused while out;
  - fishing from the boat fills a basket in 3 steps;
  - the talk lasts the trip;
  - bedtime returns the boat.

  Requirements: FR-006–FR-008.
- [ ] T014 [US2] Frontend:
  - lib/api.ts: the boat type, the `row` action, the `rowed` / `invited` events;
  - lib/village.ts: `boatCells`, `turnLabel` for row;
  - pixels.tsx: the boat drawn at its cell with its rowers (at the pier when null and built),
    respecting reduced motion as the walkers do.

  Tests in village.test.ts and pixels.test.ts. Requirement: FR-009.
- [ ] T015 [P] [US2] Check `take-the-boat` and scenario `boat-trip`:
  - backend/evals/checks/take-the-boat.json;
  - backend/evals/scenarios/boat-trip.json;
  - the condition `boat_trip` in backend/src/agent_lab/village/evals/scenarios.py, held when a
    trip happens by the horizon and noting "together" or "alone".

  Tests in test_village_evals.py. Requirement: FR-013.

## Phase 5: User Story 3 — Whispers (P3)

- [ ] T016 [US3] happening_runs.py, runner.py and api.py.
  - `whisper(name, text)`:
    - stripped text, 1–200 characters ("a whisper is at most 200 characters");
    - at most 3 per villager per village day ("Greta already heard 3 whispers today");
    - awake: the inbox entry `{"from": "a voice", …}`, the event `whispered`, the trigger
      `whispered` and the note "A voice whispered to Greta.";
    - asleep: kept with `heard: null` and delivered on waking.
  - `_decide` adds `"after_whisper": true` to the action when the trigger was among the
    decision's reasons.
  - `POST /village/villagers/{name}/whisper` answers `{"heard": bool}`: 404 for an unknown
    villager, 422 for empty or too long text, 409 at the limit.
  - The observation shows `- a voice: "…"` among what was said to it.

  Tests in test_village_runner.py, test_village_turn.py and test_village_api.py.
  Requirements: FR-010, FR-011.
- [ ] T017 [US3] Frontend:
  - lib/api.ts: `whisper(name, text)`, the `whispered` event, `after_whisper`;
  - lib/village.ts: `turnLabel` adds " (after a whisper)";
  - VillagerPanel.tsx: a whisper box with a 200-character limit and a counter, sending on
    Enter, and showing "heard" or "will hear it on waking", or the refusal.

  Tests in village.test.ts. Requirements: FR-010, SC-004.

## Phase 6: Measuring

- [ ] T018 health.py:
  - `happenings: {count, dealt}` from the day's notes;
  - `boat_trips` from notes;
  - `whispers: {count, followed}`: notes, and decision runs with `after_whisper` whose action
    is not wait.

  frontend lib/health.ts and HealthPanel show them. Tests in test_village_health.py and
  health.test.ts. Requirement: FR-012, FR-013.

## Phase 7: Polish

- [ ] T019 Docs:
  - README.md: M15 done in the roadmap; happenings, boat trips and whispers in the village line;
  - docs/village.md: happenings, the boat, whispers, the new checks; What's next: M16 MCP;
  - docs/api.md: the whisper endpoint and the new state fields;
  - AGENTS.md: `happenings.py`, `boat.py` and `happening_runs.py` in the layout; the current
    feature.
- [ ] T020 `make check`, then quickstart.md on the real model:
  - the checks at 20 repeats, compared with the M14 run of record `58ee35f159d7`;
  - the scenarios;
  - seven village days on a copy, with `evals health`;
  - the chronicles read;
  - a whisper in the running village.

  Results go in a "Manual check results" section at the end of this file (SC-001–SC-006).

## Dependencies

| Task | Needs |
|---|---|
| T001 | – |
| T002 | T001 |
| T003 | T002 (can be written alongside it: pure) |
| T004 | T003 |
| T005 | T003 |
| T006 | T004, T005 |
| T007 | T004–T006 |
| T008 | T003 |
| T009 | T007 |
| T010 | T007 |
| T011 | T002 |
| T012 | T011 |
| T013 | T012 |
| T014 | T013 |
| T015 | T013 |
| T016 | T002 |
| T017 | T016 |
| T018 | T007, T013, T016 |
| T019, T020 | last |

The user stories depend on each other only through the shared files:
- **US1** happenings is the MVP.
- **US2** the boat and **US3** whispers need only Phase 2. They can follow in either order.

## Parallel opportunities

- **Pure modules**: T003 (happenings) and T011 (the boat).
- **Small edits in separate files**: T008 (the chronicle) next to T004–T007.
- **Check files**: T010 and T015, once their behaviour exists.
- **Whispers**: US3 (T016–T017) can be built in parallel with US2.

## Implementation strategy

- **MVP**: Phases 1–3. Days that differ from each other are the point of the milestone.
- **Then**: the boat, then whispers.
- **Last**: T018 measures what is new, and T020 checks the M14 numbers hold.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | test_village_happenings.py (seeded, 1–2, different kinds, windows) |
| FR-002 | test_village_happenings.py (noticing); test_village_turn.py (observation lines); village.test.ts, pixels.test.ts |
| FR-003 | test_village_turn.py (lead), test_village_work.py (mend), test_village_trade.py (curiosity), test_village_affordances.py |
| FR-004 | test_village_runner.py (ends, notes); test_village_chronicle.py ("Today: …") |
| FR-005 | test_village_work.py (slower baskets, keepsake not carried) |
| FR-006 | test_village_boat.py, test_village_runner.py (alone, together, invitation) |
| FR-007 | test_village_work.py (lake basket), test_village_runner.py (talk lasts, memories) |
| FR-008 | test_village_boat.py (refusals), test_village_runner.py (bedtime) |
| FR-009 | pixels.test.ts (boat drawn with rowers) |
| FR-010 | test_village_runner.py, test_village_api.py (limits, refusals) |
| FR-011 | test_village_runner.py (claim in inbox, decision, on waking) |
| FR-012 | test_village_health.py (whispers count and followed) |
| FR-013 | test_village_evals.py (six checks, boat scenario, condition); test_village_health.py |
| FR-014 | test_village_runner.py (rules refresh from M14) |
| FR-015 | test_village_world.py, test_village_runner.py (v7 loads, Reset) |
| FR-016 | all of the above; `make check` (T020) |

| SC | Check |
|---|---|
| SC-001, SC-006 | quickstart step 3 (seven days, chronicles) |
| SC-002, SC-005 | quickstart step 1 (checks, compare with M14) and step 3 (waits, calls) |
| SC-003 | quickstart step 2 |
| SC-004 | quickstart step 4 |
