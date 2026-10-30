---
description: "Task list for M2 — Workflow Patterns"
---

# Tasks: M2 — Workflow Patterns

**Input**: `specs/002-workflow-patterns/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, contracts/trace-conventions.md, quickstart.md)

**Tests**: requested by the spec (FR-017, FR-018, SC-002, SC-004); every FR maps to a test or
manual check (see Traceability). Tests use `FakeLLM` only.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 / US2 / US3 from spec.md

## Conventions used by every workflow task

- Module exports `AGENT_ID`, `NAME`, `DESCRIPTION` (one line), `SAMPLE_PROMPT`, a pydantic
  `Config` (`model: str`, `reasoning: bool = False`, prompts as `str` fields, caps),
  `build_graph() -> Graph` with hand-set x/y, and a class with `async run(prompt) -> Outcome`.
- Trace conventions (contracts/trace-conventions.md): root `step "invoke_agent {AGENT_ID}"` at
  `start` (input prompt, output answer); final `step "final answer"` at `end` with
  `lab.came_from` = last node(s) and `error` set for any non-`completed` end; every node visit's
  first span carries `lab.came_from`; nested spans at the same node omit it; model calls only via
  `steps.chat`, tools only via `steps.call_tool`, decisions only via `steps.decide`.
- Every `(came_from, node_id)` pair must be a declared graph edge, including error exits.

---

## Phase 1: Setup

No new project setup or dependencies (plan: "No new dependencies").

- [ ] T001 Create the empty package backend/src/agent_lab/workflows/__init__.py (module docstring only)

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: model-client options, test fakes, shared traced helpers, ReAct on the helpers.

- [ ] T002 [P] Add node kind `code` to `Node.kind` (`start | llm | tool | code | end`) in backend/src/agent_lab/graph.py
- [ ] T003 [P] Extend `LLMClient.chat(messages, tools, *, response_format: dict[str, Any] | None = None, reasoning: bool | None = None)` in backend/src/agent_lab/llm/base.py; in backend/src/agent_lab/llm/openai_compat.py send `response_format` unchanged when given and `reasoning_effort: "none"` when `reasoning is False` (omit both for `None`; `True` → provider default)
- [ ] T004 [P] Extend `FakeLLM` in backend/src/agent_lab/llm/fake.py: script items may be `ChatResponse | Exception | Callable[[list[Message]], ChatResponse | Exception]` (callables answer from the messages, for concurrent branches); optional `delay: float = 0` seconds awaited per call; `requests: list[dict[str, Any]]` records `{"response_format", "reasoning", "tools"}` per call beside `calls`
- [ ] T005 [P] Tests: `response_format` passed through, `reasoning=False` → `reasoning_effort: "none"`, `None` sends neither, in backend/tests/test_llm_client.py (httpx.MockTransport)
- [ ] T006 Shared helpers in new backend/src/agent_lab/agents/steps.py (extracted from `ReActAgent._chat`, `_call_tool`, `_parse_arguments`; behavior unchanged): `StepContext` dataclass `(llm, tracer, reasoning: bool)`; `Outcome(status: RunStatus, answer: str | None)`; `config_version(config: BaseModel) -> str` (moved from react.py, same hash); `chat(ctx, node_id, messages, *, tools=(), response_format=None, came_from=None, attributes=None)` → `llm "chat {model}"` span recording `lab.reasoning` and, when given, `gen_ai.request.response_format`; `call_tool(ctx, tools: dict[str, Tool], call, *, caller: str, came_from=None)` (unknown tool → span on `caller`'s node, no `lab.came_from`); `came_from` stored as `attributes["lab.came_from"]`
- [ ] T007 `decide(ctx, node_id, name, messages, model_cls, *, kind=SpanKind.STEP, came_from=None, attributes=None) -> T` and `DecisionError` in backend/src/agent_lab/agents/steps.py: opens decision span `name` (input = messages + schema), sends `response_format={"type": "json_schema", "json_schema": {"name": name, "schema": model_cls.model_json_schema(), "strict": True}}` through `chat` (child llm span, no `lab.came_from`), validates content with `model_cls`; on failure extracts exactly one JSON object from prose or a code fence and validates that; otherwise records the error on the decision span and raises `DecisionError`; output = validated decision `model_dump()`
- [ ] T008 Switch `ReActAgent` to `steps.chat`/`steps.call_tool` in backend/src/agent_lab/agents/react.py: `ReActConfig.reasoning: bool = True` passed via `StepContext`; iteration span `lab.came_from` = `["start"]` on turn 1, else the tool nodes called in the previous turn; tool spans `["llm"]`; final span ← last visited node(s); import `config_version` from steps (update backend/src/agent_lab/runs.py and backend/tests/helpers.py imports)
- [ ] T009 Test helpers in backend/tests/helpers.py: `json_answer(obj) -> ChatResponse` (JSON content), `make_ctx(llm, reasoning=False) -> tuple[StepContext, list[tuple[str, Span]]]`, `assert_trace_valid(graph, spans)` (every `node_id` ∈ graph; every `(came_from, node_id)` pair is a graph edge), `taken_edges(spans) -> set[tuple[str, str]]`
- [ ] T010 Tests in new backend/tests/test_steps.py: `chat` records `lab.reasoning` and passes `reasoning` to the client; `decide` sends the schema (visible in decision span input and in `FakeLLM.requests`), returns the validated model, parses JSON in prose and in a ```json fence, raises `DecisionError` with span error on invalid JSON / two JSON objects / schema violation; `decide(kind=SpanKind.ROUTE)` sets span kind `route`
- [ ] T011 Extend backend/tests/test_react.py: existing tests still pass; new `test_reasoning_on_by_default` (ReAct sends `reasoning=True`, config contains it) and `test_react_came_from_edges` (`assert_trace_valid` on the multi-step run)

