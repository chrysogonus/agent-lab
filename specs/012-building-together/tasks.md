---
description: "Task list for M12 — Building Together"
---

# Tasks: M12 — Building Together

**Input**: `specs/012-building-together/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-018, SC-001–SC-003).
- `FakeLLM` only. The shared responder in `test_village_runner.py` tells decisions, reflections,
  chronicles, plans and the four meeting prompts apart by the prompt.
- Runner tests pass `move_gap=0`.
- Every task writes its failing test first.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **Meeting runs** (proposals, votes, decisions, work plans) are ordinary runs of the shared
  "Village meeting" agent through `Village._run(agent_id, name, prompt, tick)`, like plans and
  reflections:
  - the village never calls the model itself;
  - answers are validated, never executed, and redacted after decoding;
  - meeting runs never reach `outcomes`, never count as decisions or toward the failure pause,
    and are waited for by `_settle` (Step and Reset).
- **Rules advertise only what the parser accepts.**
  - T005 adds buy, T010 adds the meeting sentence, and T017 adds the building site.
  - `_refresh_rules` replaces a rules text only when it finds it verbatim. So each edit moves the
    text it replaces into `OLD_RULES`, starting with the M11 text as `_M11_RULES`. No village
    loaded between phases is stranded.
- **The carried thing stays `v["basket"]`.**
  - It holds basket goods (`fish`, `vegetables`, `flowers`) or loads (`wood`, `paint`,
    `saplings`).
  - Every text naming it uses `carried_text(goods)`: "a basket of fish" or "a load of wood".
- **Drawings** of the trader, plots, sites and finished projects go in the new
  `frontend/src/components/village/building.tsx`. Decorations use `pointer-events: none` and have
  no animation.

---

## Phase 1: Foundational — world version 6, the map plots and the catalogue

- [X] T001 backend/src/agent_lab/village/world.py (research §3, §7; data-model.md "Map", "Upgrade from version 5", "Reset"):
  - `ROWS` gains plot `b` at 14–17 × 13–14 and plot `r` at 9–12 × 17–18, and `BLOCKED` adds `b` and `r`.
  - `VERSION = 6`; `new_world()` adds `trader: None`, `meeting: None`, `project: None`, `built: []` and `meeting_agent_id: None`.
  - `upgrade()`:
    - the version 4 → 5 step becomes explicit (today it runs unconditionally at the end);
    - a new 5 → 6 step adds the fields above;
    - "a villager standing on a new plot cell moves to that plot's first site cell": plot `b` → (14, 12), plot `r` → (10, 16), kept in world.py as `PLOT_EXITS` so `upgrade()` needs no catalogue.
  - runner.py `_load` accepts versions 2–5.
  - Reset keeps `reflection_agent_id`, `chronicler_agent_id`, `planner_agent_id` and `meeting_agent_id`, and clears `built`.
  - `state()` leaves out `meeting_agent_id`.
  - Tests in test_village_world.py:
    - the new world shape;
    - a version-5 world upgrades with the fields above;
    - a villager on a plot cell is moved off it;
    - every walkable cell is reachable from every other with the plots blocked.
  - Tests in test_village_runner.py:
    - a version-5 and a version-2 world load and keep going;
    - Reset clears `built` and keeps the four agent ids.
  - Requirement: FR-017.
- [X] T002 [P] New backend/src/agent_lab/village/build.py, the catalogue part only (research §3, data-model.md "Catalogue"):
  - `CATALOGUE`: the ten entries `{key, name, kind, needs, site, at, done_text}` from research §3's table, with the bakehouse at "wood 14, paint 3" and the barn at "wood 16, paint 3".
  - `entry(key)`;
  - `project_named(text) -> key | None` (by name or key, case and a leading "the" ignored);
  - `new_project(key, day)` → `{key, site: {wood: 0, paint: 0, saplings: 0}, used: {wood: 0, paint: 0, saplings: 0}, work: 0, tasks: [], day}`;
  - `buildable(world)` (catalogue order, not built, not the current project);
  - `built_text(world)` ("Built so far: …").
  - Tests in new backend/tests/test_village_build.py:
    - every site cell is walkable;
    - every building's needs sum to at least 17 (more than the longest waking day of 16 hours, Jonas 05:00–21:00);
    - `project_named` with names, keys, "the" and nonsense;
    - `buildable` skips built and current projects.
  - Requirement: FR-013.
- [X] T003 [P] New backend/src/agent_lab/village/trade.py, carried things only (research §2), and backend/src/agent_lab/village/work.py:
  - `BASKET_GOODS = ("fish", "vegetables", "flowers")`, `BUILDING_GOODS = ("wood", "paint", "saplings")`, `carried_text(goods)`.
  - work.py's events, notes, `delivery_text`, the observation's "You carry …" line and the plan prompt use `carried_text`.
  - `give_refusal` without a name on the square refuses loads with "the festival stalls take fish, vegetables and flowers".
  - In autumn `delivery_text` speaks only of basket goods.
  - Tests in new backend/tests/test_village_trade.py (`carried_text` for both kinds) and test_village_work.py (a load refused on the stalls, a load given to a villager).
  - Requirement: FR-002.

## Phase 2: User Story 1 — The daily trader (P1) 🎯 MVP

- [X] T004 [P] [US1] backend/src/agent_lab/village/trade.py (research §1):
  - `TRADER_ARRIVES = 9 * 60`, `TRADER_LEAVES = 14 * 60`.
  - `trader_stock(day)`: `random.Random(f"trader {day}")`, wood 2–6, paint 1–3, saplings 0–3, the same every time the day comes.
  - `trader_due(world) -> "arrive" | "leave" | None`:
    - arrive at the first step of a day whose minute is in `[09:00, 14:00)` without that day's trader, including after a load mid-window;
    - leave at the first step at or after 14:00.
  - `buy_refusal(world, name, goods)` → reason or `None`, in this order:
    1. "the trader sells wood, paint and saplings";
    2. "no trader is at the market now; one comes every day from 09:00 to 14:00";
    3. "the trader is at the market";
    4. "the trader has no paint left";
    5. "you have nothing to trade: bring a basket";
    6. "you already carry a load of wood".

    Buying while talking is allowed.
  - `trader_text(world)` ("A trader comes to the market today from 09:00 to 14:00." / "A trader is at the market until 14:00, selling wood (4), paint (2) and saplings (1); it takes one basket of fish, vegetables or flowers for each load." / "The trader has left; the next one comes tomorrow at 09:00.").
  - Tests in test_village_trade.py:
    - the same stock for the same day and within the ranges;
    - `trader_due` at 08:50, 09:00, mid-window after a load, 13:50 and 14:00;
    - every refusal in order;
    - the three texts.
  - Requirements: FR-001, FR-002, FR-003.
- [X] T005 [US1] backend/src/agent_lab/village/turn.py:
  - a `Buy` action `{"action": "buy", "goods"}`; `parse_action` refuses with `buy_refusal`, otherwise returns `{"action": "buy", "goods", "paid": <the basket goods>}`.
  - The facts part adds `trader_text`.
  - `RULES` adds buy ('{"action": "buy", "goods": "wood"} at the market while the trader is there: your basket for a load'), and the M11 text moves into `OLD_RULES` as `_M11_RULES`.
  - plan.py `plan_prompt` adds `trader_text`.
  - Tests in test_village_turn.py:
    - buy valid, and refused for each reason;
    - "paid" names the basket;
    - the trader line before, during and after.
  - Tests in test_village_runner.py: an agent holding the M11 rules gets the new ones; an edited prompt is left alone.
  - Requirements: FR-002, FR-003, FR-016.
- [X] T006 [US1] backend/src/agent_lab/village/runner.py:
  - `_trader()` in `_advance` before the moves:
    - arrival sets `world["trader"] = {day, stock}` with the note "A trader came to the market with wood (4), paint (2) and saplings (1).";
    - leaving clears it with "The trader left the market (sold 3 loads).".
  - `_apply` buy: stock − 1, `v["basket"] = goods`, the event "You traded your basket of fish for a load of wood." (kind `traded`), the note "Lina traded a basket of fish for a load of wood.", and `village_action` `{"action": "buy", "goods", "paid"}`.
  - `_decide` turns a buy whose basket changed while deciding into a wait, as give already does.
  - `state()` adds `trader: {stock, leaves: "14:00"} | null`.
  - Tests in test_village_runner.py:
    - the trader there exactly from 09:00 to 14:00 over a scripted day (SC-001);
    - a buy applied with the basket gone and the load carried;
    - a buy refused after 14:00;
    - two villagers buying the last paint in one step: the second is refused;
    - the load kept overnight;
    - the notes in the day record.
  - Requirements: FR-001, FR-002, FR-015.
- [X] T007 [US1] Frontend:
  - frontend/src/lib/api.ts: `Goods` widened with `wood`, `paint` and `saplings`; `VillageState.trader`; the `VillageAction` buy; event kind `traded`.
  - frontend/src/lib/village.ts: `carriedText(goods)`, `traderText(state)`, and `turnLabel` for buy ("trades fish for a load of wood" or "waited: …").
  - New frontend/src/components/village/building.tsx:
    - `Trader`: a cart and a figure at the market's free corner with piles of its goods;
    - `Load`: a carried load (planks, a paint pot, a sapling) drawn beside the figure like `Basket`.
  - VillageView.tsx draws them and adds the trader line under the weather.
  - Tests in frontend/src/lib/village.test.ts: `carriedText`, `traderText` with and without a trader, and `turnLabel` buy.
  - Screenshots of the trader at the market and a carried load (taken with T021: `make dev` serves the owner's live village, so scratch screenshots wait for the manual checks).
  - Requirement: FR-003.

## Phase 3: User Story 2 — The town hall meeting and vote (P1)

- [X] T008 [P] [US2] New backend/src/agent_lab/village/meeting.py (research §5):
  - `MEETING_OPENS = 17 * 60`, `MEETING_CLOSES = 17 * 60 + 30`.
  - `meeting_day(day)`: `day % 3 == 0` and not the festival day, or the day after a festival day divisible by 3. `next_meeting(day)` returns the next such day from `day` on.
  - Prompts, each with the persona and ending by naming its one JSON shape:
    - `proposal_prompt(world)`: Hilde's persona, the date, `built_text`, `buildable` with needs, the trader's usual goods, her learnings and memories;
    - `vote_prompt(world, name)`: persona, learnings, views, the 8 memories `recall` ranks highest, the proposals with Hilde's reasons;
    - `decision_prompt(world)`: Hilde's persona, the proposals, each vote with its reason, and the tally.
  - Parsers (pydantic shapes as in contracts/http-api.md):
    - `parse_proposals(answer, world)`: projects matched with `project_named`; unknown, built and repeated ones dropped; reasons "cut to 120"; "at most 3"; none left → "no project Hilde proposed can be built";
    - `parse_vote(answer, proposals)`: a proposal and a reason ≤ 120, else the reason;
    - `tally(votes)`;
    - `parse_decision(answer, proposals, votes)` → `{key, reason, against, by}` or `None` and the reason. When it is invalid, the most valid votes decide (ties: proposal order) with `by: "vote"` and the reason "Hilde gave no valid decision; the vote decided". With no valid votes there is no decision. `against` is true when the key is not among the most-voted.
  - `meeting_text(world, name)` ("Today at 17:00 the villagers meet at the town hall to choose what to build next. Hilde proposes: …"; for Hilde "You chair today's town hall meeting at 17:00; be there."; a review "… to talk about how the building goes."; after the meeting, what came of it; other days "The next town hall meeting is on day 9.").
  - `meeting_agent()`: block agent "Village meeting", a model block `meet` with a system text describing the four answer shapes, plus check `answer-is-json`.
  - Tests in new backend/tests/test_village_meeting.py:
    - meeting days 3, 6, … and day 21 → 22 in year 1;
    - `next_meeting`;
    - each prompt holds its parts;
    - every proposal, vote and decision case, including the vote fallback, ties and `against`;
    - the meeting texts;
    - the agent validates as a block agent.
  - Requirements: FR-004, FR-005, FR-006.
- [X] T009 [US2] backend/src/agent_lab/village/runner.py:
  - `ensure_agents` creates the meeting agent once, recreated if deleted.
  - `self.meetings: dict[str, Task]` keyed `"propose"`, `"vote:<name>"`, `"decide"`, `"tasks"`; `_settle` waits for them.
  - `_schedule`: when Hilde wakes on a meeting day:
    - with no project, start `_propose`;
    - with an unfinished project, set `world["meeting"] = {day, kind: "review", …}`;
    - with nothing buildable, set the outcome "nothing left to build".
  - `_propose` stores `world["meeting"] = {day, kind: "vote", proposals: [{key, reason, run_id}], votes: {}, present: [], decision: None, outcome: None}`, the event "You proposed: …" (kind `proposed`) and a note. When invalid, the outcome is "called off: Hilde had no proposals".
  - `_meeting()` in `_advance` after `_festival_guests`:
    - from 17:00 to 17:30, awake villagers on town hall cells join `present` (note "Greta came to the town hall meeting."), and each joiner but Hilde of a vote meeting starts one `_vote`;
    - at the first step at or after 17:30 with no vote run in flight and no outcome: Hilde absent gives "called off: Hilde did not come"; otherwise a vote meeting starts `_decide_meeting`.
  - `_vote` stores `votes[name] = {key | None, reason, run_id}` and notes "Greta voted for A market stand: …" (a claim).
  - `_decide_meeting` stores the decision (with `run_id`), `world["project"] = new_project(key, day)` and the outcome "decided". Every villager gets "At the town hall meeting Hilde chose …", plus " She went against the vote (most wanted …)." when `against` (kind `meeting`). Attendees remember it (memory kind `meeting`). Then a note.
  - Results for an old meeting day or during Reset are dropped.
  - Run village_actions: `propose`, `vote` and `decide` as in contracts/http-api.md.
  - turn.py's facts part and plan.py's `plan_prompt` add `meeting_text`.
  - `state()` adds `meeting` (names resolved, votes as a list) and `next_meeting`.
  - Responder in backend/tests/test_village_runner.py: answers the four meeting prompts from `"meeting:proposals"`, `"<name>:vote"`, `"meeting:decision"` and `"meeting:tasks"` queues, else with valid defaults (the first two buildable, a vote for the first proposal, a decision for it, one build task for Greta).
  - Tests in test_village_runner.py:
    - a proposal run when Hilde wakes on a meeting day and none on other days;
    - every villager but Hilde at the town hall votes exactly once, including one arriving at 17:20 (SC-003);
    - one arriving at 17:40 does not vote;
    - the decision starts the project, and everyone is told;
    - `against` told and noted;
    - Hilde alone decides alone ("nobody else came");
    - Hilde absent calls the meeting off;
    - invalid proposals call it off;
    - an invalid decision falls back to the vote;
    - a review meeting proposes nothing;
    - the festival-day meeting moves to the next day;
    - meeting runs never pause the village, and Step and Reset wait for them;
    - the meeting agent is created once.
  - Requirements: FR-004–FR-007, FR-015.
- [X] T010 [US2] turn.py: `RULES` adds "Hilde holds a town hall meeting every third day at 17:00 where the village chooses what to build." and the T005 text joins `OLD_RULES`. Test in test_village_runner.py: an agent holding the T005 rules gets the new ones. Requirement: FR-016.
- [X] T011 [US2] Frontend:
  - frontend/src/lib/api.ts: `VillageState.meeting`, `next_meeting`; the `VillageAction`s propose, vote and decide; event kinds `proposed` and `meeting`.
  - frontend/src/lib/village.ts:
    - `meetingLines(meeting)` (proposals with reasons, each vote with its reason, the tally, the decision, "Hilde went against the vote", the outcome);
    - `turnLabel` for propose, vote and decide.
  - New frontend/src/components/village/ProjectsPanel.tsx, opened with **Village projects** next to **Read the chronicle** in VillageView.tsx. The meeting section links each run to its trace, as ChroniclePanel does.
  - Tests in village.test.ts: `meetingLines` for a vote meeting, a decision against the vote, a called-off and a review meeting; `turnLabel` propose, vote, decide, and refusals.
  - Screenshot of the panel after a meeting (taken with T021).
  - Requirement: FR-014.

## Phase 4: User Story 3 — Hilde plans and hands out the work (P1)

- [X] T012 [P] [US3] meeting.py:
  - `work_plan_prompt(world)`: Hilde's persona; the project, `needs_left` and its site; today's trader stock or "the trader comes tomorrow at 09:00"; each villager's work place, hours and what it carries; for a review, the progress and the previous tasks.
  - `parse_tasks(answer)`:
    - `task` is one of buy, bring, build;
    - goods must be a building good, required for buy and bring;
    - villagers resolved with `villager_named`, unknown ones dropped;
    - a task with nobody left is dropped;
    - "at most 6 tasks, and none left → invalid".
  - `task_text(task)` ("buy paint from the trader", "bring paint to the building site", "build at the building site").
  - build.py `needs_left(world)` (`needs[g] - site[g] - used[g]`) and `project_text(world, name)`:
    - "The village is building: … It still needs 1 paint; the site holds 1 paint; 1 of 2 loads worked in.";
    - "Hilde asked you to: …" or "Nothing is asked of you; you may still help.";
    - `built_text`.
  - Tests in test_village_meeting.py: the work-plan prompt for a new project and a review; every task drop rule; more than 6 cut; none → invalid.
  - Tests in test_village_build.py: `needs_left` with loads on the site and used; `project_text` with and without tasks.
  - Requirements: FR-008, FR-009.
- [X] T013 [US3] runner.py:
  - `_assign` runs after a decision, and at 17:30 at a review meeting Hilde came to. A valid answer sets `project["tasks"]`, gives each named villager the event "Hilde asked you to …" (kind `task`) and a `task` trigger, adds a note, and sets the outcome "reviewed" for a review. `village_action` is `{"action": "assign", "tasks": ["buy paint: Jonas", …]}` or the reason.
  - turn.py's facts part and plan.py's `plan_prompt` add `project_text`.
  - plan.py `PLAN` adds "Fit in what Hilde asked of the villager and the town hall meeting.", with `OLD_PLANS = (the M11 text,)`; runner.py `_refresh_planner` replaces it verbatim in the stored planner agent and leaves edited ones alone.
  - `state()` adds `project` (key, name, kind, needs, site, used, done = sum(used), total = sum(needs), tasks, day).
  - Tests in test_village_runner.py:
    - tasks after a decision appear in the named villagers' next observation and plan prompt;
    - a villager without a task is told about the project;
    - an invalid work plan leaves the project without tasks and records why;
    - a review meeting replaces the tasks;
    - the planner refresh, and an edited planner left alone.
  - Requirements: FR-008, FR-009.
- [X] T014 [US3] Frontend: frontend/src/lib/api.ts (`VillageState.project`, the `VillageAction` assign, event kind `task`); lib/village.ts `projectLines(project)` (needs, site, done of total, tasks) and `turnLabel` assign; ProjectsPanel.tsx's current-project section with a progress bar and the tasks. Tests in village.test.ts. Requirement: FR-014.

## Phase 5: User Story 4 — Building and seeing it stay (P2)

- [X] T015 [P] [US4] build.py (research §4):
  - `site_cells(world)`, `site_at(world, cell)`.
  - `site_refusal(world, name, goods)`: "the building site does not need paint" / "the building site has all the wood it needs".
  - `build_step(world) -> str | None`:
    - the working steps of everyone working at the site add up in `project["work"]`, only while loads lie there;
    - at `BASKET_STEPS` (6), one load lying there is used (catalogue order among those lying there): `site[g] -= 1`, `used[g] += 1`;
    - when `used` equals `needs`, return the key.
  - Tests in test_village_build.py:
    - loads delivered in any order (paint before wood and back) leave the right `needs_left`, also after a JSON round trip (save and reload);
    - two workers use a load in 3 steps;
    - no loads, no progress;
    - "a fully stocked bakehouse that one worker cannot finish within one waking day";
    - the finish returned once.
  - Requirements: FR-010, FR-011, FR-013.
- [X] T016 [US4] work.py and turn.py:
  - `work_refusal` checks `site_at` first: valid while the site holds loads, else "the building site has nothing to work with yet: bring goods first". The parsed action is `{"action": "work", "place": "site"}`.
  - `give_refusal` without a name on a site cell uses `site_refusal` and refuses basket goods.
  - `NO_GIVING` adds "or stand at the building site to set down a load".
  - `work_step` skips the site.
  - turn.py `_destination`: "building site" or "site" resolves to the site while a project runs, else "nothing is being built". Places adds "building site N steps".
  - Tests in test_village_work.py and test_village_turn.py: each refusal, the move, and the Places line with and without a project.
  - Requirements: FR-010, FR-011.
- [X] T017 [US4] turn.py: `RULES` adds the building site (give without a name there to set down a load, work there to build, move to "building site") and the T010 text joins `OLD_RULES`. Test in test_village_runner.py: an agent holding the T010 rules gets the final rules. Requirement: FR-016.
- [X] T018 [US4] runner.py:
  - `_give` at the site: `project["site"][goods] += 1`, the event "You set down a load of paint at the building site.", and a note.
  - `_set_off` and `_seek` handle the site goal.
  - `_advance` calls `build_step` after `work_step`. A finished project:
    - `built.append({key, day})`, `project = None`;
    - every worker there stops working;
    - every villager gets the event `done_text` (kind `built`);
    - awake villagers remember it (memory kind `built`);
    - a note.
  - chronicle.py `chronicle_prompt` adds `built_text`.
  - `state()` adds `built` (with names and kinds) and `map.catalogue` (`[{key, name, kind, site, at}]`).
  - Tests in test_village_runner.py:
    - one scripted cycle: meeting → decision → tasks → a buy → a load set down → work → finished project in `built` that stays after the next morning (SC-002);
    - a load the site does not need refused and kept;
    - progress kept overnight;
    - the chronicle prompt names what is built;
    - the finished project's memories and events.
  - Requirements: FR-010–FR-012, FR-015.
- [X] T019 [US4] Frontend:
  - frontend/src/lib/api.ts: `VillageState.built`, `map.catalogue`, `Villager.working` `"site"`, event kind `built`.
  - lib/village.ts: `cellKind` for `b` and `r` (a new kind `plot`), `stateText` "Building at the site".
  - building.tsx:
    - `Plot`: fenced grass until built;
    - `Site`: scaffolding and the loads lying there;
    - `Built` by kind:
      - paint: a fresh colour over the house or town hall;
      - trees: young trees;
      - stand: a striped stall;
      - building: a small house on its plot;
      - boat: a boat by the pier.
  - VillageView.tsx draws them.
  - ProjectsPanel.tsx gets a "Built so far" section.
  - Tests in village.test.ts: `cellKind` plots, `stateText` building.
  - Screenshots of a site under construction, every kind finished, and the panel (taken with T021).
  - Requirements: FR-012, FR-014.

## Phase 6: Polish

- [X] T020 Docs:
  - README.md: the trader, meetings and building; the M12 row in Milestones marked done; the roadmap with boat trips under M13.
  - docs/village.md: the trader, the meeting, tasks and the building site; the controls unchanged; "What's next" with boat trips under M13.
  - docs/api.md: the new state fields and village actions.
  - AGENTS.md: `trade.py`, `build.py` and `meeting.py` in the layout, the meeting agent in the village contracts, and the current feature.
- [X] T021 `make check`; the quickstart's manual steps on the real model on a scratch backend with a copy of the database, following specs/012-building-together/quickstart.md, results recorded in a new "Manual check results" section at the end of specs/012-building-together/tasks.md (SC-004, SC-005).

## Dependencies

| Task | Needs |
|---|---|
| T001 | – (everything backend needs it) |
| T002, T003 | – (run alongside T001) |
| T004 | T003 |
| T005 | T004 |
| T006 | T001, T005 |
| T007 | T006 |
| T008 | T002 |
| T009 | T001, T008 |
| T010 | T005, T009 |
| T011 | T009 |
| T012 | T008 |
| T013 | T009, T012 |
| T014 | T011, T013 |
| T015 | T002, T012 |
| T016 | T015 |
| T017 | T010, T016 |
| T018 | T013, T016 |
| T019 | T018 |
| T020 | – |
| T021 | everything (last) |

Stories in order:
- US1 (trader) is independent of the others.
- US2 (meeting) needs only the catalogue.
- US3 needs US2's decision.
- US4 needs US3's project and the trader's loads (US1) for its full cycle.

## Parallel opportunities

- T002 (catalogue) and T003 (carried text) alongside T001 (world).
- T004 (`trade.py`) alongside T008 (`meeting.py`): different modules, both pure.
- T012 (work-plan parsing) and T015 (`build_step`) alongside the runner tasks of earlier phases.
- The frontend tasks T007, T011, T014 and T019 each follow their story's runner task and can run
  while the next story's backend starts.

## Implementation strategy

- **MVP:** Phase 1 + Phase 2. A trader comes every day and villagers trade baskets for loads,
  which is visible on the map at once.
- **Then:** the meeting (Phase 3) and the work plan (Phase 4), which give the village a project
  and tasks. Building (Phase 5) closes the loop and leaves something on the map for good.
- Each phase is shippable on its own; only Phase 5's full cycle needs all four stories.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | test_village_trade.py (stock, due); test_village_runner.py (09:00–14:00) |
| FR-002 | test_village_trade.py, test_village_turn.py (buy and refusals); test_village_runner.py (applied, last paint race) |
| FR-003 | test_village_trade.py, test_village_turn.py (trader text); village.test.ts; T007 screenshot |
| FR-004 | test_village_meeting.py (meeting days, proposals); test_village_runner.py (proposal run) |
| FR-005 | test_village_meeting.py (meeting text); test_village_runner.py (in observations and plans) |
| FR-006 | test_village_meeting.py (votes, decision, fallback, against); test_village_runner.py (attendance, one vote each, told) |
| FR-007 | test_village_runner.py (review meeting) |
| FR-008 | test_village_meeting.py (tasks parsing); test_village_runner.py (work-plan run) |
| FR-009 | test_village_build.py (`project_text`); test_village_runner.py (tasks in observations and plans) |
| FR-010 | test_village_build.py, test_village_work.py (site deliveries); test_village_runner.py |
| FR-011 | test_village_build.py (`build_step`, any order, fully stocked bakehouse); test_village_work.py |
| FR-012 | test_village_runner.py (finished, stays, told, remembered); T019 screenshots |
| FR-013 | test_village_build.py (catalogue, sites walkable, building sizes) |
| FR-014 | village.test.ts (`meetingLines`, `projectLines`, turn labels); T011, T014, T019 screenshots |
| FR-015 | test_village_runner.py (notes); test_village_chronicle.py (built so far) |
| FR-016 | test_village_runner.py (rules refresh from M11, T005 and T010 texts; edited left alone) |
| FR-017 | test_village_world.py, test_village_runner.py (version 5 loads, Reset) |
| FR-018, FR-019 | T001–T019 tests; `make check` (T021) |

| SC | Test / check |
|---|---|
| SC-001 | test_village_runner.py (trader hours, every buy applied or refused) |
| SC-002 | test_village_runner.py (the full scripted cycle, T018) |
| SC-003 | test_village_runner.py (one vote each, decision visible and noted) |
| SC-004 | quickstart steps 2–4 (real model) |
| SC-005 | quickstart step 4 (real model) |

## Manual check results (2026-11-02)

Screenshots (a scratch world at summer day 67, 10:00, checked in a headless browser, not
committed): the trader's cart and goods at the market and its line under the weather; Lina
carrying paint and Jonas wood; the bakehouse plot fenced with scaffolding and loads at its site;
the finished town hall and Lina's house (fresh trim), trees by the square, the market stand, the
rowing boat by the pier and the barn on its plot; "Building at the site" in the list; the
**Village projects** panel with progress bar, needs, tasks, the meeting's proposals, votes and
decision (T007, T011, T014, T019).

Real model (vLLM `qwen3.5-9b`), each run on a fresh scratch copy of the owner's database at
summer day 66 (a meeting day) 04:30, everyone asleep with a basket, nothing built, six village
days at Fast (about 22 minutes, about 1,050 runs each):

| Run | Meetings | Trades / loads set down | Built | Fixed after it |
|---|---|---|---|---|
| E | day 66 called off: Hilde's proposals failed the JSON check (last brace missing) | – | – | unusable proposals and work plans are asked for once more |
| F | day 66: Hilde, Greta; market stand chosen; day 69 review, Hilde alone | 3 / 1 | – (1 of 4 loads) | a needed load is pointed to the site ("Take your load …", "set down … now"); everyone away is called to the meeting |
| G | both called off: Hilde held in a talk at 17:00, then too far to arrive by 17:30 | 0 / 0 | – | the call moved to 16:30 with the move to make; the meeting waits for Hilde until 18:30 |
| H | day 66: Jonas, Greta, Lina voted; Hilde walking from 16:30 but held in talks until 18:40 | 1 / 0 | – | walking to an open meeting goes on while talking (as the walk home to bed) |
| I | day 66: all four, 3 votes, trees decided; Hilde handed out only "build" | 0 / 0 | – | the work-plan prompt asks for buy tasks; a basket is pointed to the trader while the site holds nothing |
| J | day 66: three present, trees; "buy saplings" handed out | 4 / 3 | – (1 of 3 loads: builders left after half an hour) | loads waiting at the site call everyone not building to come and build |
| K | day 66: all four, 3 votes, trees chosen by the vote; day 69: Hilde and Greta, Hilde chose painting the town hall **against the vote** (Greta: the market stand) | 5 trades by all four / 5 | **trees by the square on day 68**; town hall 1 of 2 | – |

Run K against the success criteria:
- SC-004: the day-66 meeting had all four villagers (at least three), and a project (the trees)
  was finished on day 68, within six days. Pass.
- SC-005: all four traded a basket for a load (Greta, Lina, Jonas once, Hilde twice); three
  worked at the site (Lina 6 turns, Hilde 4, Greta 1). Pass.
- Everyone remembered "Young trees now grow by the square." and the meetings ("Hilde chose …
  I voted for …"); no run failed.

Also found and fixed during the checks: a review meeting whose project finished that morning
crashed the work plan, and answers from an earlier meeting day still counted (both with
regression tests); a vote could start while Hilde was already deciding (voting now closes when
she starts).

Observed, not fixed:
- Chronicle entries still borrow weather from the villagers' talk ("The Rush Before the Snow" on
  a cloudy summer day), the open M11 issue.
- Villagers often try to hand loads and baskets to Hilde (17–30 refusals a run with "Hilde's hands
  are full").
- `runner._decide` builds the prompt before its `try`: if that ever raised, the villager would stay
  "deciding" and Step and Reset would wait for ever (seen with a malformed test project; M11 code).

