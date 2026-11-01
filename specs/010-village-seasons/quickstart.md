# Quickstart: M10 — Village Seasons

## Automated

```bash
make check   # ruff, pyright, pytest (FakeLLM only), eslint, tsc, vitest
```

## Manual checks

Prerequisites: `make dev-llm` (vLLM) and `make dev`; open `http://127.0.0.1:3000` and switch to
the Village view. For long checks use a scratch backend on another port with a copy of the
database, driven over the API (as in the M8 checks), so the owner's village is untouched.

1. **Paces** (US1): click Slow, Normal, Fast; the marked pace and the status follow, and steps come
   every 15, 5 and 2 seconds. A villager agent's model (agent builder) is unchanged.
2. **Chronicle** (US2, SC-006): run two village days at Fast. After each night the chronicle shows
   one entry with day, season and weather; each mentions something that happened that day.
   Close and reopen the chronicle: the "new" mark clears; reload after another night: one new.
3. **Seasons and weather** (US3, SC-005): on a scratch world set the day to each season and to
   days of each weather kind (the weather table in research §2 tells which); take screenshots at
   1400 × 950 by day and at night. Check reduced motion (rain and snow still).
4. **Growth** (US4, SC-005): screenshots of each field stage, the weeds, and each garden state.
5. **Festival** (US3/US5, SC-007): set a scratch world to autumn day 6 evening, run at Fast to the
   festival night; the square is decorated, at least three villagers are on it in the evening,
   and those present have a festival memory.
6. **Observation**: open a villager's turn in the run list; the prompt names date, season,
   weather, the festival countdown and the state of the fields or garden in sight.

Record results in `tasks.md` under "Manual check results".
