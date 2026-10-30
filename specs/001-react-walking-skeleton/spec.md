# Feature Specification: M1 — ReAct Walking Skeleton

**Feature Branch**: `main` (feature directory `001-react-walking-skeleton`)

**Created**: 2026-10-30

**Status**: Draft

**Input**: Agent Lab Phase 1, milestone M1: a traced ReAct agent with two tools, an API to
start/inspect/stream runs, and a one-page UI that shows the agent's graph, a span waterfall,
span details and past runs (live and replay).

## Context

Agent Lab is a learning playground for agent fundamentals, hand-built (no agent frameworks),
with a live visualization of every step next to the running app. M1 is the walking skeleton:
one module (ReAct) end to end, with the tracing, storage, streaming and UI that every later
module reuses.

The core contracts below are part of this spec on the owner's explicit request, even though
they are more technical than a typical spec.

### Core contracts

1. **Every step emits a span; no untraced LLM or tool call.** A span carries:
   `trace_id, span_id, parent_span_id, run_id, agent_id, node_id, config_version,
   kind (llm | tool | route | retrieve | rerank | memory | step), name, input, output, error,
   started_at, ended_at, tokens_in, tokens_out, model`. Attribute names follow OpenTelemetry
   GenAI semantic conventions where cheap; no OTel SDK.
2. **Every agent or workflow declares its static graph** (`nodes`, `edges`) as data. Spans
   reference a `node_id`, which is how the UI highlights the active node and the route taken.
3. **Spans are persisted and streamed live.** Live view and replay of a stored run render from
   the same data.
4. **Security.** Backend and frontend listen on 127.0.0.1 only. API keys and auth headers are
   redacted before spans are stored. Tools get no filesystem or network access unless
   explicitly scoped.

## Clarifications

### Session 2026-10-30

- Q: Should the UI show model output token-by-token while an LLM span is running, or only when
  the span ends? → A: Span-level only; model calls are non-streaming.
- Q: What should an LLM span's input contain? → A: The full message list sent to the model
  (after redaction).
- Q: Should a running run be cancellable from the UI in M1? → A: No; the iteration cap bounds
  every run, cancellation comes with the M4 harness.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Run the ReAct agent and watch it live (Priority: P1)

The owner types a prompt (e.g. "What is 17*23 plus the temperature in Berlin?"), starts a run,
and watches the agent's graph light up node by node while spans appear in a waterfall. They
click a span to see its input, output, token counts and latency.

**Why this priority**: this is the whole point of the lab: see each agent step as it happens.

**Independent Test**: start a run against a scripted fake model and verify the live stream
delivers every span, in order, with node ids from the declared graph.

**Acceptance Scenarios**:

1. **Given** the app is running, **When** the owner submits a prompt that needs both tools,
   **Then** the run produces a step span per iteration with child LLM and tool spans, and the
   final answer appears.
2. **Given** a run is in progress, **When** a new span starts, **Then** the graph highlights
   that span's node and the waterfall shows it as running until it ends.
3. **Given** a finished span, **When** the owner selects it, **Then** the detail panel shows its
   input, output, error (if any), tokens in/out, model and latency.

---

### User Story 2 - Replay a past run (Priority: P2)

The owner opens the list of past runs, picks one, and sees the same graph, waterfall and
details as in the live view, built from stored data.

**Why this priority**: comparing runs after the fact is the basis for later milestones and
Phase 2 (fork and compare).

**Independent Test**: complete a run, restart the backend, fetch and stream the run again, and
verify the spans are identical to the live ones.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the owner opens it from the run list, **Then** all its
   spans render in the graph, waterfall and detail panel.
2. **Given** a run that is still in progress, **When** the owner opens it, **Then** already
   stored spans render first and new spans continue to arrive live.

---

### User Story 3 - Trust the failure paths (Priority: P3)

The owner sees what happens when a tool fails or the model never stops calling tools: the error
is visible in a span, and the run ends at a hard iteration cap instead of looping forever.

**Why this priority**: failure behavior is part of what the lab is meant to teach, and the cap
is a basic safety budget.

**Independent Test**: scripted fake model runs that (a) send a bad calculator expression and
(b) call tools forever.

**Acceptance Scenarios**:

1. **Given** the model calls a tool with invalid input, **When** the tool fails, **Then** the
   tool span records the error, the error is fed back to the model, and the run continues.
2. **Given** the model keeps calling tools, **When** the iteration cap is reached, **Then** the
   run ends with status `max_iterations` and no further LLM calls are made.

### Edge Cases

- Model requests a tool that does not exist → tool span with error `unknown tool`, fed back to
  the model.
- Model returns malformed tool arguments (not valid JSON) → tool span with error, fed back.
- Model endpoint unreachable or returns HTTP error → LLM span with error; run ends with status
  `error`.
- Calculator input with names, calls, attribute access or oversized exponents → rejected with
  an error, never evaluated.
- WebSocket client connects to an unknown run → connection closed with an error message.
- WebSocket client connects after the run finished → receives all stored spans, then the
  stream closes.
- Secrets appear inside free-text span input (e.g. a prompt containing a bearer token) →
  redacted before storage.

## Requirements *(mandatory)*

### Functional Requirements

**Agent and tools**

- **FR-001**: The system MUST provide a ReAct agent that alternates model calls and tool calls
  until the model returns a final answer without tool calls.
- **FR-002**: The agent MUST stop after a configurable maximum number of iterations (default 6)
  and mark the run `max_iterations`.
- **FR-003**: The system MUST provide a `calculator` tool that evaluates arithmetic
  (`+ - * / % **`, parentheses, unary minus, integers and decimals) with a hand-written parser,
  without `eval`/`exec`, and rejects anything else.
