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

## Results

To be filled in after implementation.
