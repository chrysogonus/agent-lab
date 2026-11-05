# Quickstart: M17 — The Evaluation Harness

## Automated

```bash
make check
```

This covers every functional requirement with the scripted fake model:
- `FakeLLM` for agents, cases, budgets, approvals and the judge;
- `httpx.MockTransport` for each provider's failures, waits and hints;
- an injected sleep, so retry tests do not wait;
- the in-process lab server and the notes server for ask-first tools.

No test reaches a real model or an outside service.

## Before the manual checks

- The model is `anthropic/claude-haiku-5-5` (spec, Assumptions). Set `ANTHROPIC_API_KEY` in `.env`,
  and pick the model when starting an evaluation.
- These checks spend money. Check 5 makes at least 10 agent runs.
- **Back up `backend/data/agent_lab.db` first**, or use a scratch database with `AGENT_LAB_DB`. M17
  adds columns and tables to the database on its first start.
- Pause the village unless a check asks for it, since it shares the provider's rate limits.
- `make dev` needs ports 8000 and 3000 free.

## Manual checks

1. **Three cases in 10 minutes** (SC-002):
   - save a new agent from the ReAct template; it starts with the examples and the default budget;
   - add a third case of your own, time it from here, and run all three once;
   - results with pass rates appear within 10 minutes, without leaving the lab's pages.
2. **Before and after** (SC-006):
   - run the agent's cases, change its system prompt so a case should fail, and run them again;
   - compare the two: the failing case shows as down, with both config versions, without opening a
     run.
3. **Budget and Stop** (SC-003):
   - set the agent's budget to 1 model call and run the sample prompt: it ends over budget, saying
     "model calls: 1 of 1";
   - raise it, ask for something long, and press **Stop**: it ends as stopped within 2 seconds, with
     its trace kept.
4. **Approvals** (SC-005):
   - give an agent `notes/write_note` and mark it ask first;
   - ask it to note a fact. The run waits, and the waiting notice shows from the Tools page too;
   - deny with "not now": the model sees the denial, the run goes on, and no note is written;
   - run it again and approve: the note is written.
5. **A real evaluation** (SC-007): run the unchanged ReAct template's example cases with 5 attempts
   each on `anthropic/claude-haiku-5-5`. No run ends in a provider error. This is the first run of the
   template on this model, so a failure here may be about the model and not the harness; open the run
   before concluding.
6. **The village warning** (FR-008): start the village on the same provider, then open the evaluation
   start page. It warns, and the evaluation can still start. Afterwards check the village is still
   running, unless repeated failures paused it.
7. **A restart** (FR-022): start a long evaluation, stop the backend, and start it again. The evaluation
   shows as interrupted with the results it had.

## Results (2026-11-05)

**Timing** (plan performance goals), measured once with a script:

| Path | Goal | Measured |
|---|---|---|
| `GET /evaluations/{id}` at its largest: 500 attempts of 10 checks each | under 1 s | median 24 ms, max 61 ms (1.7 MB) |
| Stop across three parallel branches | under 2 s | median 21 ms, max 24 ms |

**Browser check with a scripted model**, in headless Chromium, against a scratch backend and database, so
it cost nothing and touched nothing of the owner's. It passed, after two bugs were found and fixed: the
approval notice did not show on another page when that run was the one left open, and saving an edited
case was refused, since the form sent back fields only the server may set. The page's one 404 is the
browser asking for `/favicon.ico`, as it did before M17.

- Evaluate a template: examples listed, 2 of 2 passing, the default budget marked.
- Add a failing case: 67% overall, the failed check with its reason, opening an attempt's run and coming
  back, and comparing with the earlier evaluation, with the new case shown as new.
- Save a new agent from the template: it has the default budget and its own copy of the examples.
- Mark `calculator` ask first and run it: the run shows as waiting, the notice shows on the Tools page, its
  link opens the card, and denying with a reason lets the run complete. The span shows the decision.
- Edit a saved case, and see the judge's model choices.
- Stop a slow run: it ends as stopped.
- Lower the budget to 1 model call and approve a call: it ends over budget, "model calls: 1 of 1".

**Manual checks 1–7 on a real model**: not run yet. They spend the owner's money and need
`ANTHROPIC_API_KEY`, so they wait for the owner's go-ahead (T038).
