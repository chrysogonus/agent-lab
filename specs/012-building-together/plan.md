# Implementation Plan: M12 — Building Together

**Branch**: `main` (feature directory `012-building-together`) | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-building-together/spec.md`

## Summary

Backend: three new pure modules.

- `trade.py`: a trader comes to the market every day from 09:00 to 14:00 with a stock drawn from
  the day. A new `buy` action trades a carried basket for one load of wood, paint or saplings.
- `build.py`: a catalogue of ten projects with fixed sites. Loads are set down at the current
  site with `give`, and `work` there uses one load per village hour of work, added up over the
  workers as in M11. A finished project is kept in `built` and drawn for good; two new map plots
  hold the buildings.
- `meeting.py`: every third day Hilde proposes from the catalogue, the others at the town hall
  vote from 17:00 to 17:30, Hilde decides (and may overrule the vote with a reason), and a
  work-plan run hands out tasks. All of it runs on one shared "Village meeting" block agent.

The runner wires these in as it does plans: `_trader()` and `_meeting()` in `_advance`, meeting
runs in `self.meetings`, and `build_step` after `work_step`. Villager rules, plan prompts and
observations learn about the trader, the meeting, the project and the villager's tasks. World
version 6, upgraded from 5.

Frontend: the trader, the site, finished projects and carried loads on the map; turn labels for
the new runs; a **Village projects** panel with the current project, the latest meeting and what
has been built.

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged
- **Storage**: the village row, world version 6
- **Testing**: pytest with `FakeLLM`, vitest
- **Target Platform**: local web app (127.0.0.1)
- **Project Type**: web application (`backend/`, `frontend/`)
- **Performance Goals**: a meeting day adds at most 1 proposal, 3 votes, 1 decision and 1 work-plan
  run; other days add none beyond M11
- **Constraints**:
  - meeting runs never count as decisions or toward the failure pause;
  - the state stays small (catalogue static, at most 6 tasks, the latest meeting only);
  - the map's path search stays static (plots are blocked from the start);
  - no image assets, and decorations never intercept clicks.
- **Scale/Scope**: 4 villagers, 10 catalogue projects, one project at a time

No open questions: the owner answered all three on 2026-11-02, and research.md settles the rest.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass (see Complexity Tracking) | Rules live in three small new modules (`trade.py`, `build.py`, `meeting.py`); `runner.py` only wires them, as it does plans and reflections |
| II. Observable by default | Pass | Proposals, votes, decisions and work plans are ordinary traced runs of a block agent tagged with the villager; buy is a decision recorded as `village_action`; the meeting keeps each run id so the panel opens its trace |
| III. Secure local defaults | Pass | Every meeting answer is validated against the catalogue, the proposals and known names; reasons are cut and redacted after decoding, never executed |
| IV. Smallest change | Pass | No new endpoint or dependency; the carried thing stays one `basket` field; building reuses M11's work counting and `give`; one shared agent serves the four meeting prompts |
| V. Gates + traceability | Pass | FR → test map in `tasks.md`; view logic (carried text, trader text, project and meeting lines, turn labels, plot cells) in `lib/village.ts` with vitest |

Post-design re-check: still passes. The design refined four points of the spec, all now written
into spec.md:

- Hilde chairs the meeting and does not vote.
- A meeting Hilde misses is called off.
- An invalid decision falls back to the vote.
- New buildings need 17 or more loads, more than the longest waking day of 16 hours.

## Design

### Backend (`village/`)

- `trade.py` (new, research §1–§2):
  - constants `TRADER_ARRIVES`, `TRADER_LEAVES`, `BUILDING_GOODS`, `BASKET_GOODS`;
  - `trader_stock(day)`, `trader_here(world)`, `buy_refusal(world, name, goods)`,
    `trader_text(world)`, `carried_text(goods)`.
- `build.py` (new, research §3–§4):
  - `CATALOGUE`, `entry(key)`, `new_project(key, day)`;
  - `site_cells(world)`, `site_at(world, cell)`, `needs_left(world)`;
  - `site_refusal(world, name, goods)`, `build_step(world) -> str | None`;
  - `project_text(world, name)`, `built_text(world)`.
- `meeting.py` (new, research §5):
  - `meeting_day(day)`, `next_meeting(day)`, constants `MEETING_OPENS` and `MEETING_CLOSES`;
  - `meeting_text(world, name)`;
  - prompts: `proposal_prompt`, `vote_prompt`, `decision_prompt`, `work_plan_prompt`;
  - parsers: `parse_proposals`, `parse_vote`, `parse_decision` (with the vote fallback),
    `parse_tasks`, `tally`;
  - `task_text`, `meeting_agent()`.
- `work.py`:
  - `give_refusal` takes the site and the stalls' basket-only rule into account;
  - `work_refusal` checks the site first;
  - `work_step` skips the site, which `build_step` counts;
  - `NO_GIVING` mentions the site;
  - `delivery_text` and the texts use `carried_text`.
- `world.py`:
  - `ROWS` with plots `b` and `r`, which join `BLOCKED`;
  - `place_named` accepts "building site" and "site" (resolved against the world in `turn.py`);
  - `VERSION = 6`, and `new_world()` adds `trader`, `meeting`, `project`, `built` and
    `meeting_agent_id`;
  - `upgrade()` gets an explicit 4 → 5 step, then 5 → 6, which moves villagers off plot cells.
- `turn.py`:
  - a `Buy` action, and `parse_action` handles buy;
  - move and goodbye accept the building site while a project runs;
  - the observation adds `trader_text`, the carried line, `meeting_text`, `project_text` and
    "building site N steps" under Places;
  - `RULES` (M12), with `OLD_RULES` adding `_M11_RULES`.
- `plan.py`: `plan_prompt` adds the trader, meeting and project lines; `PLAN` gains one
  sentence; `OLD_PLANS` holds the M11 text for the planner refresh.
- `chronicle.py`: `chronicle_prompt` adds "Built so far: …".
- `runner.py`:
  - `_refresh_planner` (stored planner agents with the M11 text get the new one);
  - `ensure_agents` creates the meeting agent, and Reset keeps its id;
  - `self.meetings: dict[str, Task]`, with `_start_meeting_run(key, coro)`, `_propose`, `_vote`,
    `_decide_meeting`, `_assign`, waited for by `_settle`;
  - `_schedule` starts the proposal run when Hilde wakes on a meeting day;
  - `_advance` calls `_trader()`, then after `work_step` `build_step` (finishing a project:
    `built`, events, memories, note), then `_meeting()`;
  - `_apply` handles buy; `_give` handles the site;
  - `_set_off` and `_seek` resolve the site;
  - `state()` adds `trader`, `meeting` (with names), `project` (with name, needs, total),
    `built`, `next_meeting` and `map.catalogue`, and drops `meeting_agent_id`.

### Tests

- The shared test responder (`tests/test_village_runner.py`) answers meeting prompts:
  - scripted `proposals`, `vote`, `decision` and `tasks` queues;
  - otherwise valid defaults (the first two buildable projects, a vote for the first proposal,
    a decision for it, one build task for Greta).

  Existing tests keep running, because meeting runs only start on meeting days at set times.
- New `test_village_trade.py`, `test_village_build.py` and `test_village_meeting.py` for the pure
  modules.
- Runner, turn, work, plan, chronicle, world and API tests extended (one cycle from meeting to
  finished project in `test_village_runner.py`, for SC-002).
- `test_village_build.py` covers loads delivered in any order (paint before wood and back),
  `needs_left` per goods across a save and reload, and a fully stocked bakehouse that one worker
  cannot finish within one waking day.
- A map test checks that every walkable cell is reachable and that every site cell is walkable.

### Frontend

- `lib/api.ts`:
  - `Goods` widened, the `VillageState` fields `trader`, `meeting`, `project`, `built`,
    `next_meeting` and `map.catalogue`;
  - the buy, propose, vote, decide and assign `VillageAction`s, and the new event kinds.
- `lib/village.ts` (+ test):
  - `cellKind` for the plots;
  - `carriedText`, `traderText`, `projectLines`, `meetingLines`, `tally`;
  - `turnLabel` for the new actions.
- `components/village/building.tsx` (new): `Trader`, `Site`, `Built`, `Load`, `Plot`.
- `VillageView.tsx` draws them and shows the **Village projects** button.
- `ProjectsPanel.tsx` (new): the current project, the latest meeting and what has been built.

## Project Structure

### Documentation (this feature)

```text
specs/012-building-together/
├── spec.md
├── plan.md              # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
backend/src/agent_lab/village/trade.py (new), build.py (new), meeting.py (new), work.py,
    world.py, turn.py, plan.py, chronicle.py, runner.py
