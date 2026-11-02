# Research: M14 — Better Villagers

The baseline, from `specs/013-measuring-the-village/tasks.md`, "Manual check results":

| Measure | Baseline |
|---|---|
| "there is no work for you here" | 6.1 per 100 decisions |
| "<villager> is not next to you" | 7.3 per 100 decisions |
| "say goodbye first" | 6.1 per 100 decisions |
| waits | 45% of decisions |
| `build-with-loads` | 0/40 |
| `work-at-own-place` | 11/40 |
| `meeting-call-talking` | 27/40 |
| `talk-then-go` | 0/5 |

What the failing turns show:

- **The wrong action for the place.** Greta at a building site that held saplings walked to the
  market, her midday routine, instead of building. In other turns villagers tried to `work` on
  a path. The prompt tells them what is around them, but never plainly what they can do here and
  now.
- **Lost track.** A villager that started working is asked again every 30 minutes, and often walks
  off. Each turn starts from scratch.
- **Held by talk.** "Say goodbye first" refusals; Hilde was held in talks on her way to the meeting
  until the meeting was over.
- **Talking from afar.** Say to someone "in sight" fails with "not next to you", and find refuses
  "already next to you".

## 1. Intentions (`village/intention.py`, new, pure)

- **Decision**: a villager holds at most one intention, `v["intention"]`:
  `{kind, place, villager, until, purpose, since, say}`.
  - **kind**: go (move), work (work at a place), build (work at the site), bring (take the load
    to the site and set it down), or see (find someone).
  - **until**: a minute of the day, or null.
  - **say**: a line to say on reaching the villager, or null.

  The existing actions become intentions, and two short verbs are added:

  | Answer | Intention | Done when |
  |---|---|---|
  | `{"action": "move", "place": "pier"}` | go | arrived |
  | `{"action": "work", "place"?: "fields", "until"?: "12:00"}` | work (here, or walk there first) | `until` comes; or it walks off |
  | `{"action": "build", "until"?: "15:00"}` | build (walk to the site first) | `until` comes, or the site holds no loads and none are on the way, or the project is finished |
  | `{"action": "bring"}` | bring (walk to the site, set the load down) | set down |
  | `{"action": "find", "villager": "Greta", "say"?: "Got fish?"}` | see | next to her, then the line is said |

