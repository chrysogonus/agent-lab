# Research: M15 — Daily Happenings and Boat Trips

The starting point is the M14 village:
- intentions;
- "what you can do here";
- the M13 instruments, with the M14 results as the numbers to keep (waits 28%, 162–172 model
  calls a day).

`runner.py` is 1,331 lines. M14 moved the meeting runs into a mixin; this milestone does the same
for its own runner glue.

## 1. Happenings are chosen from the day (`village/happenings.py`, new, pure)

- **Decision**: `day_happenings(day) -> list[happening]` with
  `random.Random(f"happenings {day}")`, like `trader_stock` and `weather`.
  - **How many**: one happening, or two with a 40% chance, never two of the same kind.
  - **When they are set**: when the first villager wakes, as the day record opens. The list
    replaces yesterday's in `world["happenings"]`.
  - **The catalogue**: a short fixed one written for the four villagers:

  | Kind | Place and time | Concerns | Details from the catalogue | Dealt with when |
  |---|---|---|---|---|
  | letter | the villager's door, 08:00 (postman there 07:30–08:00) | one villager | news from outside (2–3 per villager: a cousin's wedding, prices in town …) | the villager is at its door: it reads the letter (no decision needed) |
  | visitor | the host's door from 13:00 to 19:00 | the host | name and relation ("Anna, Greta's sister") | the host spends an hour next to the visitor (the visitor follows the host once met) |
  | animal | a place, 09:00 to 19:00 | its owner | "Greta's goat", "Jonas's dog" … | someone leads it to the owner's door |
  | repair | fields, pier or flower garden, from waking to the end of the day | the place | "the fence at the fields", "the boards of the pier", "the garden gate" | an hour of work there |
  | peddler | the square, 10:00 to 15:00 | nobody | one curiosity (a lantern, a fiddle, a book of songs, a kite) | someone trades a basket for it |

- **Clashes**: on a meeting day nothing runs past 16:30, apart from the visitor, who stays with
  the host. On the festival day there is no peddler.
- **Why**: the same village day gives the same happenings, so checks, scenarios and replays agree.
  Happenings need no model calls: they are moved by fixed rules, like the trader.
- **Alternatives**:
  - a "storyteller" agent inventing happenings: rejected, because it adds calls and breaks
    reproducibility;
  - random per run: rejected for the same reason.

## 2. How villagers meet a happening

- **Seen**: a villager within sight of a happening while it is here gets the event "You see a
  lost goat at the market (Greta's)." and the trigger `happening`, once per happening. The
  observation lists it under the facts ("Happening here: …").
- **Concerned**: the villager it concerns is told when it starts, wherever it is:
  - "A letter waits for you at home.";
  - "Anna, your sister, is coming this afternoon."
- **Told**: by other villagers' lines, as claims. No new mechanism is needed.
- **Dealing with it** needs one new answer, `{"action": "lead"}` (lead the animal next to you
  home). Everything else uses existing answers:
  - work at the broken place mends it first;
  - `buy` with the curiosity at the square trades for it;
  - reading the letter and keeping the visitor company take no answer.

  "What you can do here" offers each of these when it is possible. `lead` starts an intention
  (go to the owner's door) with the animal following.
- **Ends**: dealt with (by whom) or passed. Each start and end is a note, and the chronicle
  prompt opens the day's events with "Today: …".

## 3. Repairs slow goods

- **Decision**: while a repair is open at a place, a basket there takes twice the work.
  - Work at the place goes into the repair first; an hour of work, added up, mends it.
  - It shares the place's harvest counter rules: everyone working there adds up.
- **Why**: it makes the broken thing matter, and gives a reason to come and help.

## 4. Keepsakes

- **Decision**: per villager `keepsakes: [{name, day}]`. A keepsake is traded for a basket at the
  peddler and does not occupy the hands. It is remembered (kind `keepsake`, importance 3) and
  shown in the panel.

## 5. Boat trips (`village/boat.py`, new, pure)

- **Decision**: `world["boat"] = None | {"rowers", "invited", "left", "back", "at"}`.
  - **New answer**: `{"action": "row", "with"?: "Greta", "until"?: "15:00"}` at the pier, only
    when:
    - the boat is built;
    - it is not out;
    - the weather is not a storm;
    - the villager stands at the pier.
  - **The trip**: lasts until `until`, or an hour, and is back by bedtime.
  - **"with"**: names a villager next to the rower. That villager gets the event "Jonas asks you
    to come out in the boat" and the trigger `invited`. It joins only by its own `row` answer
    within two steps; the boat waits at the pier for that long ("boarding").
- **On the lake**:
  - the rowers stand on the boat's cell, which moves one cell a step along a fixed loop of lake
    cells and comes back to the pier at the end;
  - rowers do not walk;
  - `work` in the boat fishes the lake (`lake` in GOODS and the harvest counter), with a basket
    in 3 steps instead of 6;
  - the talk of two rowers does not end by silence while they are out;
  - both remember the trip (kind `boat`, importance 4);
  - notes say "Jonas and Greta rowed out on the lake." and "… came back to the pier."
- **Why**: the built boat gets a use, and a lasting shared conversation, with the same
  intentions machinery (a `row` intention until the trip ends).
- **Alternatives**: a boat that villagers walk on as a place was rejected: lake cells are not
  walkable, and the path finder would need to change.

## 6. Whispers

- **Decision**: `POST /village/villagers/{name}/whisper {"text"}`. The runner's `whisper(name,
  text)` checks:
  - the text is stripped and 1–200 characters;
  - the villager has had fewer than 3 whispers that village day.

  Delivery when awake:
  - the inbox gets `{"from": "a voice", …}`, shown under "what others told you" as a claim;
  - the event `whispered`;
  - the trigger `whispered`;
  - the note "A voice whispered to Greta."

  When asleep, the whisper is kept and delivered on waking. The decision answering it carries
  `"after_whisper": true` in its `village_action`, so the turn list shows "after a whisper" and
  health counts what followed.
- **Why**: the owner takes part through the same channel as any line heard, so the villager
  treats it as a claim, and every effect is visible in traces.
- **Security**: the owner's own text, bound to 127.0.0.1 like the rest; it is length-limited,
  marked as a claim, and never executed.

## 7. Measuring

- **New checks** (fixtures gain `happenings` and the existing `built`):
  - `animal-lead`: next to Greta's goat, expect `lead`;
  - `repair-mend`: Jonas at the pier with broken boards, expect `work`;
  - `peddler-curiosity`: Lina with flowers next to the peddler, expect `buy` of the curiosity;
  - `letter-pass-on`: Lina has read a letter and Hilde talks to her, expect `say`;
  - `visitor-host`: Greta at the fields with her sister waiting at her door, expect going home;
  - `take-the-boat`: Jonas at the pier, the boat built, his plan saying "boat trip", expect
    `row`.
- **New scenario**: `boat-trip`, with the boat built and Jonas and Greta at the pier at 14:00.
  The condition `boat_trip` holds when a trip happens by 16:00; the result says whether it was a
  trip together.
- **Health**: per day:
  - happenings, and the share dealt with (from notes);
  - boat trips (from notes);
  - whispers, and how many were followed by a decision other than wait.

## 8. Size of the runner

- **Decision**: the runner glue goes into a mixin `village/happening_runs.py` (`HappeningRuns`):
  - starting the day's happenings;
  - their step: arrive, notice, follow, end;
  - leading;
  - boarding, rowing and coming back;
  - whispers.

  The pure rules live in `happenings.py` and `boat.py`. `runner.py` only gains the calls.
