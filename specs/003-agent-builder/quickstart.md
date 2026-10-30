# Quickstart / validation: M3

Prerequisites: as M2; for the manual part `make dev-llm` (vLLM, `qwen3.5-9b`) and `make dev`.

## Automated

```bash
make check
```

Expected: all gates pass. Notable tests: golden template graphs equal M2 (SC-006); per template
a custom agent at minimum and maximum limits runs on `FakeLLM` with every span on a graph node
(SC-002); agent API validation, name uniqueness, edit/duplicate/delete history (SC-004, SC-005);
builder state and error mapping in vitest.

## Manual (real model)

1. Pick the Routing template: its nodes open read-only settings; press Customize. The builder
   shows "Routing (copy)" with the template's graph (US1-1, US1-4).
2. Click the router node, change its prompt, add a route `poem` (description "requests for a
   poem", no tool); the graph shows a fourth branch before saving (US2-2, FR-014).
3. Enter "Write a short poem about autumn" and press Run without saving: the agent is saved,
   the run starts, the route span says `poem`, only that branch is marked (FR-015, US2-2).
   Time from step 1: under a minute (SC-001).
4. Back to editing; make the `general` route's name empty and save: the error appears at that
   field and nothing is stored (US3-4).
5. Chaining template → Customize → add a step `german` ("Translate the text into German"),
   turn the gate off, run the sample prompt: no gate node, four model calls, German answer
   (US2-1, US2-5).
6. Parallelization template → Customize → set 6 aspects and run: six review spans start
   together; the two beyond the server's 4 slots take longer (edge case, FR-010).
7. Duplicate the routing agent, edit the copy, delete the original: both agents' runs still
   replay with their own graphs, the deleted one listed under its old name (US3-1–3).
8. Run each of the six templates once: same graphs and behavior as in M2 (SC-006).
