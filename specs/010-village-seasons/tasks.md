---
description: "Task list for M10 — Village Seasons"
---

# Tasks: M10 — Village Seasons

**Input**: `specs/010-village-seasons/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-020, SC-001–SC-004). `FakeLLM` only; answers come from
callables that tell decisions, reflections and chronicles apart by the system prompt (the
chronicler's prompt must not contain `"learnings"`, which marks a reflection). Runner tests
pass `move_gap=0`. A scripted year is tested on `end_day` directly (28 calls), not by running
4,032 steps.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- The chronicler is an ordinary run of the shared chronicler agent through `runs.new_run` /
  `runs.execute_run` via `Village._run(agent_id, None, prompt, tick)`; the village never calls the
  model itself; its answer is validated, never executed, and redacted after decoding.
- Calendar, weather, sky and snow cover are derived from the day (research §2), never stored.
- New drawings live in `components/village/seasons.tsx`; new keyframes stop under
  `prefers-reduced-motion`; decorations use `pointer-events: none`.

---

## Phase 1: Foundational — calendar, weather and world version 4

- [ ] T001 New backend/src/agent_lab/village/seasons.py (research §2): `SEASONS = ("spring", "summer", "autumn", "winter")`, `DAYS_PER_SEASON = 7`, `date(day) -> (year, season, day_of_season)`, `festival_in(day)` ("days until autumn day 7 while in autumn, 0 on the day, else None"), `SUN` per season (spring 06:00–20:00, summer 05:00–21:30, autumn 06:30–19:00, winter 08:00–17:00), `sky(day, minute)` (the five existing keys shifted by the season), `dark(day, minute)`, `WEATHER` weights per season and for the festival day ("sun 1 · clouds 1"), `weather(day)` via `random.Random(day).choices`, `snow_cover(day)` (snow today or yesterday), `WEATHER_TEXT`; world.py: `VERSION = 4`, `new_world()` adds `growth` (fields `{stage: "resting", progress: 0, untended: 0}`, flower_garden `{stage: "budding", watered: 0, dry: 0}`), `tended` `{fields: 0, flower_garden: 0}`, `day_record: None`, `festival: None`, `chronicle: []`, `chronicler_agent_id: None`; `upgrade()` chains 2 → 3 → 4 with growth from the season (data-model.md "Upgrade from version 3"); runner.py `_load` upgrades versions 2 and 3; `state()` adds `calendar {year, season, day_of_season, festival_in}`, `weather`, `snow_cover`, `sky`, `dark` and drops the internal fields (contracts/http-api.md); tests in new backend/tests/test_village_seasons.py (day 1/8/15/22/29 dates, festival countdown, sky and dark per season, every day of two years has one allowed weather and the same on a second call, festival weather sun or clouds, snow cover) and test_village_world.py / test_village_runner.py (new world shape, a version-3 and a version-2 world load and keep going, state fields)

## Phase 2: User Story 1 — Three paces (P1) 🎯 MVP

- [ ] T002 [P] [US1] frontend/src/lib/village.ts: `PACES` (Slow 15, Normal 5, Fast 2), `paceOf(interval)` (null for other values), `statusLine(state)` "Running at Normal pace" ("Running, a step every 7 s" when no pace matches; stepping and paused texts unchanged); frontend/src/components/village/VillageView.tsx: three toggle buttons with `aria-pressed` replace the seconds field and call `setVillageInterval`; tests in frontend/src/lib/village.test.ts (paces, `paceOf` for 15/5/2/7, `statusLine` running at a pace, at an unmatched interval, stepping and paused); backend test in test_village_runner.py that the running loop waits the interval between steps while someone is awake (scaled to 0.05 s) and keeps `NIGHT_STEP` while everyone sleeps (the existing night test covers the latter); backend test in test_village_api.py that changing the interval leaves every villager agent's model unchanged (SC-001, FR-002)

## Phase 3: User Story 2 — The village chronicle (P1)

- [ ] T003 [P] [US2] New backend/src/agent_lab/village/chronicle.py (research §6): `CHRONICLE_KEPT = 28`, `chronicle_prompt(world, record)` (the record's day as "Day 17, day 3 of autumn, year 1", that day's weather, the places' states, the items), `parse_entry(answer) -> (entry | None, reason)` ("`title` and `text` non-empty strings; title cut to 60, text to 800"), `chronicler_agent()` (block agent "Village chronicler": model block `chronicle` + check `answer-is-json`); tests in new backend/tests/test_village_chronicle.py: the prompt lists date, weather and items; every valid and invalid answer; the agent validates as a block agent
- [ ] T004 [US2] backend/src/agent_lab/village/runner.py: `_note(text)` ("texts cut to 300, at most 120 items"), day record opened in `_schedule` at the first waking when none is open, notes from `_look` (first meeting of a pair that day, found, missed), `_end_conversation` (once per conversation, with the transcript), `_set_off`, goodbye; `_fall_asleep` closes the record and starts `_chronicle` when everyone sleeps; `_chronicle` runs the agent, appends `{day, year, season, day_of_season, weather, title, text, run_id}` (≤ 28, oldest dropped), sets `village_action` `{"action": "chronicle", "title"}` or `{"action": "chronicle", "reason"}`, publishes; `_settle` waits for it; failures never reach `outcomes`; `ensure_agents` creates the chronicler once and Reset keeps `chronicler_agent_id` (recreated if deleted); `state()` sends `chronicle` newest first; tests in test_village_runner.py: one chronicle per night over 7 scripted days (SC-004), the entry carries the record's day and weather when the last villager falls asleep after midnight (US2 scenario 2), invalid answers add none and record the reason, a failing chronicle does not pause the village, Step and Reset wait for it, reset clears the chronicle, at most 28 kept, the agent created once and listed
- [ ] T005 [US2] frontend/src/lib/api.ts (`chronicle`, `VillageAction` `chronicle`), lib/village.ts (`newEntries(chronicle, seenRunId)` — all when the id is missing; `turnLabel` "writes the chronicle of day 3" or the reason), new frontend/src/components/village/ChroniclePanel.tsx (entries newest first with day, season and weather; new ones marked; opening stores the newest run id in `localStorage` inside try/catch; each entry opens the run that wrote it via `GET /runs/{run_id}` and the existing turn view, because the run list leaves out village runs), VillageView.tsx (a Chronicle button with the count of new entries); tests in village.test.ts; screenshot at 1400 × 950

## Phase 4: User Story 3 — Seasons and weather (P2)

- [ ] T006 [US3] backend/src/agent_lab/village/turn.py: first observation line "Day 17 (day 3 of autumn, year 1), 09:40, morning. Rain all day." with `WEATHER_TEXT`; tests in test_village_turn.py for each season and weather kind (FR-010)
- [ ] T007 [US3] New frontend/src/components/village/seasons.tsx: season palettes for grass and trees (spring blossom, summer green, autumn gold/orange/red per tree position, winter bare), snow cover, `Weather` (rain ≈ 40 streaks and grey tint, `Puddles` on path cells, storm with lightning flashes, fog bands, snow ≈ 40 flakes, cloud shadows), `WeatherIcon`; pixels.tsx `Ground` and trees take season and snow cover, butterflies only spring/summer without rain, fireflies not in winter; lib/village.ts `calendarText` ("Day 3 of autumn, year 1") and the sky from `state.sky`; VillageView.tsx calendar line with weather icon, lamps and windows from `state.dark`; globals.css keyframes off under reduced motion; tests in village.test.ts (`calendarText`, sky key); screenshots of each season and weather by day and night (SC-005)

## Phase 5: User Story 4 — Fields and flowers that grow from work (P2)

- [ ] T008 [P] [US4] seasons.py (research §3, data-model.md "State transitions"): `end_day(world, day) -> list[str]` (tended = "`tended >= 6`"; fields: tilled, sown, then progress "+2 on rain or storm, else +1" with thresholds 3 / 5 / 6, harvest on a tended autumn day when ripe, `untended` counting; garden: watered = tended or rain or storm, "2 watered days → blooming", "2 dry days → wilting", watered revives; then the new day: first of winter rests both and loses ripe fields, first of spring buds the garden; returns the notes), `neglected(growth)` ("sprouting, growing or ripe with `untended >= 2`"), `growth_text(place, growth)`; tests in test_village_seasons.py: a scripted year tended daily without rain harvests on day 17 before the festival, never tended stays resting, rain doubles progress, neglect after 2 untended days and cleared by a tended day, ripe lost at winter, garden wilts after 2 dry days, recovers on rain, blooms when visited on dry days, winter tending does nothing (SC-003)
- [ ] T009 [US4] runner.py: after the moves of each step, `tended[place] += 1` for the fields and the garden when an awake villager stands on it; at midnight `end_day` and its notes into the day record, `tended` reset; turn.py place lines for a villager on the place, with a cell of it in sight, or working there ("The fields are sprouting; nobody has tended them for 2 days."); `state()` `growth {fields: {stage, neglected}, flower_garden: {stage}}`; tests in test_village_runner.py (counting only awake villagers, the midnight update, notes in the record) and test_village_turn.py (who is told)
- [ ] T010 [US4] seasons.tsx: field stages (resting, tilled, sown, sprouting, growing, ripe, harvested) and weeds, garden states (resting, budding, blooming, wilting); pixels.tsx and VillageView.tsx draw them from `state.growth`; screenshots of each stage (SC-005)

## Phase 6: User Story 5 — The harvest festival (P3)

- [ ] T011 [US5] world.py `usual_place(name, tick)` (festival day from 18:00: the square for every awake villager), callers in turn.py and runner.py; turn.py festival lines ("in N days", "today, this evening on the square", "on now"); memory.py `IMPORTANCE["festival"] = 5`; runner.py guests recorded in `world["festival"]` each festival-evening step, a festival memory naming the other guests when a guest's bedtime starts, a note in the day record; tests in test_village_turn.py and test_village_runner.py (countdown days 1–6, today, on now, usual place, memory only for guests, not on other days)
- [ ] T012 [US5] seasons.tsx `Festival`: bunting across the square and lanterns at its corners, lit when dark, on the festival day; screenshot by day and night

## Phase 7: Polish

- [ ] T013 README.md (seasons, weather, growth, festival, chronicle, paces), AGENTS.md (`seasons.py`, `chronicle.py` in the layout; the chronicler in the village contracts)
- [ ] T014 `make check`; quickstart manual steps on the real model with results recorded below (SC-006, SC-007)

## Dependencies

T001 → everything backend. T002 is independent (frontend only). T003 ∥ T001; T004 needs T001 and
T003; T005 needs T004. T006 and T007 need T001. T008 needs T001; T009 needs T004 (day record) and
T008; T010 needs T009. T011 needs T004 and T006; T012 needs T007. T013 → T014 last.

## Parallel opportunities

- T002 (frontend) alongside T001 / T003 (backend).
- T003 (`chronicle.py`) alongside T001 (`seasons.py`, `world.py`).
- T008 (`seasons.py` growth rules) alongside T005–T007.

## Implementation strategy

MVP: Phase 1 + Phase 2 (paces) + Phase 3 (chronicle) — the owner can leave the tab open and catch
up. Then seasons and weather, growth, the festival; each phase is shippable on its own.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | village.test.ts (paces); T002 |
| FR-002 | test_village_api.py (models unchanged) |
| FR-003, FR-004, FR-005 | test_village_runner.py (record, once per night, after midnight, invalid, not a failure, Step/Reset); test_village_chronicle.py |
| FR-006 | village.test.ts (`newEntries`); T005 screenshot (an entry opens its run) |
| FR-007, FR-008 | test_village_seasons.py (dates, weather) |
| FR-009 | T007 screenshots; test_village_seasons.py (sky, dark, snow cover) |
| FR-010 | test_village_turn.py (first line) |
| FR-011, FR-012, FR-013, FR-015 | test_village_seasons.py (scripted year, garden, neglect, winter) |
| FR-014 | test_village_turn.py (place lines); T010 screenshots |
| FR-016, FR-017 | test_village_turn.py, test_village_runner.py (festival); T012 screenshots |
| FR-018 | test_village_runner.py (version 2 and 3 load, reset) |
| FR-019 | CSS reduced motion; `pointer-events: none`; T007/T010/T012 |
| FR-020, FR-021 | T001–T012 tests; `make check` (T014) |

| SC | Test / check |
|---|---|
| SC-001 | village.test.ts; test_village_runner.py (loop timing); test_village_api.py; quickstart step 1 |
| SC-002 | test_village_seasons.py |
| SC-003 | test_village_seasons.py |
| SC-004 | test_village_runner.py |
| SC-005 | T007, T010, T012 screenshots |
| SC-006 | quickstart step 2 (real model) |
| SC-007 | quickstart step 5 (real model) |

## Manual check results

(filled in by T005, T007, T010, T012 and T014)
