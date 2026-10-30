# Feature Specification: M2 — Workflow Patterns

**Feature Branch**: `main` (feature directory `002-workflow-patterns`)

**Created**: 2026-10-30

**Status**: Draft

**Input**: Agent Lab Phase 1, milestone M2: the five workflow patterns (prompt chaining, routing,
parallelization, orchestrator-workers, evaluator-optimizer), each a small hand-built module with a
very simple use case, traced and visualized like the M1 ReAct agent.

## Context

M1 delivered one agent (ReAct) with tracing, storage, live streaming and a one-page UI. M2 adds
the five canonical workflow patterns as separate, readable modules on the same runtime, so the
owner can run each one, watch its graph and spans, and compare how the patterns differ in
control flow, number of model calls, latency and tokens.

All M1 core contracts apply unchanged: every model call and tool call emits a span; each workflow
declares its static graph as data and every span references a node of it; spans are persisted
and streamed; secrets are redacted; servers stay on 127.0.0.1. Models are reached only through
the M1 model client; tests use the scripted fake model.

### The five workflows and their use cases

| Workflow | Use case (deliberately tiny) | Control flow to make visible |
|---|---|---|
| **Prompt chaining** | Turn a topic into a short product blurb: outline → check → draft → polish | Fixed sequence of model calls with a programmatic gate that can stop the chain |
| **Routing** | Answer a question by first classifying it as `math`, `weather` or `general`, then handing it to a specialised handler (math and weather handlers use the M1 tools) | One model decision selects exactly one branch |
| **Parallelization** | Review a short text on three fixed aspects (clarity, tone, claims) at the same time, then merge the three reviews | Independent branches run concurrently, then join |
| **Orchestrator-workers** | Write a short trip note: an orchestrator splits the request into 2–4 subtasks at run time, workers handle them, a synthesizer combines the results | Number of worker calls is decided by the model, not by the graph |
| **Evaluator-optimizer** | Write a slogan under 12 words that mentions a given product; an evaluator approves or returns feedback, and the generator revises | Feedback loop bounded by a round cap |

## Clarifications

### Session 2026-10-30

- Q: How should the workflows get the route label, the orchestrator's plan and the evaluator's
  verdict from the model? → A: JSON-schema structured output (`response_format` with a schema
  per decision); code still validates the result.
- Q: Should qwen3's thinking be on or off in the workflows? → A: A reasoning setting in each
  workflow's configuration, default off; the ReAct agent keeps thinking on as in M1.
- Q: Should each run show totals (model calls, tool calls, tokens in/out, wall time)? → A: Yes,
  in the run header and in the past-runs list.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Run any workflow and watch it live (Priority: P1)

The owner picks a workflow (or the M1 ReAct agent) from a list, sees its graph and a sample
prompt before running anything, starts a run, and watches the graph and waterfall update live,
exactly as for ReAct.

**Why this priority**: the five patterns are the content of M2; without running and seeing them
there is nothing to learn from.

**Independent Test**: for each workflow, a scripted fake-model run streams spans whose node ids
all belong to that workflow's declared graph, and the run ends `completed` with an answer.

**Acceptance Scenarios**:

1. **Given** the app is open, **When** the owner selects a workflow, **Then** its graph,
   a one-line description and a sample prompt are shown before any run.
2. **Given** a selected workflow, **When** the owner starts a run, **Then** spans stream live,
   the graph highlights every node that is currently running, and the run ends with an answer.
3. **Given** a finished run of any workflow, **When** the owner opens it from past runs,
   **Then** it replays with the same graph and spans, and the list shows which workflow it was.

---

### User Story 2 - See each pattern's control flow (Priority: P2)

For each pattern, the visualization makes the pattern's defining control-flow decision visible:
the chain's gate result, the route chosen, branches overlapping in time, the number of workers the
orchestrator created, and each evaluator verdict and revision round.

**Why this priority**: telling the patterns apart is the learning goal; a generic waterfall alone
does not show why a branch or loop was taken.

**Independent Test**: scripted runs that force each decision (gate fails, each route, a 3-subtask
plan, approval on round 2) produce spans recording that decision, and only the taken edges are
marked.

**Acceptance Scenarios**:

