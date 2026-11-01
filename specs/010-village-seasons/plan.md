# Implementation Plan: M10 — Village Seasons

**Branch**: `main` (feature directory `010-village-seasons`) | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-village-seasons/spec.md`

## Summary

Backend: a new `seasons.py` derives the calendar, the season's light and a reproducible weather
from the village day and updates the fields and the flower garden once a day from how long awake
villagers stood on them; the observation names date, season, weather, the festival countdown and
the places' states; on the festival evening the square becomes everyone's usual place and guests
remember it. A new `chronicle.py` holds the "Village chronicler" block agent: the runner keeps a
day record from the first waking until everyone sleeps, then runs the chronicler like a
reflection and keeps the last 28 entries. World version 4, upgraded from 3. Frontend: three pace
buttons in place of the seconds field, a chronicle panel with "new" marks, season palettes, weather
overlays, growth stages, festival decorations and a calendar line in the HUD, in a new
`seasons.tsx`.

## Technical Context

**Language/Version**: Python 3.12, TypeScript / Next.js 16 · **Dependencies**: unchanged (stdlib
`random` for the seeded weather) · **Storage**: the village row, world version 4 · **Testing**:
pytest with `FakeLLM`, vitest · **Constraints**: no image assets, CSS animation only, reduced
motion respected, decorations never intercept clicks, the state stays small (chronicle ≤ 28
entries) because it is published after every move

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Two small new modules (`seasons.py`, `chronicle.py`) and one new view file instead of growing `runner.py` and `pixels.tsx` |
| II. Observable by default | Pass | The chronicler is an ordinary traced run of a block agent; its outcome is the run's `village_action` |
| III. Secure local defaults | Pass | The chronicler's answer is validated, cut and redacted after decoding, never executed |
| IV. Smallest change | Pass | Calendar and weather derived, not stored; pace reuses the interval endpoint; no new endpoint or dependency |
| V. Gates + traceability | Pass | FR → test map in `tasks.md`; view logic (paces, new entries, calendar text) in `lib/village.ts` with vitest |

Post-design re-check: unchanged, all pass.

## Design

### Backend (`village/`)

- `seasons.py` (new, research §2–§3): `SEASONS`, `DAYS_PER_SEASON`, `date`, `festival_in`,
  `SUN`, `sky`, `dark`, `WEATHER`, `weather`, `snow_cover`, `WEATHER_TEXT`, `growth_text`,
  `new_growth`, `growth_for_season` (upgrade), `end_day(world, day) -> list[str]` (the notes for
  the day record).
- `chronicle.py` (new, research §6): `CHRONICLE_KEPT = 28`, `chronicle_prompt(world, record)`,
  `parse_entry(answer)`, `chronicler_agent()`.
- `world.py`: `VERSION = 4`; `new_world()` adds growth, `tended`, `day_record`, `festival`,
  `chronicle`, `chronicler_agent_id`; `upgrade()` chains 2 → 3 → 4; `usual_place(name, tick)`
  with the festival evening.
- `memory.py`: `IMPORTANCE["festival"] = 5`.
- `turn.py`: first observation line with calendar and weather, festival line, place lines;
  `usual_place` called with the tick.
- `runner.py`:
  - `_load` upgrades version 2 and 3.
  - `ensure_agents` creates the chronicler; Reset keeps its id.
  - `_advance` counts `tended` after the moves, records festival guests; the first waking of a day runs
    `end_day` for the day before and notes its changes.
  - `_note` writes the day record: opened in `_schedule` on the first waking, filled from
    `_look`, `_end_conversation`, `_set_off`, goodbye and the festival.
  - `_fall_asleep` starts the chronicle when everyone sleeps; `_chronicle` runs it;
    `_settle` waits for it.
  - Festival memory when a guest's bedtime starts.
  - `state()` adds `calendar`, `weather`, `snow_cover`, `sky`, `dark`, `growth`, `chronicle`
    (newest first) and drops the internal fields.

### Frontend

- `lib/api.ts`: the new state fields, `VillageAction` `chronicle`.
- `lib/village.ts`: `PACES`, `paceOf`, `stateText` with the pace, `calendarText` ("Day 3 of
  autumn, year 1"), `newEntries`, `turnLabel` for chronicle runs, the sky from `state.sky`.
- `components/village/seasons.tsx` (new): season palettes, `Weather`, `Puddles`, field and garden
  stage tiles, `Weeds`, `Festival`, `WeatherIcon`.
- `components/village/pixels.tsx`: `Ground` and trees take the season and snow cover; butterflies
  and fireflies by season and weather.
- `components/village/ChroniclePanel.tsx` (new): entries newest first with day, season, weather;
  marks new ones; stores the newest seen run id.
- `VillageView.tsx`: pace buttons, chronicle button with the count of new entries, calendar line
  and weather icon, lights from `state.dark`.
- `globals.css`: keyframes for rain, snow, fog, cloud shadows, lightning and lanterns; off under
  reduced motion.

## Project Structure

```text
backend/src/agent_lab/village/seasons.py (new), chronicle.py (new), world.py, memory.py,
    turn.py, runner.py
backend/tests/test_village_seasons.py (new), test_village_chronicle.py (new),
    test_village_world.py, test_village_turn.py, test_village_runner.py, test_village_api.py
frontend/src/lib/api.ts, lib/village.ts (+ test), components/village/seasons.tsx (new),
    ChroniclePanel.tsx (new), pixels.tsx, VillageView.tsx, app/globals.css
README.md, AGENTS.md
```

## Complexity Tracking

None.
