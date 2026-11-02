# Quickstart: M12 — Building Together

## Automated

```bash
make check   # ruff, pyright, pytest (FakeLLM only), eslint, tsc, vitest
```

## Manual checks

Prerequisites: `make dev-llm` (vLLM) and `make dev`. As in the M10 and M11 checks, long checks
run on a scratch backend on another port with a copy of the database. They are driven over the
API, so the owner's village is untouched.

1. **Trader** (US1, SC-001): run one village day at Fast from 08:30. Check:
   - the trader appears at the market at 09:00 with its goods and leaves at 14:00;
   - turns with `buy` show the basket paid and the load carried;
   - refused buys give a reason (after 14:00, empty hands).

   Screenshot the trader at the market.
2. **Meeting** (US2, SC-003, SC-004): start a scratch world on a meeting day at 07:00, with
   nothing built and every villager holding a basket, and run at Fast. Check:
   - Hilde's proposal run lists 2–3 projects;
   - from 17:00 to 17:30 each villager but Hilde at the town hall has one vote run (Hilde
     chairs and decides);
   - the decision names a proposal (note whether Hilde went against the vote);
   - **Village projects** shows the proposals, the votes with their reasons and the decision;
   - at least three villagers attend.
3. **Tasks** (US3): after the decision, the work-plan run gives tasks. The assigned villagers'
   next plans and decision prompts show them.
4. **Building** (US4, SC-004, SC-005): continue for up to six village days. Check:
   - loads are bought, carried and set down at the site;
   - the site shows scaffolding and loads;
   - at least two villagers trade baskets and at least two work at the site;
   - the project finishes and stays on the map the next morning;
   - the chronicle names it.

   Screenshot the site under construction and the finished result.
5. **Seasons and growth**: in the same run, note which baskets paid for the loads (early spring
   has only fish; flowers follow once the garden blooms). Count the trades refused for empty
   hands.

Record the results in `tasks.md` under "Manual check results".