1. **Given** a routing run classified as `weather`, **When** the owner views it, **Then** the
   route decision is a span showing the label, and only the edge to the weather handler is
   marked taken.
2. **Given** a parallel run, **When** the owner views the waterfall, **Then** the three aspect
   spans overlap in time and all three branch edges and their joins are marked.
3. **Given** an orchestrator run that planned 3 subtasks, **When** the owner views it, **Then**
   the plan span shows the 3 subtasks and there are 3 worker spans under one worker node.
4. **Given** an evaluator run approved on the second round, **When** the owner views it,
   **Then** each round shows the draft, the verdict and the feedback, and the loop edge is marked.
5. **Given** a chaining run whose outline fails the gate, **When** the owner views it, **Then**
   the gate span records the failure and the chain stops without the later steps.

---

### User Story 3 - Trust the failure paths (Priority: P3)

The owner sees what happens when the model returns an unusable decision (unknown route, a plan
that is not valid, an evaluator reply that cannot be read), when one parallel branch fails, or
when the evaluator never approves.

**Why this priority**: model output that drives control flow is the main new failure surface in
M2.

**Independent Test**: scripted runs for each failure produce an error on the relevant span and a
well-defined end state, never a hung or crashed run.

**Acceptance Scenarios**:

1. **Given** the router returns a label outside the allowed set, **When** the run continues,
   **Then** the route span records the invalid label and the `general` handler is used.
2. **Given** the orchestrator returns an unreadable plan or more than 4 subtasks, **When** the
   run continues, **Then** the plan span records the error and the run ends `error`.
3. **Given** the evaluator never approves, **When** the round cap (3) is reached, **Then** the
   run ends `max_iterations` and the last draft is the answer.
4. **Given** one of three parallel branches fails, **When** the others finish, **Then** the
   failed branch span shows the error and the merge step works with the remaining reviews.

### Edge Cases

- Decision outputs (route label, plan, verdict) wrapped in extra prose or code fences → parsed
  if a valid decision can be extracted unambiguously; otherwise treated as invalid.
- The orchestrator plans zero subtasks → treated as an invalid plan.
- A branch or worker call is slow → no per-call time limit in M2 (budgets and timeouts arrive
  with M4); runs are bounded only by the round and subtask caps.
- Two runs of different workflows at the same time → both stream independently.
- An existing M1 database → M1 runs still list and replay after the upgrade.

## Requirements *(mandatory)*

### Functional Requirements

**Workflows**

- **FR-001**: The system MUST provide a prompt-chaining workflow (outline → gate → draft →
  polish) whose gate is a code check, not a model call; a failed gate MUST stop the chain and
  end the run `error` with the gate's reason.
- **FR-002**: The system MUST provide a routing workflow that classifies the input into exactly
  one of `math`, `weather`, `general` with one model call and runs only the matching handler;
  the math and weather handlers MUST use the M1 `calculator` and `get_weather` tools.
- **FR-003**: The system MUST provide a parallelization workflow that runs the three aspect
  reviews concurrently and merges their results with one model call.
- **FR-004**: The system MUST provide an orchestrator-workers workflow whose orchestrator
  produces a plan of 1–4 subtasks at run time, runs one worker per subtask concurrently, and
  combines the worker results with a synthesizer call.
- **FR-005**: The system MUST provide an evaluator-optimizer workflow that alternates generator
  and evaluator calls until the evaluator approves or 3 rounds have run; each round after the
  first MUST pass the previous feedback to the generator.
- **FR-006**: Model outputs that drive control flow (route label, plan, verdict) MUST be
  requested as JSON-schema structured output, one schema per decision, and MUST still be
  validated by code; invalid output MUST be recorded as a span error and handled as stated in
  User Story 3. The schema sent MUST be visible in the decision span's input.
- **FR-007**: Each workflow MUST be its own module, readable in one sitting, built only on the
  M1 model client, tools and tracer.

**Tracing and graph**

- **FR-008**: Every workflow MUST declare its static graph as data; every span MUST reference a
  node of the workflow's graph; dynamic repetition (workers, rounds) MUST reuse one node and be
  distinguishable by span name and attributes.
- **FR-009**: Each control-flow decision MUST be its own span recording the decision as output:
  route label (kind `route`), gate result, plan, and evaluator verdict.
