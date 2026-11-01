# Quickstart: M11 — Plans and Purpose

## Automated

```bash
make check   # ruff, pyright, pytest (FakeLLM only), eslint, tsc, vitest
```

## Manual checks

Prerequisites: `make dev-llm` (vLLM) and `make dev`. Long checks run on a scratch backend on
another port with a copy of the database, driven over the API (as in the M10 checks), so the
owner's village is untouched.

1. **Plans** (US1, SC-004): run two village days at Fast. Open each villager: "Today's plan"
   shows 2–6 entries with "now" and "next" marked; its turns list the plan runs, and a revision
   after a long conversation. For each villager and day, compare the plan's first entry with the
   villager's position within an hour of its time: at least three of four on at least one day.
2. **Facts and claims** (US2, SC-004): open a decision turn: the prompt starts with "What you
   know for sure:" and lists heard lines under "What others told you". The villager agents'
   system prompts contain "Trust what you see over what you hear". No chronicle entry of the two
   days reports weather other than the day's.
3. **Repetition** (US3, SC-006): count decision runs whose reason is "you already said that"
   (`GET /runs` filtered by village action) and read the conversations: no villager repeats one
   of its last three lines.
4. **Work and deliveries** (US4, SC-005): on a scratch world at autumn day 1 with ripe fields and
   a blooming garden, run at Fast to the festival evening. Baskets appear next to villagers who
   worked; at least two of fish, vegetables and flowers are on the stalls; the festival memories
   and the chronicle name them. Screenshot the stalls and a carried basket.
5. **Working together**: in the same run, note any time two villagers work one place: the turn
   events show baskets coming in half the time.

Record results in `tasks.md` under "Manual check results".
