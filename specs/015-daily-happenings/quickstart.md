# Quickstart: M15 — Daily Happenings and Boat Trips

## Automated

```bash
make check
```

## Manual checks (real model, `make dev-llm`)

Back up `backend/data/agent_lab.db` and stop `make dev` before the world-version change (8).

1. **Turn checks** (SC-002, SC-005):
   - `make eval-checks` at 20 repeats;
   - the six new checks must each reach 14/20;
   - `compare` with the M14 result of record `58ee35f159d7`: no M14 check may be marked worse.
2. **Scenarios** (SC-003): `make eval-scenarios`. `boat-trip` must hold in at least 4 of 5 runs,
   with a trip together in at least 2.
3. **Seven village days** (SC-001, SC-005, SC-006):
   - run them on a copy of the owner's database, as in M14;
   - read `evals health --db <copy> --days 8` for happenings, the share dealt with, waits and
     calls per day;
   - read the seven chronicle entries: do they name the day's happening, and are the titles all
     different?
4. **Whispers** (SC-004): in the running village, whisper to a villager from its panel. Its next
   turn shows "after a whisper" and the prompt lists the voice's line as a claim. Whisper to a
   sleeping villager and see it heard on waking.
5. **The map**: watch the postman, a visitor following the host, an animal being led, the
   repair mark, the peddler, and (on a copy with the boat built) the boat moving on the lake.

Record the results in `tasks.md` under "Manual check results".
