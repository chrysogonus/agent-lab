# Research: M11 — Plans and Purpose

## 1. Daily plans (new `village/plan.py`)

- **Decision**: a shared "Village planner" block agent (model block `plan` + check
  `answer-is-json`), created by `ensure_agents` once, id in `world["planner_agent_id"]`, kept
  across Reset — the same pattern as the reflection and chronicler agents.
  - **When**: `_schedule` starts a plan run when a villager wakes; `_end_conversation` starts a
    revision for each participant when the conversation had at least 4 lines, the participant is
    awake and not at bedtime, has today's plan and has used fewer than 2 revisions (`REVISIONS`).
    The revision counter goes up when the run starts, so at most two revision runs a day.
  - **Tasks**: `self.plans: dict[str, Task]`, one chain per villager like `self.reflections`
    (a new run awaits the one before); `_settle` waits for them; they never reach `outcomes`.
  - **Stale results**: the run remembers the day it started for; its result is dropped when the
    villager is asleep or the day has changed (a revision from yesterday finishing after the
    morning's waking), so there is one plan per villager per day.
  - **Prompt** (`plan_prompt(world, name, revise=None)`): the persona; sleeping hours and the
    usual day from the routine ("05:00 pier, 11:00 market, 14:00 pier"); the date, weather and
    festival line; how the fields and the garden are doing; the stalls line in autumn; what the
    villager carries; its learnings, views and the 8 memories `recall` ranks highest. A revision
    adds "Your plan so far:" and "The conversation you just had:" with the transcript. Ends with
    "Plan your day. Answer with one JSON object."
  - **Answer**: `{"plan": [{"time": "07:30", "place": "town hall", "purpose": "…"},
    {"time": "11:00", "villager": "Jonas", "purpose": "…"}]}`. `parse_plan` validates the shape
    with pydantic, then per entry: time `H:MM`/`HH:MM` within the day, else dropped; `place`
    resolved like a move (`_place`, "home" allowed) or else `villager` resolved like a find
    (`_name`, not the villager itself), else dropped; purpose stripped and cut to 120, empty
    dropped. Entries are sorted by time and cut to 6; fewer than 2 left → invalid ("a plan needs
    at least 2 entries"). The result is redacted after decoding.
  - **Applied**: `v["plan"] = {"day", "entries": [{minute, place, villager, purpose}],
    "revisions"}`; the villager gets the event "You planned your day." (or "You changed your
    plan.") and the day record notes "Hilde's plan for the day: 07:30 town hall (…); …" so the
    chronicler sees plans. `village_action`: `{"action": "plan", "revision": 0|1|2, "entries":
    ["07:30 town hall: …", …]}` or `{"action": "plan", "revision": n, "reason": …}`. An invalid
    answer keeps the previous plan (or none).
- **Marking** (`plan_lines(plan, minute)`): the current entry is the last one whose time has
  come, the next is the first still to come; the observation shows "Your plan for today:" with
  "- 11:00 see Jonas: ask for fish (now)" and "(next)". The state sends the same indices.
- **Why**: Generative Agents' top-down daily plan, kept small (2–6 entries, no hourly
  decomposition); a shared agent keeps the villagers' own agents and their rules contract
  unchanged apart from §2. The village never moves anyone to follow a plan (spec assumption).
- **Alternatives**: planning inside the villager's own agent with a "plan" action — rejected, it
  mixes two answer shapes in one agent and costs a decision turn at waking; hourly
  decomposition — rejected, too many calls for a local model.

## 2. Facts apart from claims (`turn.py`, `chronicle.py`)

- **Decision**: the observation is regrouped (order inside groups unchanged otherwise):
  1. "What you know for sure:" — date, time, weather (with "this is the real weather"), the
     festival line, where you are and whether you work there, the growing places you know, the
     stalls in autumn, your basket, your hours and usual place, your plan, your goal, next to
     you, in sight, whom you talk with, places with distances.
  2. "What you said lately:" — your last three lines (§3).
  3. "Where the others are, as far as you know:" — only what you saw, or their routine when you
     have not seen them (`seen_text`; `belief_text` stays for the panel).
  4. "What others told you (claims; they may be wrong):" — "Said to you since your last turn:"
     and "Heard about where others are:" with heard beliefs ("- Greta: at the market (Lina said
     at 09:00)").
  5. Learnings, memories, last events (heard events shown as `Jonas said to you: "…"`), the
     question.
- **Rules**: a new `RULES` text adds work and give (§4) and two sentences: "Trust what you see
  over what you hear; the weather you are told is the real weather." and "Follow your plan for
  the day unless something more important comes up." `OLD_RULES = (M7 rules, M9 rules)`;
  `_refresh_rules` replaces whichever one a stored agent still holds verbatim, owner-edited
  prompts are left alone.
- **Chronicle**: the conversation note becomes "Greta and Lina talked; what they said (their
  claims): …"; `chronicle_prompt` heads the list with "What happened (what villagers said are
  their claims, not events; never report a claim as an event; the weather is the one given
  above):". The instruction lives in the prompt, not the agent's system text, so stored
  chronicler agents need no refresh.
- **Why**: Concordia's game master keeps the record of what happens apart from what agents say;
  our observation is the only channel, so the split is a matter of grouping and labels.
- **Alternatives**: filtering weather words out of heard lines — rejected, brittle and it
  censors the villagers.

## 3. No repeated lines (`turn.py`, `runner.py`)

- **Decision**: each villager keeps `said`: its last three lines as spoken (after the
  `SPEECH_SHOWN` cut), updated in `_say`. `same_line(a, b)` compares `re.sub(r"[\W_]+", "",
  text.lower())`. In `parse_action`, a say repeating one of them becomes a wait with "you already
  said that"; a goodbye whose text repeats one keeps the goodbye with `text: None`. The
  observation lists them under "What you said lately:" ("- nothing yet" when empty). `said` is
  kept across days and cleared by Reset.
- **Why**: the speaker's own last lines catch the observed loop (the same question three times)
  without judging others' lines; SC-006 counts the refusals from the runs' `village_action`.

## 4. Work, baskets and the stalls (new `village/work.py`)

- **Decision**:
  - `GOODS = {"pier": "fish", "fields": "vegetables", "flower_garden": "flowers"}`;
    `goods_at(world, place)` gives the goods a place has now: fish always at the pier,
    vegetables when the fields are `ripe` or `harvested`, flowers when the garden is `blooming`,
    else `None`.
  - `work_refusal(world, name)` → reason or `None`: at the fields or the garden anyone may work;
    at the pier Jonas, or anyone while Jonas works there ("only Jonas fishes here; work with him
    while he fishes"); elsewhere "there is no work for you here". Working while talking is
    allowed (spec edge case). Work while already working on the place keeps going (no reason).
  - `v["working"] = {"place", "steps"}` (steps since its last basket). Walking off (`move`,
    `find`, a goodbye with a place or villager) and bedtime end it; say and wait do not.
  - `work_step(world) -> list[(name, goods)]`, called in `_advance` after the moves: for every
    awake villager working on its place, `world["tended"][place] += 1` (fields and garden: the
    working steps of everyone add up, `TENDED_STEPS` stays 6) and `steps += 1`; per place with
    goods, `world["harvest"][place] = min(harvest + workers, 6)`, and at 6 the worker with empty
    hands and the most `steps` (ties: villager order) gets a basket, `harvest` back to 0 and its
    `steps` to 0. A place without goods keeps `harvest` at 0; nobody with empty hands keeps it at
    6 until someone has. Two villagers working together therefore tend a place and fill a basket
    in half the time (SC-003).
  - The runner turns each basket into the event "You filled a basket of fish.", a `basket`
    trigger (the villager may set off to deliver it) and the note "Jonas filled a basket of fish."
  - **Give**: `{"action": "give", "to": "Hilde"}` or `{"action": "give"}`. `parse_action`
    refuses: empty hands ("your hands are empty"); a named villager unknown, not next to you,
    asleep, or with full hands ("Hilde's hands are full"); no name off the square ("nobody to
    give it to: name someone next to you, or stand on the square to set it out for the
    festival"). Applied: the basket moves (events "You gave your basket of fish to Hilde." / "Jonas
    gave you a basket of fish." and a `given` trigger for the receiver), or onto
    `world["stalls"][goods] += 1` ("You set out your fish on the festival stalls."); both noted in
    the day record.
  - **Stalls**: `stalls_text(stalls)` — "The festival stalls on the square hold fish; they still
    lack vegetables and flowers." — in observations and plan prompts in autumn; in the chronicle
    prompt of the festival day; in festival memories ("… The stalls held fish and flowers." or
    "… The stalls stood empty."). `end_day` clears the stalls when winter comes, with the growth.
- **Why**: one module keeps the rules testable without the runner and keeps `runner.py` from
  growing much; counting per worker is the simplest rule where work adds up.
- **Alternatives**: a basket per villager per own hour of work — rejected, cooperation would not
  speed anything up; quantities and money — out of scope (spec assumption).

## 5. World version 5

- **Decision**: `VERSION = 5`. `new_world()` adds per villager `plan: None`, `basket: None`,
  `working: None`, `said: []`; and `stalls: {fish: 0, vegetables: 0, flowers: 0}`,
  `harvest: {pier: 0, fields: 0, flower_garden: 0}`, `planner_agent_id: None`. `upgrade()` chains
  2 → 3 → 4 → 5 with explicit steps; `_load` accepts 2, 3 and 4. Reset keeps all three shared
  agent ids.
- **State**: per villager `plan` (`{entries: [{time, place (label) | null, villager | null,
  purpose}], current, next, revisions}` for today, else `null`), `basket`, `working` (place key
  or `null`) and the new state `working`; world `stalls`. `said`, `harvest` and
  `planner_agent_id` stay internal.

## 6. The view

- **Decision**:
  - `VillagerPanel`: "Today's plan" under the persona, the current entry marked "now" and the
    next "next"; empty text "No plan yet: villagers plan their day when they wake."
  - `lib/village.ts`: `planEntryText`, `stateText` for working ("Working at the fields"),
    `turnLabel` for plan, work and give runs, `stallsText`; vitest.
  - Map (`seasons.tsx`): `Stalls` — three small stalls along the square's lower edge in autumn
    and whenever goods are out, each showing its goods (fish, vegetable crates, flower pots) or
    standing bare; `Basket` — a small basket in the goods' colour next to a carrying villager's
    sprite. `pointer-events: none`, no animation.
- **Why**: same drawing approach as M9/M10; the plan is text, so the panel is the right place.