**Checkpoint**: `make check` passes; ReAct behaves as in M1 apart from the new attributes.

---

## Phase 3: User Story 1 — Run any workflow and watch it live (P1) 🎯 MVP

**Goal**: the five workflows run end to end, are listed by the API, and can be picked, previewed
and watched live in the UI with multi-node highlighting.

**Independent test**: for each workflow, a scripted FakeLLM run ends `completed` with an answer and
`assert_trace_valid` holds (SC-002); `GET /agents` lists all six; `POST /runs {agent_id}` streams
spans over the WebSocket.

### Workflows (each module also implements the failure handling tested in US3)

- [ ] T012 [P] [US1] Prompt chaining in backend/src/agent_lab/workflows/chain.py (`AGENT_ID="chain"`): nodes start, outline (llm), gate (code), draft (llm), polish (llm), end; edges start→outline→gate→draft→polish→end plus gate→end; gate = `step "gate"` span with output `GateResult{passed: bool, reason: str}`, passed iff the outline has ≥ 3 non-empty bullet lines (`-`, `*` or `1.` prefixes); failed gate sets span error, skips draft/polish, run `error` with the reason as final error; sample prompt e.g. "A reusable water bottle that tracks how much you drink"
- [ ] T013 [P] [US1] Routing in backend/src/agent_lab/workflows/routing.py (`AGENT_ID="routing"`): nodes start, router (llm), math, weather, general (llm), tool:calculator, tool:get_weather, end; `Route{label: Literal["math", "weather", "general"]}` via `decide(..., name="route", kind=SpanKind.ROUTE)` at router; invalid (`DecisionError`) → `general`, span error kept; math/weather: chat with only its one M1 tool → `call_tool` for each call (came_from handler node) → chat without tools (came_from the tool node); general: one chat; edges router→each handler, handler↔its tool, each handler→end
- [ ] T014 [P] [US1] Parallelization in backend/src/agent_lab/workflows/parallel.py (`AGENT_ID="parallel"`): nodes start, clarity, tone, claims (llm), merge (llm), end; inside a `step "sections"` span at node start (no `lab.came_from`), `asyncio.gather(..., return_exceptions=True)` over three `chat` calls with `came_from=["start"]`; merge (`came_from` = the aspects that succeeded) gets only successful reviews; all three failed → skip merge, run `error`, final span ← the three aspects; edges start→each aspect, each aspect→merge, merge→end, each aspect→end (all-failed exit)
- [ ] T015 [P] [US1] Orchestrator-workers in backend/src/agent_lab/workflows/orchestrator.py (`AGENT_ID="orchestrator"`, `max_subtasks = 4`): nodes start, orchestrator (llm), worker (llm), synthesizer (llm), end; `Plan{subtasks: list[str]}` with validation "1..4 items, each non-empty, ≤ 200 chars" via `decide(..., name="plan")`; invalid → run `error`, final span ← orchestrator; workers gathered concurrently under the root span, each a `step "worker {i}"` at node worker with `lab.worker.index` = i (0..3), `came_from=["orchestrator"]`, wrapping one tool-less `chat`; synthesizer ← `["worker"]`; edges start→orchestrator→worker→synthesizer→end plus orchestrator→end
- [ ] T016 [P] [US1] Evaluator-optimizer in backend/src/agent_lab/workflows/evaluator.py (`AGENT_ID="evaluator"`, `max_rounds = 3`): nodes start, generator (llm), evaluator (llm), end; per round 1..3: generator `chat` (round 1 ← start, later ← evaluator, previous feedback in the messages) then `decide(Verdict{approved: bool, feedback: str}, name="verdict")` ← generator, with validation "feedback non-empty when not approved"; both spans carry `lab.round`; invalid verdict → not approved, feedback = the error text; approved → `completed`; cap → `max_iterations`, answer = last draft; edges start→generator→evaluator→end plus evaluator→generator (loop)
- [ ] T017 [P] [US1] Happy-path tests named `test_happy_path`, one file per workflow, each asserting `completed`, an answer, `assert_trace_valid`, `agent_id`, and that every llm request sent `reasoning=False`: backend/tests/test_workflow_chain.py, test_workflow_routing.py (general route), test_workflow_parallel.py, test_workflow_orchestrator.py (2 subtasks), test_workflow_evaluator.py (approved round 1)

