# Research: M10 — Village Seasons

## 1. Pace

- **Decision**: a frontend-only change. `PACES` in `lib/village.ts` (Slow 15 s, Normal 5 s, Fast
  2 s) drawn as three toggle buttons (`aria-pressed`) in place of the seconds field; a click calls
  the existing `PUT /village/interval`. `paceOf(interval)` returns the matching pace or `null` (a
  stored 7 s marks none). The status reads "Running at Normal pace".
- **Why**: the backend already accepts 1–30 s and the model comes from each agent's own config, so
  the pace cannot touch the model (FR-002) without new code.
- **Alternatives**: a backend `pace` field — rejected, it duplicates `interval`.

## 2. Calendar, light and weather (new `village/seasons.py`)

- **Decision**: everything is derived from the village day, nothing stored:
  - `date(day) -> (year, season, day_of_season)`: `SEASONS = ("spring", "summer", "autumn",
    "winter")`, `DAYS_PER_SEASON = 7`, day 1 is day 1 of spring.
  - `festival_in(day) -> int | None`: days until autumn day 7 while in autumn (0 on the day).
  - `SUN = {spring: (06:00, 20:00), summer: (05:00, 21:30), autumn: (06:30, 19:00), winter:
    (08:00, 17:00)}`; `sky(day, minute)` gives one of the five existing sky keys shifted by the
    season (night until 30 min before sunrise, morning until 11:00, midday until 14:00, afternoon,
    evening from 2 h before sunset until 30 min after it); `dark(day, minute)` is before sunrise
    or after sunset. The villagers' `period` stays as it is (their routines use it).
  - `weather(day)`: `random.Random(day).choices(kinds, weights)` from `WEATHER[season]`
    (spring sun 4 · clouds 3 · rain 3; summer sun 6 · clouds 3 · storm 1; autumn clouds 3 ·
    rain 3 · fog 2 · storm 1 · sun 1; winter clouds 3 · snow 3 · fog 2 · sun 2); the festival day
    uses sun 1 · clouds 1. A seeded stdlib generator per day is reproducible across runs and
    resets (SC-002) and needs no storage.
  - `snow_cover(day)`: snow today or yesterday.
- **Why**: deriving keeps the world row small and makes weather trivially testable.
- **Alternatives**: storing a forecast list — rejected, nothing to keep in sync.

## 3. Growth (`seasons.py`, applied by the runner)

- **Decision**: `world["growth"]` holds `{fields: {stage, progress, untended}, flower_garden:
  {stage, watered, dry}}` and `world["tended"]` counts, per place, the steps of the current day
  in which at least one awake villager stood on it. When the first villager wakes (the moment the
  next day's record opens) the runner calls `end_day(world, yesterday)` and notes its news as
  "Overnight: …", so growth news reaches the chronicle of the day it shows on the map; nobody
  is awake between midnight and the first waking, so nothing is counted twice:
  - A place is tended with `tended >= 6` (one village hour in total); the garden is watered if
    tended or the weather was rain or storm.
  - Fields (outside winter): tended → resting→tilled, tilled→sown; in sown, sprouting and growing,
    progress += 2 on rain or storm, else 1, and the stage advances at 3 (sown→sprouting), 5
    (sprouting→growing) and 6 (growing→ripe), progress back to 0; ripe and tended in autumn →
    harvested. Untended days count up (`untended`), a tended day resets them; neglected =
    sprouting, growing or ripe with `untended >= 2`.
  - Garden (outside winter): watered → `watered += 1`, `dry = 0`, budding with 2 watered → blooming,
    wilting → blooming; dry → `dry += 1`, blooming with `dry >= 2` → wilting.
  - Then the new day: first day of winter → fields resting (ripe ones lost, noted in the day
    record), garden resting; first day of spring → garden budding.
  - Every stage change is noted in the day record ("The fields sprouted.").
- **Numbers check** (SC-003): tended daily without rain, fields are tilled day 1, sown day 2,
  sprouting day 5, growing day 10, ripe day 16 (autumn day 2), harvested day 17, before the
  festival on day 21; rain only brings ripeness forward (harvest still waits for autumn).
- **Why**: one state per place, updated once a day, keeps it cheap and easy to test; counting
  steps with anyone present follows the spec's "awake villagers … in total".

## 4. What villagers are told (`turn.py`)

- **Decision**: the observation's first line becomes "Day 17 (day 3 of autumn, year 1), 09:40,
  morning. Rain all day." (weather texts: sun "Sunny", clouds "Cloudy", rain "Rain all day",
  storm "A storm with thunder and heavy rain", fog "Thick fog", snow "Snow is falling"). Then, when
  it applies:
  - Festival: autumn days 1–6 "The harvest festival is on the square in 3 days."; day 7 before
    18:00 "Today is the harvest festival, this evening on the square."; from 18:00 "The harvest
    festival is on now on the square."
  - Places: for the fields and the garden when the villager stands on it, has a cell of it in sight,
    or works there: "The fields are sprouting; nobody has tended them for 2 days." / "The flower
    garden is blooming."
