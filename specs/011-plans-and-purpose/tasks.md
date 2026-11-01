---
description: "Task list for M11 — Plans and Purpose"
---

# Tasks: M11 — Plans and Purpose

**Input**: `specs/011-plans-and-purpose/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-016, SC-001–SC-003). `FakeLLM` only; the shared responder in
`test_village_runner.py` tells decisions, reflections, chronicles and plans apart by the prompt.
Runner tests pass `move_gap=0`.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- Plans and revisions are ordinary runs of the shared planner agent through
  `Village._run(agent_id, name, prompt, tick)`, like the reflections: the village never calls the
  model itself; the answer is validated, never executed, and redacted after decoding; plan runs
  never reach `outcomes`, never count as decisions or toward the failure pause.
- The rules only advertise actions the parser accepts: T006 adds the sentences of US1 and US2,
  T010 adds work and give. `_refresh_rules` only replaces a rules text it finds verbatim, so each
  edit moves the text it replaces into `OLD_RULES`; no village loaded between phases is stranded.
- New drawings live in `components/village/seasons.tsx`; decorations use `pointer-events: none`
  and have no animation.

---

## Phase 1: Foundational — world version 5

- [ ] T001 backend/src/agent_lab/village/world.py (research §5, data-model.md): `VERSION = 5`; `new_world()` adds per villager `plan: None`, `basket: None`, `working: None`, `said: []`, and world `stalls {fish: 0, vegetables: 0, flowers: 0}`, `harvest {pier: 0, fields: 0, flower_garden: 0}`, `planner_agent_id: None`; `upgrade()` chains 2 → 3 → 4 → 5 with an explicit 4 → 5 step ("no plans, empty hands, not working, nothing said, empty stalls, harvest 0s, `planner_agent_id` null"); runner.py `_load` accepts versions 2, 3 and 4; Reset keeps `reflection_agent_id`, `chronicler_agent_id` and `planner_agent_id`; `state()` leaves out `said`, `harvest` and `planner_agent_id`; tests in test_village_world.py (new world shape, a version-4 world upgrades with the fields above) and test_village_runner.py (a version-4 and a version-2 world load and keep going, Reset clears the new fields and keeps the three agent ids, `state()` has none of the internal fields) (FR-015)

## Phase 2: User Story 1 — Daily plans (P1) 🎯 MVP

- [ ] T002 [P] [US1] New backend/src/agent_lab/village/plan.py (research §1): `PLAN_ENTRIES = 6`, `PURPOSE_TEXT = 120`, `REVISIONS = 2`; `plan_prompt(world, name, revise=None)` (persona; sleeping hours and the usual day from the routine, e.g. "05:00 pier, 11:00 market, 14:00 pier"; date, weather and festival line; how the fields and the garden are doing; the 8 memories `recall` ranks highest, learnings and views; a revision adds "Your plan so far:" and "The conversation you just had:" with the transcript; ends "Plan your day. Answer with one JSON object."); `parse_plan(answer, name) -> (entries | None, reason)` (pydantic shape `{"plan": [{"time", "place"?, "villager"?, "purpose"}]}`; per entry: time `H:MM`/`HH:MM` within the day else dropped; `place` resolved with turn.py `_place` ("home" allowed), else `villager` with `_name` (not the villager itself), else dropped; purpose stripped and "cut to 120", empty dropped; sorted by time, cut to 6; "fewer than 2 left → invalid" with the reason "a plan needs at least 2 entries"); `marks(plan, minute) -> (current, next)` (current: the last entry whose time has come; next: the first still to come); `entry_text(entry)` ("11:00 see Jonas: ask for fish", "07:30 town hall: …"); `plan_lines(plan, minute)` ("Your plan for today:" with "(now)" and "(next)" marks); `planner_agent()` (block agent "Village planner": model block `plan` + check `answer-is-json`); tests in new backend/tests/test_village_plan.py: the prompt holds each part and a revision's transcript; valid plans; each dropped-entry case (bad time, unknown place and villager, itself, empty purpose); more than 6 cut by time; purpose cut to 120; fewer than 2 invalid; marks before the first entry, between entries and after the last; the agent validates as a block agent
- [ ] T003 [US1] backend/src/agent_lab/village/runner.py (research §1): `ensure_agents` creates the planner once (recreated if deleted); `self.plans: dict[str, Task]` chained per villager like `self.reflections`; `_start_plan(name, revise)` from `_schedule` when a villager wakes and from `_end_conversation` for each awake participant not at bedtime when the conversation had at least 4 lines, the participant has today's plan and fewer than `REVISIONS` revisions (the counter goes up when the run starts); `_plan` drops the result when the villager is asleep or the day has changed, else sets `v["plan"] = {day, entries: [{minute, place, villager, purpose}], revisions}`, the event "You planned your day." / "You changed your plan." (kind `planned`), the day-record note "Hilde's plan for the day: 07:30 town hall (…); …", `village_action` `{"action": "plan", "revision", "entries"}` or `{"action": "plan", "revision", "reason"}` (the previous plan kept); `_settle` waits for plan tasks; turn.py `observation` adds `plan_lines` for today's plan; `state()` per villager `plan {entries: [{time, place (label) | null, villager | null, purpose}], current, next, revisions}` for today, else `null`; test responder in backend/tests/test_village_runner.py answers planner prompts from a `"<name>:plan"` queue, else a default valid plan, and existing assertions that count a villager's turns include its plan runs; tests in test_village_runner.py: one plan run per villager on waking, a valid plan stored and shown with marks in every observation that day, an invalid answer keeps the previous plan (or none) and records the reason, a 4-line conversation starts a revision that sees the transcript, a 3-line one does not, no third revision in a day (SC-001), a yesterday's run finishing after waking is dropped, a failing plan run does not pause the village, Step and Reset wait for plan runs, the planner agent created once and listed (FR-001–FR-003)
- [ ] T004 [US1] frontend/src/lib/api.ts (`Villager.plan`, `VillageAction` plan, event kind `planned`); frontend/src/lib/village.ts `planEntryText(entry)` and `turnLabel` for plan runs ("plans the day" / "changes the plan" or the reason); frontend/src/components/village/VillagerPanel.tsx "Today's plan" under the persona, the current entry marked "now" and the next "next", empty text "No plan yet: villagers plan their day when they wake."; tests in frontend/src/lib/village.test.ts (`planEntryText` with a place and with a villager, `turnLabel` plan, revision and refusal); screenshot of the panel with a plan (FR-004)

## Phase 3: User Story 2 — Facts apart from claims (P1)

- [ ] T005 [US2] backend/src/agent_lab/village/turn.py (research §2): `observation` regrouped, order inside groups otherwise unchanged: "What you know for sure:" (date, time, weather with "this is the real weather", festival line, where you are, growing places you know, your hours and usual place, your plan, your goal, next to you, in sight, whom you talk with, places with distances), "Where the others are, as far as you know:" (new `seen_text`: only what you saw, or their routine when unseen; `belief_text` stays for the panel), "What others told you (claims; they may be wrong):" ("Said to you since your last turn:" and "Heard about where others are:" with "- Greta: at the market (Lina said at 09:00)"), then learnings, memories, last events (heard events as `Jonas said to you: "…"`) and the question; tests in test_village_turn.py: facts before claims, heard lines and heard whereabouts only under claims, `seen_text` for seen and unseen villagers (FR-005)
- [ ] T006 [US2] turn.py: `RULES` adds "Trust what you see over what you hear; the weather you are told is the real weather." and "Follow your plan for the day unless something more important comes up." (no work or give yet: T010); `PREVIOUS_RULES` becomes `OLD_RULES = (M7 rules, M9 rules)`; runner.py `_refresh_rules` replaces whichever of `OLD_RULES` a stored agent holds verbatim and leaves edited prompts alone; tests in test_village_runner.py: agents holding the M7 text and the M9 text both get the new rules, an edited prompt is left alone, new villager agents hold the new rules (FR-006)
- [ ] T007 [P] [US2] runner.py conversation note "Greta and Lina talked; what they said (their claims): …"; backend/src/agent_lab/village/chronicle.py `chronicle_prompt` heads the items with "What happened (what villagers said are their claims, not events; never report a claim as an event; the weather is the one given above):"; tests in test_village_chronicle.py (the heading, a conversation note marked as claims) (FR-007)

## Phase 4: User Story 3 — No repeated lines (P2)

- [ ] T008 [US3] turn.py (research §3): `same_line(a, b)` comparing `re.sub(r"[\W_]+", "", text.lower())`; `parse_action` turns a say repeating one of the speaker's `said` into a wait with "you already said that" and a goodbye repeating one into the goodbye with `text: None`; `observation` adds "What you said lately:" after the facts ("- nothing yet" when empty); runner.py `_say` keeps the last 3 lines as spoken (after the `SPEECH_SHOWN` cut), oldest first, across days; tests in test_village_turn.py ("Where are the fish?" vs "where are the fish" refused, a line said four lines ago allowed, the goodbye without its text, the observation section) and test_village_runner.py (a refused say is never heard, `said` keeps 3, Reset clears it) (FR-008, FR-009, SC-002)

## Phase 5: User Story 4 — Work and festival deliveries (P2)

- [ ] T009 [P] [US4] New backend/src/agent_lab/village/work.py (research §4): `GOODS = {"pier": "fish", "fields": "vegetables", "flower_garden": "flowers"}`; `goods_at(world, place)` (fish always at the pier, vegetables when the fields are `ripe` or `harvested`, flowers when the garden is `blooming`, else `None`); `work_refusal(world, name)` (fields and garden for anyone; the pier for Jonas or anyone while Jonas works there, else "only Jonas fishes here; work with him while he fishes"; elsewhere "there is no work for you here"; working while talking allowed); `give_refusal(world, name, to)` ("your hands are empty"; unknown, not next to you, asleep; "Hilde's hands are full"; no name off the square: "nobody to give it to: name someone next to you, or stand on the square to set it out for the festival"); `work_step(world) -> list[tuple[str, str]]` (every awake villager working on its place: `tended[place] += 1` for the fields and the garden, its `steps += 1`; per place with goods `harvest = min(harvest + workers, 6)`, at 6 the worker with empty hands and the most `steps` (ties: villager order) gets the basket, `harvest` and its `steps` back to 0; no goods keeps `harvest` at 0; nobody with empty hands keeps it at 6); `stalls_text(stalls)` ("The festival stalls on the square hold fish; they still lack vegetables and flowers."); `empty_stalls()`; tests in new backend/tests/test_village_work.py: goods at each place and stage, every work and give refusal, one worker fills a basket in 6 steps and two in 3 (SC-003), two workers tend in half the steps, the longest worker gets the basket, nobody with empty hands keeps the work, no basket from a place without goods, stalls text for empty, partial and full stalls (FR-010, FR-011)
- [ ] T010 [US4] turn.py: `RULES` adds work and give (contracts/http-api.md "Villager agent answers") and the T006 text joins `OLD_RULES`, so agents refreshed in Phase 3 get the final rules on load; `Work` and `Give` actions; `parse_action` handles `{"action": "work"}` (refused with `work_refusal`) and `{"action": "give", "to"?}` (refused with `give_refusal`); the facts part adds "you work here" to where you are, your basket and, in autumn, `stalls_text`; tests in test_village_turn.py (each new action valid and refused, the basket and stalls lines, stalls only in autumn) and test_village_runner.py (an agent holding the T006 rules gets the final rules) (FR-006, FR-012–FR-014)
- [ ] T011 [US4] runner.py: `_apply` work (`v["working"] = {place, steps: 0}`, kept when already working there; event kind `worked`) and give (basket to the receiver with the events "You gave your basket of fish to Hilde." / "Jonas gave you a basket of fish." and a `given` trigger, kinds `gave` and `received`; or onto `world["stalls"][goods] += 1` with "You set out your fish on the festival stalls."; both noted in the day record; `village_action` `{"action": "give", "to", "goods"}`); `_set_off`, `_seek`, a goodbye with a place or villager and bedtime end working, say and wait do not; `_advance` calls `work_step` in place of counting standing villagers, each basket becomes the event "You filled a basket of fish." (kind `basket`), a `basket` trigger and the note "Jonas filled a basket of fish."; `_remember_festival` adds "The stalls held fish and flowers." or "The stalls stood empty."; seasons.py `end_day` clears the stalls when winter comes; chronicle.py adds `stalls_text` on the festival day; `plan_prompt` adds the stalls line in autumn and the villager's basket; `state()` per villager `basket`, `working` (place key or `null`), state `working`, and world `stalls`; tests in test_village_runner.py: standing without working never tends, working tends, Greta and Lina together tend the fields and fill a basket in half a village hour (spec US4 scenario 7), fishing with Jonas and refused without him, Jonas stopping leaves the others fishing, a basket from each place and none from empty ones, give to a villager and to the stalls with both sides told, the basket kept overnight, walking off ends work, a scripted autumn with all three goods delivered fills the stalls and one without deliveries leaves them empty (SC-003), the festival memories and chronicle prompt name the goods, stalls cleared at winter in test_village_seasons.py (FR-010–FR-014)
- [ ] T012 [US4] frontend/src/lib/api.ts (`Villager.basket`, `Villager.working`, state `working`, `VillageState.stalls`, `VillageAction` work and give, event kinds `worked`, `basket`, `gave`, `received`); lib/village.ts `stateText` for working ("Working at the fields"), `turnLabel` for work and give, `stallsText(stalls)`; seasons.tsx `Stalls` (three small stalls along the square's lower edge in autumn and whenever goods are out, each showing fish, vegetable crates or flower pots, or bare) and `Basket` (a small basket in the goods' colour beside a carrying villager); VillageView.tsx draws them; tests in village.test.ts (`stateText` working, `turnLabel` work, give to a villager and to the stalls, `stallsText`); screenshots of the stalls empty and full and of a carried basket (FR-013)

## Phase 6: Polish

- [ ] T013 README.md (plans, work and baskets, the festival stalls, the M11 row in Milestones marked done), docs/village.md (plans, facts and claims, no repeated lines, work and give), AGENTS.md (`plan.py`, `work.py` in the layout; the planner in the village contracts; current feature)
- [ ] T014 `make check`; quickstart manual steps on the real model on a scratch backend with a copy of the database, results recorded below (SC-004–SC-006)

## Dependencies

T001 → everything backend. T002 ∥ T001; T003 needs T001 and T002; T004 needs T003. T005 needs
T003 (the plan sits in the facts). T006 needs T005; T007 is independent of T005/T006. T008 needs
T005. T009 needs T001; T010 needs T006 and T009; T011 needs T003, T010; T012 needs T011. T013 →
T014 last.

## Parallel opportunities

- T002 (`plan.py`) alongside T001 (`world.py`).
- T007 (chronicle prompt) alongside T005–T006.
- T009 (`work.py`) alongside Phases 2–4.

## Implementation strategy

MVP: Phase 1 + Phase 2 (plans) — the biggest visible change. Then facts and claims (cheap, fixes
the invented storms), no repeated lines, work and deliveries; each phase is shippable on its own.

## Traceability

| FR | Test / check |
|---|---|
| FR-001 | test_village_plan.py (prompt, parse); test_village_runner.py (plan on waking) |
| FR-002 | test_village_plan.py (marks); test_village_runner.py (marked in every observation) |
| FR-003 | test_village_runner.py (revision after 4 lines, limit, not a decision, Step/Reset) |
| FR-004 | village.test.ts (`planEntryText`, `turnLabel`); T004 screenshot |
| FR-005 | test_village_turn.py (facts and claims parts) |
| FR-006 | test_village_runner.py (rules refresh from M7, M9 and the T006 text, edited left alone) |
| FR-007 | test_village_chronicle.py (claims heading, conversation note) |
| FR-008, FR-009 | test_village_turn.py, test_village_runner.py (repeated lines, said lately) |
| FR-010, FR-011 | test_village_work.py; test_village_runner.py (tending, shared work, baskets, Jonas) |
| FR-012 | test_village_turn.py, test_village_runner.py (give) |
| FR-013 | test_village_turn.py (stalls in autumn); test_village_runner.py (festival); test_village_seasons.py (cleared at winter); T012 screenshots |
| FR-014 | test_village_work.py, test_village_turn.py (every refusal) |
| FR-015 | test_village_world.py, test_village_runner.py (version 4 loads, Reset) |
| FR-016, FR-017 | T001–T012 tests; `make check` (T014) |

| SC | Test / check |
|---|---|
| SC-001 | test_village_runner.py (plans all day, at most two revisions) |
| SC-002 | test_village_turn.py, test_village_runner.py |
| SC-003 | test_village_work.py; test_village_runner.py (scripted autumn) |
| SC-004 | quickstart steps 1–2 (real model) |
| SC-005 | quickstart step 4 (real model) |
| SC-006 | quickstart step 3 (real model) |

## Manual check results

(filled in by T014)