### Registry, runs, API

- [ ] T018 [US1] Registry in new backend/src/agent_lab/agents/registry.py: `AgentSpec(id, name, description, sample_prompt, make_config: Callable[[LLMClient], BaseModel], graph: Callable[[BaseModel], Graph], create: Callable[[LLMClient, BaseModel, Tracer], Runnable])` where `Runnable.run(prompt)` returns something with `status`/`answer`; `AGENTS: dict[str, AgentSpec]` ordered react, chain, routing, parallel, orchestrator, evaluator (ReAct gets name/description/sample prompt here)
- [ ] T019 [US1] Dispatch through the registry in backend/src/agent_lab/runs.py: `new_run(prompt, agent_id, llm, secrets)` builds config/graph/`config_version` from `AGENTS[agent_id]`; `execute_run` creates the runnable via `spec.create`; tracer, store, bus and `run_ended` unchanged
- [ ] T020 [US1] API in backend/src/agent_lab/api.py: `GET /agents` → `[AgentInfo{id, name, description, sample_prompt, graph}]` in registry order; `POST /runs {"prompt": str (1..4000), "agent_id": str = "react"}`, unknown `agent_id` → 422
- [ ] T021 [US1] API tests in backend/tests/test_api.py: `test_list_agents` (six entries, ReAct first, every graph has start/end); `test_post_run_defaults_to_react`; `test_unknown_agent_id_422`; `test_workflow_run_streams` (routing run over WS, all span node ids in the stored graph, run `agent_id`/`config_version` set, stored config contains `reasoning: false`)

### Frontend

