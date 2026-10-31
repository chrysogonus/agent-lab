# Quickstart / validation: M5

Prerequisites: as M4 (`make dev-llm`, `make dev`; OpenAI optional).

## Automated

```bash
make check
```

Expected: all gates pass, with no real model called. Notable tests: each block kind at its
limits with every span on a declared node (SC-003); references and visibility; every invalid
layout in the validation list rejected at its block and field, nothing stored (SC-004); the six
template conversions reach the template's status, answer and call counts on the same script and
have its nodes and a subset of its edges (SC-002); history after edit and delete (SC-005);
golden template file unchanged (FR-014); block tree edits in vitest.

## Manual (real model)

1. New block agent: the graph shows start → answer → end. Add a tool block `calc` (calculator,
   expression `{previous}`) after it, then a model block `explain` with message
   `"Question: {input}\nResult: {calc}"`. Change `answer`'s prompt to "Reply with only the
   arithmetic expression for the question." Save and run "What is 17 times 23?": three spans on
   three nodes, answer explains 391. Time from New to running: under 3 minutes (SC-001).
2. Rename `calc` to `math`: `{calc}` in `explain` becomes `{math}`. Remove `math`: saving shows
   an error at `explain`'s message (unknown reference).
3. Add a check after `answer` (`contains` "*"), run a prompt without multiplication: the run ends
   `error` naming the check.
4. Open the Routing template as blocks, save, run its sample prompt: same route and answer as the
   template; then add a fourth route with two blocks and run a matching prompt.
5. Open Parallelization and Orchestrator-workers as blocks and run: branches and items start
   together; the merge or synthesizer runs after them.
6. Open Evaluator-optimizer as blocks, set max rounds 1, run: approved → `completed`; rejected →
   `max_iterations` with the first slogan as the answer.
7. Build a 30-block, 3-level layout (or load the test fixture): the graph redraws within 1 s of an
   edit (SC-006).
8. Edit and delete a block agent with runs: the runs still replay with their own graph (SC-005).
