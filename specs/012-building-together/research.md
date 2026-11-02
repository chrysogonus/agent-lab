# Research: M12 — Building Together

## 1. The daily trader (new `village/trade.py`)

- **Decision**:
  - `TRADER_ARRIVES = 9 * 60`, `TRADER_LEAVES = 14 * 60` (minutes of the day), `BUILDING_GOODS =
    ("wood", "paint", "saplings")`.
  - `trader_stock(day) -> {wood, paint, saplings}`: drawn with `random.Random(f"trader {day}")`,
    so it is the same every time the day comes, like the weather: wood 2–6, paint 1–3, saplings
    0–3.
  - `world["trader"]`: `{"day", "stock"}` while the trader is at the market, else `None`. The
    runner's new `_trader()` (called in `_advance`) creates it at the first step of a day whose
    minute is in `[09:00, 14:00)` and the trader is not yet that day's (also after a load in the
    middle of the window), and clears it at the first step at or after 14:00. Notes: "A trader came
    to the market with wood (4), paint (2) and saplings (1)." and "The trader left the market (sold 3
    loads)."
  - **Buy**: `{"action": "buy", "goods": "wood"}`. `buy_refusal(world, name, goods)` → reason or
    `None`, in this order:
    1. unknown goods: "the trader sells wood, paint and saplings";
    2. no trader: "no trader is at the market now; one comes every day from 09:00 to 14:00";
    3. not at the market: "the trader is at the market";
    4. out of stock: "the trader has no paint left";
    5. empty hands: "you have nothing to trade: bring a basket";
    6. carrying a load: "you already carry a load of wood".

    Buying while talking is allowed, as work is. Applied: the stock goes down by one, the basket
    goes with the trader, `v["basket"] = goods`. Event "You traded your basket of fish for a load
    of wood.", note "Lina traded a basket of fish for a load of wood."
  - `trader_text(world)` in the observation and plan prompt (in the facts part):
    - before 09:00: "A trader comes to the market today from 09:00 to 14:00.";
    - while there: "A trader is at the market until 14:00, selling wood (4), paint (2) and saplings
      (1); it takes one basket of fish, vegetables or flowers for each load.";
    - after it left: "The trader has left; the next one comes tomorrow at 09:00.".
- **Why**: the owner chose barter (Q1: A). One basket for one load keeps M11's work useful all
  year without money, prices or purses. A deterministic stock keeps tests simple and makes "the
  trader had no paint today" part of the story.
- **Alternatives**: a trader agent that haggles — rejected, it costs model calls for no new
  learning; M13 brings visitors that talk. Coins — rejected by the owner.
- **Seasons**: spring starts with only the pier giving baskets (fields not ripe, garden
  budding), so fish pay for early spring's building; the garden blooms after two watered days
  (worked an hour or rained on) and gives flowers from then on, and vegetables come once the
  fields ripen in summer. This follows from M11's growth rules; the manual check notes which
  baskets paid.

## 2. One carried thing: basket or load (`work.py`, `trade.py`)