- [ ] T022 [P] [US1] Types and calls in frontend/src/lib/api.ts: `GraphNode.kind` adds `"code"`; `AgentInfo`; `listAgents()`; `startRun(prompt, agentId)` sends `agent_id`
- [ ] T023 [P] [US1] `activeNodes(spans): Set<string>` (node ids of running spans with no running child) replacing `activeNode` in frontend/src/lib/run-state.ts; tests in frontend/src/lib/run-state.test.ts: three concurrent running branches → three nodes; parent with running child → only the child's node; finished run → empty
- [ ] T024 [US1] GraphView in frontend/src/components/GraphView.tsx: take a set of active nodes and highlight every one (switch the caller frontend/src/components/RunViewer.tsx from `activeNode` to `activeNodes`); draw `code` nodes distinctly from `llm` (e.g. dashed border); accept a graph without a run (preview)
- [ ] T025 [US1] New frontend/src/components/AgentPicker.tsx (radio group from `listAgents()`); wire in frontend/src/app/page.tsx: selecting an agent shows its description, previews its graph before any run, and passes `agentId` and the sample prompt to frontend/src/components/PromptForm.tsx (new props; it replaces its hard-coded default prompt and calls `startRun(prompt, agentId)`)
- [ ] T026 [US1] Show each run's agent name (from `agent_id` via the agents list, fallback to the id) in frontend/src/components/RunList.tsx

**Checkpoint**: every workflow runs from the UI with FakeLLM tests green; MVP usable.

---

## Phase 4: User Story 2 — See each pattern's control flow (P2)

**Goal**: each pattern's defining decision is a span, only taken edges are marked (from
`lab.came_from`), and runs show totals for comparison.

**Independent test**: scripted runs forcing each decision record it on a span and produce exactly
the expected taken edges; totals match the spans.

- [ ] T027 [P] [US2] Chain test `test_gate_fails_stops_chain` in backend/tests/test_workflow_chain.py: 2-bullet outline → gate span error with reason, no draft/polish spans, run `error`, taken edges = {start→outline, outline→gate, gate→end} (US2-5)
- [ ] T028 [P] [US2] Routing tests in backend/tests/test_workflow_routing.py: `test_route_math` (calculator called, route span kind `route` output label `math`), `test_route_weather` (only router→weather and weather↔tool:get_weather edges taken, no math/general spans), decision span input contains the schema (US2-1)
- [ ] T029 [P] [US2] Parallel test `test_branches_overlap_and_join` in backend/tests/test_workflow_parallel.py: FakeLLM callables answering by aspect with `delay=0.05`; the three aspect spans overlap in time, root duration < sum of branch durations (SC-003), merge `lab.came_from` = all three, all fan-out and fan-in edges taken (US2-2)
- [ ] T030 [P] [US2] Orchestrator test `test_three_subtasks` in backend/tests/test_workflow_orchestrator.py: plan span output has 3 subtasks, exactly 3 `worker {i}` spans at node worker with `lab.worker.index` 0..2 overlapping in time, synthesizer ← worker (US2-3)
- [ ] T031 [P] [US2] Evaluator test `test_approved_round_two` in backend/tests/test_workflow_evaluator.py: round 1 verdict rejects with feedback, round-2 generator messages contain that feedback, spans carry `lab.round` 1/2, loop edge evaluator→generator taken, run `completed` (US2-4)
- [ ] T032 [US2] `takenEdges` in frontend/src/lib/run-state.ts: when any span has `attributes["lab.came_from"]`, edges = every `(came_from, node_id)` pair; otherwise the M1 inference unchanged (FR-016); tests in frontend/src/lib/run-state.test.ts: fan-out + fan-in, loop edge, M1 spans without the attribute give the M1 result
- [ ] T033 [US2] Loop edges in frontend/src/components/GraphView.tsx: an edge whose source lies right of its target (e.g. evaluator→generator) uses bottom source/target handles so it does not overlap the forward edge
- [ ] T034 [US2] Totals in backend/src/agent_lab/store.py: `RunTotals{llm_calls, tool_calls, tokens_in, tokens_out, wall_ms}` on `Run.totals`, filled by `list_runs`/`get_run` via one aggregate query over `spans` (counts of kind `llm`/`tool`; token sums with null treated as 0; `wall_ms` = (ended_at − started_at) × 1000, null while running); no schema change
- [ ] T035 [US2] Totals tests in backend/tests/test_store.py: `test_totals` (values for a scripted run), `test_totals_running_wall_null`, `test_m1_run_still_lists` (run + spans written in M1 shape, no `lab.came_from`/`reasoning` → listed and fetched with totals) (FR-016, FR-020)
- [ ] T036 [US2] Frontend totals: `RunTotals` on `Run` in frontend/src/lib/api.ts; `runTotals(spans, run)` in frontend/src/lib/run-state.ts (same definition, live wall time from `now` while running) with tests in frontend/src/lib/run-state.test.ts; show totals in the run header in frontend/src/components/RunViewer.tsx and per entry (stored totals) in frontend/src/components/RunList.tsx

