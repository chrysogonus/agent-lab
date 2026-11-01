# Quickstart / validation: M8

Prerequisites: as M7 (`make dev-llm`, `make dev`).

## Automated

```bash
make check
```

Notable tests: memories from conversations, finds, misses and first meetings; the 60-memory
limit; recall ranking; a reflection when falling asleep after an eventful day and none after an
uneventful one; valid and invalid reflection answers; learnings and views in the next day's
observations; reflections not overlapping and not counting as failed decisions; persistence,
reset and loading an M7 world.

## Manual (real model)

1. Start the village and let it run through day 1 into day 2.
2. At bedtime, each villager who talked to someone reflects; its panel shows "Has learned" and
   its views of the others (US3-1); the reflection opens in the run view (US3-2).
3. On day 2, read the decisions' prompts and answers: at least one follows a learning or a view
   from day 1 (SC-006).