- `usual_place(name, tick)` (now takes the tick): on the festival day from 18:00 every awake
  villager's usual place is the square; callers in `turn.py` and `runner.py` pass the tick.
- **Why**: the observation is the only channel to the villagers; the agents' stored rules stay
  untouched, so no rules refresh is needed this time.

## 5. Festival memory

- **Decision**: during the festival evening each step records awake villagers on the square in
  `world["festival"] = {"day": d, "present": [...]}`; when a present villager's bedtime starts, it
  remembers (kind `festival`, importance 5) "The harvest festival on the square with Lina and
  Jonas." The square is decorated (bunting, lanterns) from the state's `calendar.festival_in == 0`.
- **Why**: bedtime is the end of that villager's evening; importance 5 keeps the memory through
  the memory limit for a long time.
- **Festival start** (added after the real-model check): at the first festival-evening step every
  awake villager gets the event "The harvest festival has begun on the square; the whole village
  is expected there." and a trigger, so it decides again with the festival in mind; the
  observation line says the same. Without it, villagers stayed in long conversations and only
  one of four reached the square (the village still never moves anyone).

## 6. Chronicle (new `village/chronicle.py`)

- **Decision**:
  - Day record: `world["day_record"] = {"day": d, "items": [{tick, text}]}`, opened when the first
    villager wakes and no record is open. `_note(text)` adds an item (texts cut to 300, at most 120
    items) from: the first meeting of a pair that day, each finished conversation once with its
    transcript, found and missed, setting off for a place, goodbye, growth changes, the festival.
  - When `_fall_asleep` leaves everyone asleep and a record is open, the record is closed
    (`day_record = None`) and a chronicle task starts with a prompt built from it: the date of the
    record's day, that day's weather, the places' states and the items. The entry therefore
    always belongs to the day the record began, even past midnight (spec US2 scenario 2).
  - "Village chronicler" block agent (model block `chronicle` + check `answer-is-json`), created
    by `ensure_agents` once, id in `world["chronicler_agent_id"]`, kept across Reset.
  - Answer `{"title": "...", "text": "..."}`; `parse_entry` checks both are non-empty strings,
    cuts the title to 60 and the text to 800 characters, redacts after decoding.
  - The run goes through `_run(agent_id, None, prompt, tick)` (no villager tag);
    `village_action` is `{"action": "chronicle", "title": …}` or `{"action": "chronicle",
    "reason": …}`.
  - `self.chronicle` holds the task; `_settle` waits for it, failures never reach `outcomes`.
  - Entries `{day, year, season, day_of_season, weather, title, text, run_id}` are kept newest
    last, at most 28 (`CHRONICLE_KEPT`), and sent newest first in the state.
- **Why**: a dedicated record survives the 8-line log and the per-villager memory limit; the
  existing reflection pattern (task map, `_settle`, `set_village_action`) is reused.
- **Alternatives**: rebuilding the day from villager memories — rejected: duplicated per villager,
  thinned by the memory limit, and moves are not memories.

## 7. "New" chronicle entries

- **Decision**: the view keeps the run id of the newest entry the owner has seen in
  `localStorage` (try/catch, per browser); `newEntries(chronicle, seen)` counts entries before
  that run id, all of them when it is missing (e.g. after Reset). Opening the chronicle stores
  the newest run id.
- **Why**: the spec asks for nothing on the server about the owner.

## 8. The look (frontend)

- **Decision** (new `components/village/seasons.tsx`, so `pixels.tsx` does not grow):
  - Season palettes for grass and trees (spring fresh green with pink blossom dots, summer deep
    green, autumn gold, orange and red chosen per tree by its position, winter bare branches),
    snow cover whitening grass, paths and roofs.
  - Weather overlay: rain (about 40 falling streaks, grey tint, puddles on a few path cells),
    storm (heavier rain and a lightning flash every few seconds), fog (three drifting bands),
    snow (about 40 drifting flakes), clouds (two cloud shadows crossing the map), sun (nothing).
    Butterflies only in spring and summer without rain; fireflies not in winter.
  - Field stages and the garden's states as tile variants, weeds over neglected fields.
  - Festival: bunting across the square and lanterns at its corners, lit when dark.
  - HUD: "Day 3 of autumn, year 1" with a small pixel weather icon next to the clock.
  - Everything `pointer-events: none`; all new keyframes stop under reduced motion (rain and
    snow stay drawn, still).
- **Why**: same approach as M9 — SVG drawn in code, CSS animation, no dependency.