- **Decision**: `v["basket"]` keeps its name and now holds any of `fish`, `vegetables`, `flowers`,
  `wood`, `paint`, `saplings`. `BASKET_GOODS = ("fish", "vegetables", "flowers")`.
  `carried_text(goods)` gives "a basket of fish" or "a load of wood", and every text that names
  what a villager carries uses it: events, notes, observation, plan prompt and panel.
  - Give to a villager works for any goods, as before.
  - Give without a name:
    - on the square, only `BASKET_GOODS` go onto the stalls ("the festival stalls take fish,
      vegetables and flowers");
    - at the current project's site, only loads the project still needs (§4);
    - anywhere else: `NO_GIVING`, which gains "or stand at the building site to set down a load".
- **Why**: one carried thing is already the M11 rule. Keeping the field avoids a rename through
  the API, frontend and upgrade for no behaviour change. The cost is a field name that no longer
  says everything, which a one-line comment in `world.py` and the contract record.
- **Alternatives**: a separate `load` field with "one of the two" checks everywhere — rejected,
  more code for the same rule; renaming to `carrying` — rejected for now, a pure rename with an
  API change.

## 3. The catalogue and the sites (new `village/build.py`)

- **Decision**: `CATALOGUE` is a tuple of plain dicts:
  `{key, name, kind, needs: {goods: n}, site: [cells], at: [cells]}`.
  - `kind` (`paint`, `trees`, `stand`, `building`, `boat`) tells the view how to draw it.
  - `site` holds the walkable cells villagers stand on to deliver and build.
  - `at` holds where the result is drawn.

| key | name | kind | needs | site | drawn at |
|---|---|---|---|---|---|
| `paint_town_hall` | Paint the town hall | paint | paint 2 | the town hall's cells | the town hall building |
| `paint_hilde` | Paint Hilde's house | paint | paint 2 | Hilde's door (9, 3) | her house |
| `paint_jonas` | Paint Jonas's house | paint | paint 2 | Jonas's door (26, 15) | his house |
| `paint_greta` | Paint Greta's house | paint | paint 2 | Greta's door (9, 16) | her house |
| `paint_lina` | Paint Lina's house | paint | paint 2 | Lina's door (26, 3) | her house |
| `trees_square` | Plant trees by the square | trees | saplings 3 | (18, 10), (20, 10), (22, 10) | the same cells |
| `market_stand` | A market stand | stand | wood 3, paint 1 | the market's cells | beside the market (26, 8) |
| `boat` | A rowing boat | boat | wood 4, paint 1 | the shore (16–18, 16) | the water by the pier (20, 17) |
| `bakehouse` | A bakehouse on the meadow | building | wood 14, paint 3 | (14–16, 12) | plot `b` (14–17, 13–14) |
| `barn` | A barn by the fields | building | wood 16, paint 3 | (10–12, 16) | plot `r` (9–12, 17–18) |

  - **Plots**: the map gains two fenced building plots, letters `b` and `r` in `ROWS`. They join
    `BLOCKED`, like the houses, so a finished building never has villagers walking through it,
    and the cached path search stays static. A check over the map confirmed every walkable cell
    is still reachable with both plots blocked (541 of 541).
  - **Planted trees and stands**: these are decorations and do not block. The code carries the
    comment `shortcut: planted trees do not block walking, block them if villagers visibly walk
    through them`.
  - **The site as a place**: while a project runs, its site is a destination. `move` accepts
    "building site" (or "site"), `steps_to` lists "building site N steps" under Places, and
    `site_at(world, cell)` says whether a cell is on the current site. Without a project, "the
    building site" is refused like an unknown place ("nothing is being built").
  - `needs_left(world)`: the loads still to deliver, per goods: `needs[g] - site[g] - used[g]`.
    The project keeps what it used per goods (`used`), not just a count, because loads arrive in
    any order; how far along it is (`done`) is `sum(used)`.
  - `project_text(world, name)` gives the observation lines:
    - "The village is building: Paint the town hall (the site is at the town hall). It still
      needs 1 paint; the site holds 1 paint; 1 of 2 loads worked in.";
    - "Hilde asked you to: buy paint from the trader; bring paint to the site.", or "Nothing is
      asked of you; you may still help.";
    - "Built so far: Paint Lina's house, A market stand." when anything is.
- **Why**: fixed sites keep every project testable and drawable. A temporary place for the site
  means villagers do not need a new kind of move.
- **Alternatives**: buildings placed anywhere by the model — rejected, invalid positions and
  blocked paths; permanent named places for all ten sites — rejected, they would crowd the
  Places line every turn.

## 4. Building work (`build.py`, `work.py`)

- **Decision**:
  - **Delivering**: `give` without a name on a site cell puts the load on the site,
    `project["site"][goods] += 1`, when `needs_left` still has it. Otherwise the villager waits:
    "the building site does not need paint" or "the building site has all the wood it needs".
    Events "You set down a load of paint at the building site." and a note.
  - **Working**: `work_refusal` first checks `site_at`. On the site the villager works while
    the site holds loads; without loads it is refused: "the building site has nothing to work
    with yet: bring goods first". Working there sets `working = {"place": "site", "steps"}`.
  - `build_step(world) -> str | None`, called in `_advance` right after `work_step`:
    1. the working steps of everyone at the site add up in `project["work"]`, but only while
       loads lie there;
    2. at `BASKET_STEPS` (6, one village hour), one load lying at the site is used (goods in
       catalogue order among those lying there): `site[g] -= 1`, `used[g] += 1`;
    3. when `used` equals `needs`, the project is finished and its key is returned.
  - **Finished**: `world["built"].append({"key", "day"})` and `project = None`. Each worker
    stops working. Every villager gets the event "The town hall has been painted!" (the
    catalogue's `done_text`), and awake villagers remember it (kind `built`). The day record
    notes it, and the chronicle hears it through the note.
- **Why**: building is work at a new place with the same counting as M11. Working together
  speeds it up, and the loads tie the trader, the carrying and the work together. The longest
  waking day is 16 hours (Jonas 05:00–21:00, Greta 05:30–21:30), so a building of 17 or more
  loads takes more than a day of one villager's work even on a fully stocked site (spec
  assumption); a scripted test checks it.

## 5. The meeting (new `village/meeting.py`)

- **Decision**:
  - **When**: `meeting_day(day)` is `day % 3 == 0` and not the festival day, or the day after a
    festival day that was divisible by 3 (year 1: day 21 → 22). `MEETING_OPENS = 17 * 60`,
    `MEETING_CLOSES = 17 * 60 + 30`.
  - **One shared agent**: "Village meeting" (`meeting_agent()`, model block + `answer-is-json`
    check). `ensure_agents` creates it once and keeps its id in `world["meeting_agent_id"]`
    across Reset. It serves four prompts, and each prompt ends with the one JSON shape it wants;
    the system text describes all four, so the owner can edit one agent.
  - **Proposals**: on a meeting day, when Hilde wakes and no project is unfinished,
    `proposal_prompt(world)` is run for her (tagged Hilde). The prompt holds:
    - her persona and the date;
    - what is built;
    - the projects left, with their needs;
    - the trader's usual goods;
    - her learnings and memories.

    Answer: `{"proposals": [{"project": "A market stand", "reason": "…"}]}`. `parse_proposals`
    matches each project by name or key (case and "the" ignored), drops unknown, built or
    repeated ones, cuts reasons to 120 characters and keeps at most 3. None left → invalid ("no
    project Hilde proposed can be built"). The catalogue has fewer than 2 left → 1 is enough.
    Applied: `world["meeting"] = {"day", "kind": "vote", "proposals", "votes": {}, "present": [],
    "decision": None, "outcome": None}`, event "You proposed: …" and a note. Invalid → `outcome:
    "called off: Hilde had no proposals"`.
  - **Review**: on a meeting day with an unfinished project, the meeting is `kind: "review"` with
    no proposals.
  - **Nothing left**: if the catalogue is empty, `outcome: "nothing left to build"`.
  - **Told**:
    - `meeting_text(world, name)` in observations and plan prompts on a meeting day: "Today at
      17:00 the villagers meet at the town hall to choose what to build next. Hilde proposes: A
      market stand (…); Paint Lina's house (…)."
    - Hilde instead reads "You chair today's town hall meeting at 17:00; be there."
    - For a review: "… to talk about how the building goes."
    - After the meeting: what came of it.
    - On other days: "The next town hall meeting is on day 9."
  - **Attending**: `_meeting()` is called in `_advance` after `_festival_guests`. From 17:00 to
    17:30, every awake villager on a town hall cell joins `present` (note "Greta came to the town
    hall meeting."). Each villager but Hilde who joins a vote meeting gets one vote run.
  - **Votes**: `vote_prompt(world, name)` holds:
    - the persona, learnings and views;
    - the memories `recall` ranks highest;
    - the proposals with Hilde's reasons.

    Answer: `{"vote": "A market stand", "reason": "…"}`; a vote for anything not proposed is
    invalid. `village_action` is `{"action": "vote", "project", "reason"}` or `{"action":
    "vote", "reason": why}`.
  - **Decision**: at the first step at or after 17:30 with no vote run in flight and no
    `outcome`:
    - if Hilde is not in `present`, the outcome is "called off: Hilde did not come";
    - otherwise `decision_prompt` is run, holding her persona, the proposals, each vote with its
      reason, and the tally.

    Answer: `{"decision": "A market stand", "reason": "…"}`. `parse_decision` accepts only a
    proposal. When it is invalid, the most valid votes decide (ties: proposal order), recorded as
    "Hilde gave no valid decision; the vote decided". With no votes either, there is no decision.
    `against` is true when the decided project is not among the most-voted ones. Applied:
    - `meeting["decision"] = {"project", "reason", "against"}`;
    - `world["project"] = new_project(key)`;
    - every villager gets the event "At the town hall meeting Hilde chose A market stand: …",
      plus " She went against the vote (most wanted Paint Lina's house)." when `against`;
    - attendees remember the meeting (kind `meeting`);
    - the note, then the work-plan run.
  - **Work plan**: `work_plan_prompt(world)` holds:
    - Hilde's persona and the project;
    - `needs_left` and the site;
    - today's trader stock, or "the trader comes tomorrow at 09:00";
    - every villager's work place, hours and what it carries;
    - for a review, the progress and the previous tasks.

    Answer: `{"tasks": [{"task": "buy", "goods": "paint", "villagers": ["Jonas"]}, {"task":
    "bring", "goods": "paint", "villagers": ["Jonas"]}, {"task": "build", "villagers": ["Greta",
    "Lina"]}]}`. `parse_tasks`:
    - `task` must be one of buy, bring, build;
    - goods are required for buy and bring and must be building goods;
    - villagers are resolved with `villager_named` and unknown ones dropped;
    - a task with nobody left is dropped;
    - at most 6 tasks, and none left → invalid.

    Applied: `project["tasks"] = tasks`, event "Hilde asked you to …" for each named villager and
    a `task` trigger, and a note. On a review meeting it runs at 17:30 when Hilde came. Tasks stay
    until the project is done or a review replaces them.
  - **Hints from the first real-model run** (as M11's delivery hint): a villager carrying a
    load the project still needs is told "Take your load of wood to the building site (…) and
    set it down there" (or, at the site, "set down your load … now with {"action": "give"}"),
    and one at a site holding loads, not yet building, "build here with {"action": "work"}";
    at 16:30 every villager up and away from the town hall gets a `meeting` event and trigger
    with the move to make (or the goodbye, when talking). Without them only one load was set
    down in six days and two villagers came to the meeting. A second run showed Hilde held in a
    talk at 17:00 and, another day, too far away to arrive by 17:30: the call moved to 16:30,
    and the meeting waits for Hilde until 18:30 (`HILDE_WAITED`) before it is called off. A
    third run showed her walking from 16:30 and held in talks with villagers she met on the
    way until 18:40: walking to today's open meeting now goes on while talking, as the walk
    home at bedtime does, and the talk ends when they walk apart.
  - **Asking again**: an unusable proposal or work-plan answer (a run that failed, often JSON
    missing its last brace on the real model, or nothing usable in it) is asked for once more;
    the first run records the reason with "; asked again". A missed proposal would cost the
    village three days. Votes are not asked again (an invalid vote is not counted) and the
    decision falls back to the vote.
  - **Runs**: `self.meetings: dict[str, Task]`, keyed by `"propose"`, `"decide"`, `"tasks"` or
    `"vote:<name>"`. As with plans, these runs never count as decisions or toward the failure
    pause, `_settle` waits for them, and a result arriving during Reset or for an old meeting day
    is dropped.
- **Why**:
  - The owner chose this flow (Hilde proposes, the others vote, Hilde decides, Hilde hands out
    the work) and Q2: A (she may overrule with a reason).
  - Shared agents keep the villagers' own decision prompts and answer shapes unchanged apart
    from buy.
  - The fallback to the vote keeps the village moving when a small model answers badly.
- **Alternatives**:
  - votes through each villager's own agent — rejected, it mixes a second answer shape into the
    decision agent (M11 research §1, the same reasoning as the planner);
  - one agent per meeting step — rejected, four agents in My agents for one feature;
  - deciding and handing out tasks in one answer — rejected, review meetings need the work plan
    alone.

## 6. Villager rules, plans and the chronicle

- **Rules**: a new `RULES` text adds buy and the building site:
  - `{"action": "buy", "goods": "wood"}` at the market while the trader is there, paying with a
    basket;
  - `give` without a name at the building site to set down a load;
  - `work` at the building site to build;
  - one sentence: "Hilde holds a town hall meeting every third day at 17:00 where the village
    chooses what to build."

  `OLD_RULES` gains the M11 rules text (renamed `_M11_RULES`). Stored agents holding it verbatim
  get the new text; owner-edited prompts are left alone.
- **Planner**: `plan_prompt` adds `trader_text`, `meeting_text` and `project_text` (with the
  villager's own tasks) after the growth lines. The planner agent's system text gains "Fit in
  what Hilde asked of the villager and the town hall meeting." Stored planner agents still
  holding the M11 `PLAN` text verbatim get the new one on load (`_refresh_planner`, the same
  pattern as the rules).
- **Chronicle**: no prompt change. The day record carries:
  - trader visits and trades;
  - proposals, votes (as claims: "Greta voted for A market stand: …") and the decision;
  - deliveries and finished projects.

  `chronicle_prompt` adds "Built so far: …" so the chronicler knows what stands in the village.
- **Memories**: two new kinds, `meeting` (attendees: "The town hall meeting: we chose A market
  stand; I voted for it.") and `built` (everyone awake: "The town hall has been painted.").
  `recall` treats them like other memories.

## 7. World version 6

- **Decision**: `VERSION = 6`. `new_world()` adds:
  - `trader: None`;
  - `meeting: None`;
  - `project: None`;
  - `built: []`;
  - `meeting_agent_id: None`.

  `upgrade()` gains an explicit `if version == 4` step for the M11 fields (today they are added
  unconditionally at the end), then the version 5 → 6 step. Upgrading also moves any villager
  standing on a new plot cell to the plot's first site cell, so no one stands inside a blocked
  cell. Reset keeps all four shared agent ids and clears `built`.
- **State**:
  - `trader` (`{stock, leaves: "14:00"}` or `null`);
  - `meeting` (the latest: day, kind, proposals with names, votes, present, decision, outcome);
  - `project` (key, name, needs, site holds, used, done, total, tasks);
  - `built` (keys with names and days);
  - `next_meeting` (the day of the next town hall meeting);
  - `map.catalogue` (`[{key, name, kind, site, at}]`, the static drawing data);
  - `meeting_agent_id` stays internal.

## 8. The view

- **Decision**:
  - New `components/village/building.tsx`:
    - `Trader`: a cart with a figure at the market's free corner while it is there, showing
      piles of its goods;
    - `Site`: scaffolding and the loads lying there, on the current project's cells;
    - `Built`, by kind:
      - paint: a fresh colour over the house or town hall roof;
      - trees: young trees;
      - stand: a striped stall;
      - building: a small house on the plot;
      - boat: a boat moored by the pier;
    - `Load`: a carried load, beside the figure, like `Basket`.

    Plots are drawn as fenced grass until built. All of them use `pointer-events: none` and no
    animation, as M10 and M11 do.
  - `lib/village.ts` (+ vitest):
    - `cellKind` knows the plot letters;
    - `carriedText` and `traderText`;
    - `projectLines` and `meetingLines`;
    - `turnLabel` for buy, propose, vote, decide and assign.
  - New `ProjectsPanel.tsx`, opened with **Village projects** next to **Read the chronicle**.
    It shows the current project (needs, site holds, progress bar, tasks), the latest meeting
    (proposals, each vote with its reason, the decision, "went against the vote") and the list
    of what has been built with days. Each meeting run links to its trace.
- **Why**: the same drawing approach as M9–M11; meetings and tasks are text, so a panel is the
  right place, as for the chronicle.
