# Quickstart: M14 — Better Villagers

## Automated

```bash
make check
```

## Manual checks (real model, `make dev-llm`)

Back up `backend/data/agent_lab.db` and stop `make dev` before the world-version change.

1. **Turn checks** (SC-001, SC-006): `make eval-checks` at 20 repeats, then `compare` with the
   M13 result at 20 repeats. These must be marked better: `build-with-loads`,
   `work-at-own-place` and `meeting-call-talking`. No M13 check may be marked worse, and the new
   checks must reach at least 15/20.
2. **Scenarios** (SC-002): `make eval-scenarios`. `talk-then-go` must hold at least 3/5, and the
   other two at least 4/5.
3. **Three village days** (SC-003 to SC-005): copy the owner's database to a scratch backend, run
   three village days at Fast, then `evals health --db <copy>`. Compare per 100 decisions with
   the baseline:
   - "no work here" 6.1, "not next to you" 7.3, "say goodbye first" 6.1 (each must halve);
   - waits at most 35%;
   - model calls per day no more than at baseline.

   Count the out-of-season memories in plan and decision prompts, and the weather slips in the
   three chronicles.
4. Watch a villager's panel: its intention, its turns showing intentions begin and end, and the
   "What you can do here" section in a decision prompt.

Record the results in `tasks.md` under "Manual check results".