**Checkpoint**: each pattern's decision is visible in replay; past runs comparable without opening.

---

## Phase 5: User Story 3 — Trust the failure paths (P3)

**Goal**: unusable decisions, branch failures and the round cap end in a well-defined state.

**Independent test**: scripted failure runs record the error on the relevant span and end in the
documented status; no run hangs.

- [ ] T037 [P] [US3] Routing test `test_invalid_label_falls_back_to_general` in backend/tests/test_workflow_routing.py: `{"label": "sports"}` → route span error records the invalid output, general handler runs, run `completed`, edge router→general taken (US3-1)
- [ ] T038 [P] [US3] Orchestrator tests in backend/tests/test_workflow_orchestrator.py: unreadable plan, 5 subtasks, 0 subtasks, a subtask over 200 chars → plan span error, no worker spans, run `error`, final span ← orchestrator (US3-2)
- [ ] T039 [P] [US3] Evaluator tests in backend/tests/test_workflow_evaluator.py: `test_never_approves` → 3 rounds, run `max_iterations`, answer = third draft (US3-3); `test_invalid_verdict_counts_as_rejection` → verdict span error, next generator gets the error text as feedback
- [ ] T040 [P] [US3] Parallel tests in backend/tests/test_workflow_parallel.py: `test_one_branch_fails` → failed aspect span has the error, merge gets two reviews and ← the two survivors, run `completed` (US3-4); `test_all_branches_fail` → no merge span, run `error`, final span ← the three aspects
- [ ] T041 [P] [US3] Model transport error mid-workflow (`LLMError` in the script) → span error, run status `error`, `run_ended` published, in backend/tests/test_api.py `test_workflow_llm_error_ends_run`; plus `test_two_workflow_runs_stream_independently` (routing and parallel runs started together, each WS receives only its own spans)
- [ ] T042 [US3] Fix any defects exposed by T037–T041 in the workflow modules under backend/src/agent_lab/workflows/

**Checkpoint**: every US2 decision and US3 failure has a passing test (SC-004).

---

## Phase 6: Polish

- [ ] T043 [P] Update AGENTS.md: current feature `specs/002-workflow-patterns/`; layout adds `agents/steps.py`, `agents/registry.py`, `workflows/`; contract 2 notes `lab.came_from` and the steps helpers as the only path to model/tools; mention README.md run instructions for picking a workflow
- [ ] T044 Run quickstart.md manual checks with `qwen3:8b` (FakeLLM smoke if no model is pulled) and record results under "Manual check results" in this file
- [ ] T045 Final `make check`; fill in any missing rows of the Traceability table below

---

## Dependencies

- Setup → Foundational → US1 → US2 → US3 → Polish.
- T006 → T007 → T008; T009 needs T006; T010 needs T007 + T009; T011 needs T008 + T009.
- US1: T012–T016 need Phase 2 and are independent of each other; T017 per workflow after its module; T018 needs T012–T016; T019 → T020 → T021; T024–T026 need T022 (and T023 for T024).
- US2 backend tests (T027–T031) only need their US1 module; T032–T033 need T024; T034 → T035 → T036.
- US3 adds tests on US1 code; T042 follows them.