backend/tests/test_village_trade.py (new), test_village_build.py (new),
    test_village_meeting.py (new), test_village_runner.py, test_village_turn.py,
    test_village_work.py, test_village_plan.py, test_village_chronicle.py,
    test_village_world.py, test_village_api.py
frontend/src/lib/api.ts, lib/village.ts (+ test), components/village/building.tsx (new),
    ProjectsPanel.tsx (new), VillageView.tsx
README.md, docs/village.md, docs/api.md, AGENTS.md
```

**Structure Decision**: the existing web application layout. Village rules go in
`backend/src/agent_lab/village/` as one small module per topic; view logic goes in
`frontend/src/lib/village.ts`; drawings go in `frontend/src/components/village/`.

## Complexity Tracking

| Concern | Why accepted | Simpler alternative rejected because |
|---|---|---|
| `runner.py` grows from about 1,080 to about 1,300 lines (principle I: readable in one sitting) | The new rules live in `trade.py`, `build.py` and `meeting.py`. The runner gains only orchestration: when runs start, applying their results, and events and notes, written like the existing plan and reflection code. | Splitting the runner (for example a `meeting_runs.py` mixin) during a feature milestone mixes a refactor into new behaviour. If the owner wants it, it is better done as its own step after M12, behaviour unchanged and covered by the existing tests. |
