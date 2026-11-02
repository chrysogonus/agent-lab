# Quickstart: M13 — Measuring the Village

## Automated

```bash
make check   # ruff, pyright, pytest (FakeLLM only), eslint, tsc, vitest
```

The evals are not part of `make check`.

## Manual checks

Prerequisites: `make dev-llm` (vLLM). Back up `backend/data/agent_lab.db` first, as always
before a milestone touches the store.

1. **Village health** (US1, SC-002): with `make dev`, open **Village health**. Check that:
   - the owner's recent days appear in under 2 seconds;
   - days before M13 show "–" for plan kept, stuck hours and loads worked in;
   - a refusal reason opens its turns.

   Run the village for a day at Fast. The new day shows every number, and it is marked "so far"
   until the chronicle is written. Compare `evals health` on the command line with the panel.
2. **Turn checks** (US2, SC-003, SC-005): run `make eval-checks` (10 repeats). Note the time
   (under 15 minutes) and the pass rates with their ranges. Run the checks twice more at 20
   repeats, without changes, and `compare` them: at most 2 checks may be marked changed. Then
   `add-check` from a recorded run, and run it alone with `--only`.
3. **Scenarios** (US3, SC-004): checksum the owner's village row, run `make eval-scenarios`
   (5 repeats), and check that the row is unchanged. Each scenario reports held/finished counts,
   the reason per run and the health of its days. Open one copy with `make dev`
   (`AGENT_LAB_DB=…`) to see the run in the UI.
4. **Baseline** (SC-006): from the owner's last days of health, the check results and the
   scenario results, write down the three weakest behaviours with their numbers.

Record the results in `tasks.md` under "Manual check results".