- **FR-010**: Concurrent branches and workers MUST each have their own span, parented correctly
  under the step that launched them, with overlapping start/end times.
- **FR-011**: Every run MUST record the workflow's `agent_id` and a `config_version` derived from
  the workflow's configuration.
- **FR-019**: Each workflow's configuration MUST include a reasoning setting (model thinking on or
  off), default off for the five workflows and on for the M1 ReAct agent; the setting MUST be
  part of `config_version` and visible in the run's stored configuration.

**API and UI**

- **FR-012**: The API MUST list the available agents and workflows (id, name, description,
  sample prompt, graph) and MUST let a run be started for a chosen one; starting without a choice
  MUST keep running the M1 ReAct agent.
- **FR-013**: The UI MUST let the owner choose an agent or workflow, show its graph, description
  and sample prompt before running, and start a run for it.
- **FR-014**: The graph MUST highlight all currently running nodes (more than one during
  parallel work) and mark every edge taken, including fan-out, fan-in and loop edges.
- **FR-015**: The past-runs list MUST show which agent or workflow each run used.
- **FR-016**: Runs stored by M1 MUST still list and replay.
- **FR-020**: The run header and the past-runs list MUST show per-run totals: model calls, tool
  calls, tokens in, tokens out and wall time, computed from the run's spans.

**Quality**

- **FR-017**: For each workflow, tests with the scripted fake model MUST cover the happy path,
  each decision branch named in User Story 2 and each failure in User Story 3.
- **FR-018**: All quality gates (`make check`) MUST pass; every requirement maps to a test or an
  explicit manual check in `tasks.md`.

### Key Entities

- **Workflow**: a runnable unit with id (`agent_id`), name, one-line description, sample prompt,
  configuration (prompts, model, caps, reasoning on/off) and static graph. The M1 ReAct agent is listed alongside
  the five workflows.
- **Decision**: a validated control-flow result produced from model output: route label, gate
  result, plan (list of subtasks), verdict (approve or feedback). Recorded as a span's output.
- **Run, Span, Graph**: as in M1. Graph nodes gain kinds for code-only steps (gate, merge,
  route) so the UI can tell model calls from code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All five workflows run end to end with the local default model and finish with an
  answer for their sample prompt.
- **SC-002**: For every workflow, 100% of model and tool calls appear as spans whose node id is
  in that workflow's graph (verified by tests over scripted runs).
- **SC-003**: In a parallel or orchestrator run, the waterfall shows branch spans overlapping in
  time, and total run time is less than the sum of the branch times.
- **SC-004**: For every decision branch in User Story 2 and failure in User Story 3, a test shows
  the expected spans, taken edges and end state.
- **SC-005**: A reader can tell which pattern a replayed run used from its graph alone.
- **SC-006**: The owner can compare any two runs by model calls, tokens and wall time from the
  past-runs list, without opening either run.

## Future Scope (not planned in M2)

- **M3 MCP**: hand-written MCP JSON-RPC server and host.
- **M4 Harness**: budgets, timeouts, retries, context compaction, approval gates.
- **M5 Agent memory**: store, retrieve, reflect.
- **M6 RAG**: small retrieval pipeline with retrieve/rerank spans.
- **Phase 2 Village**: tick-driven runner over the same agents and workflows.

## Assumptions

- One model (the configured default, `qwen3:8b`) serves every call in every workflow; per-node
  model choice is out of scope.
- Parallelization covers sectioning only; voting (same prompt N times, aggregate) is out of scope.
- Orchestrator workers are plain model calls without tools; subtask cap is 4.
- Evaluator round cap is 3; chaining has exactly one gate (after the outline).
- Workflows run to completion inside one run; tick-driven execution remains a Phase 2 seam
  (M1's step-wise ReAct agent is unchanged).
- Invalid router output falls back to `general` (a safe, always-available handler); invalid plans
  end the run, since no safe default plan exists.
- A failed parallel branch does not cancel the others; the merge works with what succeeded and
  the run ends `error` only if every branch failed.
- Comparing runs side by side and editing prompts in the UI are out of scope (Phase 2); the
  per-run totals (FR-020) are the M2 comparison aid.
- With reasoning off, decision and worker calls take seconds; turning it on is a config change
  that yields a new `config_version`, so before/after runs stay distinguishable.