## Parallel opportunities

- Phase 2: T002, T003, T004, T005 together; then T006 → T007.
- US1: the five workflow modules T012–T016 in parallel, each followed by its part of T017; T022 ∥ T023 alongside the backend work.
- US2: T027–T031 in parallel (one test file each); T032 ∥ T034.
- US3: T037–T041 in parallel.

```bash
# US1 example
Task: "Prompt chaining in backend/src/agent_lab/workflows/chain.py"
Task: "Routing in backend/src/agent_lab/workflows/routing.py"
Task: "Parallelization in backend/src/agent_lab/workflows/parallel.py"
Task: "Orchestrator-workers in backend/src/agent_lab/workflows/orchestrator.py"
Task: "Evaluator-optimizer in backend/src/agent_lab/workflows/evaluator.py"
```

## Implementation strategy

1. Phase 2 first: ReAct must stay green while it moves onto `steps.py`.
2. MVP = US1: the five workflows runnable and watchable; stop and run quickstart steps 1–2.
3. US2 makes the patterns distinguishable (decision tests, recorded edges, totals).
4. US3 hardens the failure paths; mostly tests over US1 code.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_workflow_chain.py::test_happy_path, test_gate_fails_stops_chain |
| FR-002 | test_workflow_routing.py::test_route_math, test_route_weather, test_happy_path |
| FR-003 | test_workflow_parallel.py::test_branches_overlap_and_join |
| FR-004 | test_workflow_orchestrator.py::test_three_subtasks, test_happy_path |
| FR-005 | test_workflow_evaluator.py::test_approved_round_two, test_never_approves |
| FR-006 | test_steps.py (schema sent, validation, prose/fence extraction, DecisionError); US3 tests T037–T039 |
| FR-007 | module layout (review); pyright gate; workflows import only steps, tools, tracer, llm |
| FR-008 | `assert_trace_valid` in every workflow test; test_three_subtasks, test_approved_round_two (one node, distinguished by name/attributes) |
| FR-009 | test_route_*, test_gate_fails_stops_chain, test_three_subtasks, test_approved_round_two |
| FR-010 | test_branches_overlap_and_join, test_three_subtasks (parents, overlap) |
| FR-011 | test_api.py::test_workflow_run_streams; test_react.py::test_config_version_stable |
| FR-012 | test_api.py::test_list_agents, test_post_run_defaults_to_react, test_unknown_agent_id_422 |
| FR-013 | quickstart step 1 |
| FR-014 | run-state.test.ts (activeNodes, takenEdges from came_from); quickstart steps 3–4, 6 |
| FR-015 | quickstart step 7 (RunList agent name) |
| FR-016 | test_store.py::test_m1_run_still_lists; run-state.test.ts M1 takenEdges fallback; quickstart step 7 |
| FR-017 | test_workflow_*.py (happy path, US2 decisions, US3 failures) |
| FR-018 | `make check` (T045) |
| FR-019 | test_steps.py (lab.reasoning); workflow happy paths (reasoning=False sent); test_react.py::test_reasoning_on_by_default; test_api.py::test_workflow_run_streams (stored config) |
| FR-020 | test_store.py::test_totals, test_totals_running_wall_null; run-state.test.ts (runTotals); quickstart step 7 |

| SC | Test / check |
|---|---|
| SC-001 | quickstart step 2 (real model) |
| SC-002 | `assert_trace_valid` in every workflow test |
| SC-003 | test_branches_overlap_and_join; quickstart step 4 |
| SC-004 | T027–T031, T037–T041 |
| SC-005 | quickstart steps 3–6 (distinct graphs per pattern) |
| SC-006 | quickstart step 7 (totals in past-runs list) |

## Manual check results (T044)

_Pending._