- **FR-004**: The system MUST provide a `get_weather` tool that returns deterministic fake
  weather for a city name (same input → same output).
- **FR-005**: A tool error (invalid input, unknown tool, malformed arguments) MUST be recorded
  on the tool span and returned to the model as the tool result; it MUST NOT crash the run.
- **FR-006**: Tools MUST declare their access scopes; M1 tools declare none and receive no
  filesystem or network access.

**Model access**

- **FR-007**: The system MUST call models through its own thin client for the
  OpenAI-compatible chat completions API with native tool calling; provider, base URL, model
  and API key come from environment variables, defaulting to local Ollama.
- **FR-008**: The model client MUST sit behind an interface that a second provider adapter
  (Anthropic) can implement later without changes to the agent.
- **FR-009**: The system MUST include a fake model that replays scripted responses, and the
  test suite MUST NOT need a real model.

**Tracing**

- **FR-010**: Every agent iteration, model call and tool call MUST produce a span with all
  fields of core contract 1, nested via `parent_span_id` (iteration → model/tool calls).
- **FR-011**: Model spans MUST record the model name, the full message list sent (as input),
  the response (as output) and input/output token counts reported by the provider. Model calls
  are non-streaming; spans update only on start and end.
- **FR-012**: The agent MUST declare its static graph (nodes and edges) as data, and every
  span MUST reference a node id from that graph.
- **FR-013**: Each run MUST record `agent_id` and a `config_version` derived deterministically
  from the agent configuration (system prompt, model, tools, iteration cap).
- **FR-014**: API keys, auth headers and bearer/API-key-shaped strings MUST be redacted from
  span input, output and error before a span is stored or streamed.

**Storage and API**

- **FR-015**: Runs and spans MUST be persisted locally so they survive a backend restart.
- **FR-016**: `POST /runs` with a prompt MUST start a run asynchronously and return its id.
- **FR-017**: `GET /runs/{id}` MUST return the run (status, agent graph, final answer) and its
  spans; `GET /runs` MUST list past runs, newest first.
- **FR-018**: `WS /runs/{id}/stream` MUST send all spans already stored for the run, then live
  span start/end events until the run ends, then close.
- **FR-019**: Backend and frontend MUST listen on 127.0.0.1 only; the backend MUST accept
  browser requests only from the local frontend origin.

**UI (one page)**

- **FR-020**: The page MUST offer a prompt input that starts a run.
- **FR-021**: The page MUST render the agent's declared graph, highlight the active node and
  mark the edges taken so far.
- **FR-022**: The page MUST render a waterfall of spans (nesting, relative start, duration,
  running vs. finished vs. error).
- **FR-023**: Selecting a span MUST show its input, output, error, tokens in/out, model and
  latency.
- **FR-024**: The page MUST list past runs; opening one replays it from stored spans using the
  same rendering as the live view.

**Repository**

- **FR-025**: One command (`make check`) MUST run all quality gates (backend lint, format check,
  type check, tests; frontend lint, type check).
- **FR-026**: The repository MUST contain `AGENTS.md` (commands, gates, layout, contracts),
  `CLAUDE.md` (pointer to `AGENTS.md`) and `README.md` (run instructions).

### Key Entities

- **Run**: one execution of an agent on a prompt. Id, agent id, config version, prompt,
  status (`running | completed | max_iterations | error`), final answer, started/ended times.
- **Span**: one traced step (core contract 1). Belongs to a run; optional parent span; points
  at a graph node.
- **Agent graph**: static nodes (id, label, kind) and edges (source, target) declared by an
  agent; stored with the run so replay does not depend on current code.
- **Agent config**: system prompt, model, tool names, iteration cap; hashed into
  `config_version`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of model and tool calls in a run appear as spans with a valid node id (verified
  by tests over scripted runs).
- **SC-002**: A span appears in the live view within 1 second of starting or ending.
- **SC-003**: Replaying a stored run shows exactly the same spans (ids, nesting, inputs,
  outputs) as the live view did.
- **SC-004**: No stored span contains a configured API key or an auth header value (verified by
  a test that scans the stored data).
- **SC-005**: Every functional requirement maps to at least one automated test or an explicit
  manual check listed in `tasks.md`, and `make check` passes.

## Future Scope (not planned in M1)

- **M2 Workflow patterns**: chaining, routing, parallel, orchestrator-workers,
  evaluator-optimizer on the same tracing/graph runtime.
- **M3 MCP**: hand-written MCP JSON-RPC server and host.
- **M4 Harness**: budgets, retries, context compaction, approval gates.
- **M5 Agent memory**: store, retrieve, reflect.
- **M6 RAG**: a small retrieval pipeline with retrieve/rerank spans.
- **Phase 2 Village**: 2D world of LLM villagers on the same runtime (live-editable prompts and
  flows, per-agent history and stats, fork-and-compare), driven by a tick runner; relies on
  M1's agent ids, config versions and step-wise agent loop.

## Assumptions

- Single local user; no authentication beyond the loopback-only binding.
- Agent/tool errors are fed back to the model (standard ReAct), only transport-level model
  errors end the run.
- Default model for manual runs is `qwen3:8b` on local Ollama; it must be pulled separately.
- Run history is kept indefinitely in a local database file; no retention policy in M1.
- Runs cannot be cancelled in M1; the iteration cap bounds them.
- Multiple runs may execute concurrently; each streams independently.
- The ReAct graph has one node per tool so the route taken is visible:
  `start → llm → {calculator, get_weather} → llm → end`.
