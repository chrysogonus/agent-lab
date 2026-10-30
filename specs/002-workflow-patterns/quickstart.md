# Quickstart / validation: M2

Prerequisites: as M1; for the manual part a model server: `make dev-llm` (vLLM, `qwen3.5-9b`), or
Ollama with `qwen3:8b`.

## Automated

```bash
make check
```

Expected: all gates pass; workflow tests run on `FakeLLM` only.

## Manual (real model)

```bash
make dev-llm
make dev-backend
make dev-frontend
```

1. Pick each workflow in the agent picker: graph, description and sample prompt appear before
   running (FR-012, FR-013).
2. Run each sample prompt; each finishes with an answer (SC-001). Note totals in the header.
3. Routing: ask "What is 2**10?" → route span says `math`, only router→math and the calculator
   edges are marked (US2-1).
4. Parallel: three review spans overlap; header wall time < sum of the three (SC-003); three nodes
   highlighted at once while running (FR-014).
5. Orchestrator: plan span lists the subtasks; one worker span per subtask (US2-3).
6. Evaluator: rounds visible with verdicts; loop edge marked if a revision happened (US2-4).
7. Past runs: every entry shows its workflow and totals; an M1 ReAct run still replays (FR-015,
   FR-016, FR-020).
