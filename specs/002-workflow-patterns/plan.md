# Implementation Plan: M2 — Workflow Patterns

**Branch**: `main` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-workflow-patterns/spec.md`

## Summary

Five workflow modules (chain, routing, parallel, orchestrator, evaluator) on the M1 runtime. Three
shared, traced building blocks are extracted from the ReAct agent and reused everywhere: a model
call, a tool call, and a structured decision (JSON-schema output validated by a pydantic model).
A small registry lists the ReAct agent and the workflows; `POST /runs` takes an `agent_id`. Every
node visit records the node(s) it came from, so the UI marks taken edges from data instead of
guessing, which also covers fan-out, fan-in and loops. The UI gains an agent picker with graph
preview, multi-node highlighting and per-run totals.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged from M1 (FastAPI, uvicorn, pydantic, httpx; Next.js, React,
Tailwind, @xyflow/react; dev ruff, pyright strict, pytest, httpx2, eslint, vitest). No new
dependencies.

**Storage**: SQLite as in M1; no schema change (totals are computed by query).

**Testing**: pytest with `FakeLLM` (extended: callable script items, optional delay, recorded
request options); vitest for frontend view logic.

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: parallel/orchestrator runs finish faster than the sum of their branches
(SC-003); with reasoning off a workflow call takes seconds on `qwen3:8b`.

**Constraints**: no agent frameworks; structured output via the OpenAI-compatible
`response_format` (verified against local Ollama 0.21.2 + `qwen3:8b`); M1 runs keep replaying.

**Scale/Scope**: ≤ 4 workers, ≤ 3 evaluator rounds, one gate; single user.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Each workflow is one module (~80–150 lines) using three shared helpers; no framework, no new deps |
| II. Observable by default | Pass | Helpers are the only path to the model/tools and always open spans; every workflow declares its graph; decisions are spans; `lab.came_from` records edges |
| III. Secure local defaults | Pass | No new network surface; tools still argument-only; `agent_id` validated against the registry; structured output is still validated by code |
| IV. Smallest change | Pass | No workflow engine/DSL: each workflow is plain async code; registry is a dict; totals by SQL query, no migration |
| V. Gates + traceability | Pass | `make check` unchanged; FR → test map in `tasks.md` |

Post-design re-check: passes; no Complexity Tracking entries.

## Design

### Shared building blocks (`backend/src/agent_lab/agents/steps.py`)

Extracted from `agents/react.py` (behavior unchanged, ReAct switches to them):

| Helper | Span(s) | Notes |
|---|---|---|
| `chat(ctx, node_id, messages, *, tools=(), response_format=None, came_from=None)` | `llm "chat {model}"` | Today's `ReActAgent._chat`; passes the config's `reasoning` setting to the client |
| `call_tool(ctx, call, *, caller)` | `tool "execute_tool {name}"` | Today's `_call_tool` + `_parse_arguments`; unknown tools stay on the caller's node |
| `decide(ctx, node_id, name, messages, model_cls, *, kind=STEP, came_from=None) -> T` | decision span (`route` for the router, else `step`) with the `llm` call as child | Sends `response_format={"type":"json_schema", ...}` from `model_cls.model_json_schema()`; validates with `model_cls`; falls back to extracting one JSON object from prose/code fences; raises `DecisionError` (recorded on the decision span) |

`ctx` is a small dataclass `(llm, tracer, reasoning)` so helpers stay plain functions.

### Model client changes (`llm/base.py`, `llm/openai_compat.py`, `llm/fake.py`)

- `chat(messages, tools, *, response_format: dict | None = None, reasoning: bool | None = None)`.
  `reasoning=False` → `reasoning_effort: "none"`; `None`/`True` → provider default.
  `response_format` passed through. Both are recorded in the llm span's `attributes`
  (`gen_ai.request.response_format`, `lab.reasoning`) and the schema is in the decision span's input.
- `FakeLLM`: script items may also be `Callable[[list[Message]], ChatResponse]` (needed when
  concurrent branches pop in nondeterministic order); optional `delay` seconds; `requests` records
  `response_format`/`reasoning` per call.

### Workflows (`backend/src/agent_lab/workflows/`)

Each module exports `AGENT_ID`, `NAME`, `DESCRIPTION`, `SAMPLE_PROMPT`, a pydantic `Config`
(model, `reasoning=False`, prompts, caps), `build_graph()` and a class with
`async run(prompt) -> Outcome(status, answer)`. Each run opens the root span
`invoke_agent {id}` at `start` and ends with a span at `end`, as ReAct does.

| Module | Nodes (kind) | Flow |
|---|---|---|
| `chain.py` | start, outline (llm), gate (code), draft (llm), polish (llm), end | gate: ≥ 3 non-empty bullet lines in the outline; fail → end with error |
| `routing.py` | start, router (llm), math (llm), weather (llm), general (llm), tool:calculator, tool:get_weather, end | `decide(Route{label: Literal[...]}, kind=route)`; invalid → `general`; math/weather: model call with its one tool → run tool calls → model call without tools |
| `parallel.py` | start, clarity, tone, claims (llm), merge (llm), end | `asyncio.gather(..., return_exceptions=True)` inside a `step "sections"` span; merge gets successful reviews; all failed → `error` |
| `orchestrator.py` | start, orchestrator (llm), worker (llm), synthesizer (llm), end | `decide(Plan{subtasks: list[str] 1..4})`; invalid → `error`; workers gathered, span `worker {i}` with `lab.worker.index` |
| `evaluator.py` | start, generator (llm), evaluator (llm), end | rounds 1..3: generate (with last feedback) → `decide(Verdict{approved, feedback})`; spans carry `lab.round`; cap → `max_iterations`, answer = last draft; invalid verdict → treated as not approved, feedback = error text |

ReAct: `ReActConfig` gains `reasoning: bool = True` (new `config_version` for new ReAct runs;
old runs keep theirs).

### Registry and runs (`agents/registry.py`, `runs.py`)

- `registry.py`: `AGENTS: dict[str, AgentSpec]` with `AgentSpec(id, name, description,
  sample_prompt, make_config(llm), graph(config), create(llm, config, tracer))`; ReAct first.
- `runs.new_run(prompt, agent_id, llm, secrets)` and `execute_run` dispatch through the registry;
  everything else (tracer → store + bus, `run_ended`) is unchanged.

### Edges taken: recorded, not inferred

- The span that starts a node visit carries `attributes["lab.came_from"] = [node ids]`
  (e.g. merge ← `["clarity","tone","claims"]`, generator round 2 ← `["evaluator"]`,
  ReAct llm ← `["start"]` or the tools of the previous turn). Set via the helpers' `came_from`.
- Backend tests assert every `(came_from, node_id)` pair is a declared graph edge.
- UI `takenEdges`: edges from `lab.came_from` when any span has it; otherwise the M1 inference
  (kept for M1 runs, FR-016).
- UI `activeNodes` (replaces `activeNode`): nodes of all running spans that have no running child.

### Run totals

- Backend: `store.list_runs`/`get_run` add `totals {llm_calls, tool_calls, tokens_in, tokens_out,
  wall_ms}` via one aggregate query over `spans` (works for M1 runs); `wall_ms` from run times
  (null while running).
- UI: run header computes the same totals live from spans (`runTotals` in `run-state.ts`); the
  list uses the stored ones.

### API (see contracts/http-api.md)

- `GET /agents` → `[AgentInfo]` (id, name, description, sample_prompt, graph).
- `POST /runs {prompt, agent_id = "react"}`; unknown `agent_id` → 422.
- `Run` gains `totals`. WS stream unchanged.

### UI

- Agent picker above the prompt (radio group): selecting one shows its description, fills the
  sample prompt and previews its graph (no run).
- Node kind `code` (gate) drawn distinctly from `llm`; backward edges (evaluator → generator)
  use bottom handles so loops don't overlap forward edges.
- Run header: totals; past-runs list: agent name + totals.

## Project Structure

### Documentation (this feature)

```text
specs/002-workflow-patterns/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md  contracts/trace-conventions.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/src/agent_lab/
├── agents/steps.py         # new: chat, call_tool, decide (extracted from react.py)
├── agents/registry.py      # new: AGENTS
├── agents/react.py         # uses steps; reasoning setting
├── workflows/              # new: chain, routing, parallel, orchestrator, evaluator
├── llm/base.py, openai_compat.py, fake.py   # response_format, reasoning, fake extensions
├── graph.py                # node kind "code"
├── store.py, runs.py, api.py               # totals, registry dispatch, GET /agents
backend/tests/
├── test_steps.py, test_workflow_{chain,routing,parallel,orchestrator,evaluator}.py
frontend/src/
├── lib/api.ts, lib/run-state.ts (+ tests)  # agents, totals, came_from edges, activeNodes
└── components/AgentPicker.tsx, GraphView.tsx, RunViewer.tsx, RunList.tsx, app/page.tsx
```

**Structure Decision**: extend the M1 layout; workflows get their own package beside `agents/`.

## Complexity Tracking

None.