- **Steps**: `next_step(world, v) -> Step` is pure, and is one of:
  - `walk` (to the target's cells);
  - `start_work`;
  - `set_down`;
  - `say`;
  - `done`, `given_up` with a reason, or `none` (keep at it).

  The runner applies each step where the village used to wait for a decision. The certain steps
  need no model call: walking, starting work on arrival, setting a needed load down at the site,
  and saying the stored line next to the villager.
- **Asked only when something happens**:
  - an idle re-decision (`IDLE_STEPS`) happens only for villagers without an intention;
  - triggers (spoken to, met, found, missed, basket, task, meeting, built) still ask;
  - "arrived" does not ask when the intention goes on (work or set down follows).

  This is how waits fall (SC-004).
- **Ends**:
  - `done`, with the reason ("you set down the saplings", "noon came", "you found Greta");
  - `given_up` ("the project was finished", "Greta is asleep", "you lost sight of Greta", "the
    day is over" at bedtime);
  - `replaced` (the next answer that starts an intention).

  Each end is an event and a note: "Greta stopped building: noon came." The decision run's
  `village_action` keeps the intention it started.
- **Why**: villagers lose track of what they were doing because every turn starts from scratch;
  storing the intention and taking the certain steps keeps them at it. The answer shapes stay
  close to the existing ones, so a small model keeps answering well.
- **Alternatives**:
  - a separate "intend" action naming a kind — rejected: it is one more shape, and `work` and
    `move` already say the kind;
  - planning several steps ahead — rejected: the daily plan already does that.

## 2. What you can do here (`village/affordances.py`, new, pure)

- **Decision**: one section of the observation, "What you can do here:", replaces the scattered
  hints (`delivery_text`, the site hints, the buy hint, "build here"). It lists the actions that
  would be accepted right now, each as exact JSON with a short why. It is computed from the same
  refusal functions the parser uses, so it can never offer something that would be refused.
  Examples:
  - `{"action": "work"}`: you can work the fields here (they are growing);
  - `{"action": "build"}`: the site holds 2 saplings;
  - `{"action": "bring"}`: you carry wood the project needs;
  - `{"action": "buy", "goods": "saplings"}`: the trader has 2 left;
  - `{"action": "give"}`: set out your fish on the festival stalls;
  - `{"action": "say", "to": "Greta"}`: Greta is next to you.

  At most 6 entries, in that order. Moves are not listed: the places are listed with distances.
- **Why**: the failed turns tried actions the place did not allow ("no work for you here",
  "already next to you"). One honest list covers trade, work and the stalls, and lets the M11 and
  M12 hints go, so the prompt gets shorter instead of longer.
- **Rules refresh**: the villager rules change (§6). The hint texts leave the observation;
  `delivery_text` stays only for the planner's autumn line.

## 3. Reaching each other

- **Following** (exists in part). A find already re-aims at the person while they are in sight.
  It now ends as given up, "you lost sight of Greta", when they go out of sight (with the last
  place seen), rather than walking to an empty cell.
- **Say from afar**: in `parse_action`, a say whose `to` is awake and in sight but not next to the
  speaker becomes `{"action": "find", "villager", "say": text}` instead of a refusal. A say to
  someone out of sight keeps its refusal.
- **Find someone next to you**: a find of someone already next to you becomes a wait without a
  refusal ("Greta is right next to you; talk to her"). The affordance list shows say to her.
- **Give to a villager** (FR-007): accepted when the receiver is the giver's intention target
  (see), or asked for those goods within the last hour. Otherwise it is refused, with what the
  goods are for: "your wood belongs at the building site", "set your fish out on the stalls or
  keep it", "Hilde did not ask for it". A **request** is noted when a line heard by the giver,
  from the receiver, names the goods ("…any fish?"): `v["requests"] = [{from, goods, tick}]`,
  kept for 6 steps.
- **Next to you / in sight**: the observation already separates the two. The lines stay, but now
  give names only ("Next to you: Greta. In sight: Hilde (4 steps away).") and drop titles, so
  names match what answers must use.

## 4. Leaving a talk

- **Decision**: a talking villager whose answer starts an intention elsewhere (move, find, work
  somewhere else, build away, bring) says goodbye and sets off. `parse_action` turns it into a
  goodbye with the intention attached, instead of the refusal "say goodbye first".
  - Walkers with an intention walk while talking (`_walks`). The talk ends when they walk apart
    (`_upkeep`, "you walked apart"), as it already does.
  - Two talkers going to the same place stay next to each other on the shared path, so their talk
    goes on.
  - The special cases `_to_meeting` and bedtime walking become this rule. Bedtime is an intention
    to go home, and the meeting call suggests `move` to the town hall.
- **Why**: one rule instead of two special cases, and the 6.1 refusals per 100 decisions go away
  by construction.

## 5. Memory

- **Season weight**: `score` subtracts 3 from a memory that is from another season and not about
  anyone at hand. Recency already fades within the day (15% per hour); importance (festival 5,
  reflection 5) kept old festival memories on top all year.
- **Summaries**: when a villager has more than 5 reflections older than 3 days, its night
  reflection prompt adds "Your older reflections:" and asks for an extra `"summary"` field.
  - The summary replaces those reflections as one memory of kind `summary` (importance 4).
  - The reflection agent's system text gains one sentence about the field. Stored reflection
    agents holding the M8 text verbatim get the new text (`OLD_REFLECT`, as for the rules).
  - This takes no extra run (FR-012: at most one more, here none).
- **Weather talk**: `chronicle_prompt` appends "(talk, not the day's weather)" to a note that
  names weather the day did not have (`weather_slips` on the note). Conversations are already
  marked as claims.

## 6. Rules, version, measuring

- **Rules**: a new `RULES` adds build, bring, work with place and until, and find with say. It
  says "you keep doing what you set out to do until it is done; you are asked when something
  happens", and drops "While you talk with someone, you both stay where you are…". The M12 text
  joins `OLD_RULES`.
- **World version 7**: per villager `intention: null` and `requests: []`. `upgrade` gets a 6 → 7
  step. **The version bump and `_load` change in one write, with `make dev` stopped and the
  database backed up** (memory note).
- **New checks** (FR-014), all fixtures:
  - `intention-keeps-building`: building with loads, asked after a "met", should not walk off;
    expect not move or find;
  - `say-to-someone-in-sight`: expect a find of Greta with a line;
  - `leave-talk-for-intention`: talking at 10:55, a plan entry at 11:00 elsewhere; expect not a
    wait;
  - `summer-plan-without-festival`: the planner in summer with old festival memories; a new
    expectation kind `excludes: ["festival"]` checks the answer text.
- **The M13 checks** keep running unchanged as the baseline. Some prompts change by design (the
  affordance list). That is the change being measured, because fixture checks build prompts with
  today's code.

## 7. Size of the runner

`runner.py` is 1,533 lines, over "readable in one sitting" (principle I), and M14 touches its
step loop.

- **Decision**: a first phase moves the meeting runs (about 330 lines: `_meeting` to `_assign`)
  into `village/meeting_runs.py` as a mixin, with behaviour unchanged and every test green
  (code-simplification). Intention steps go into the new `intention.py`.
- **Why**: the M12 plan deferred this split "after M12, behaviour unchanged". M14 changes the
  loop, so it is the time.
