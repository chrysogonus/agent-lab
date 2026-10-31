# Agent Lab Constitution

## Core Principles

### I. Hand-Built and Readable over Clever

- Agent loops, routers, tool calling, tracing and (later) the MCP JSON-RPC layer MUST be
  hand-written. Agent frameworks (LangChain, LangGraph, LlamaIndex, CrewAI, OpenAI Agents SDK)
  and MCP SDKs MUST NOT be used.
- Plain libraries (httpx, numpy, pydantic) are allowed. Any dependency not listed under
  "Technology Constraints" MUST be approved by the owner before it is added.
- Each module MUST be small enough to read in one sitting. Prefer explicit code over
  indirection, metaprogramming or generic plugin machinery.

Rationale: the project exists to learn agent fundamentals by building them.

### II. Observable by Default

- Every step MUST emit a span. There MUST be no untraced LLM call or tool call.
- Span fields: `trace_id, span_id, parent_span_id, run_id, agent_id, node_id, config_version,
  kind (llm|tool|route|retrieve|rerank|memory|step), name, input, output, error, started_at,
  ended_at, tokens_in, tokens_out, model`. Attribute names follow the OpenTelemetry GenAI
  semantic conventions where cheap; no OTel SDK dependency until explicitly approved.
- Every agent or workflow MUST declare its static graph (`nodes`, `edges`) as data. Spans
  reference a `node_id` from that graph.
- Spans MUST be persisted to SQLite and streamed over a WebSocket. Live view and replay of a
  stored run MUST render from the same data.

Rationale: seeing every step is the point of the lab.

### III. Secure Local Defaults

- Backend and frontend MUST bind to 127.0.0.1 only.
- API keys and auth headers MUST be redacted before a span is stored or streamed.
- Tools get no filesystem or network access unless a scope is explicitly declared and granted.
- Tool inputs from the model are untrusted: no `eval`/`exec` of model output.

### IV. Smallest Change That Works

- Build only what the current milestone needs. No speculative abstractions.
- The only sanctioned forward-looking seam is the provider seam for a future Anthropic
  adapter. Stable agent ids and config versions are core features (runs record which agent ran
  with which config), not seams for later work.

### V. Quality Gates and Traceability

- One command, `make check`, runs every gate:
  backend `ruff check`, `ruff format --check`, `pyright` (strict), `pytest`;
  frontend `eslint`, `tsc --noEmit`, `vitest run`.
- A gate MUST pass before any task is marked done. Gates MUST NOT be weakened to make a change
  pass; a persistently failing gate is reported to the owner instead.
- Frontend view logic (state reduction, graph highlighting) lives in pure modules covered by
  vitest; components stay thin.
- Tests MUST NOT require a real model; they use a `FakeLLM` that replays scripted responses.
- Each functional requirement in a spec MUST map to at least one test, referenced in
  `tasks.md`.

## Technology Constraints

- Backend: Python 3.12, FastAPI (served by uvicorn), uv, pydantic, sqlite3 (stdlib), httpx.
  Dev: ruff, pyright, pytest (async tests via the anyio pytest plugin), httpx2 (Starlette
  test client).
- Frontend: Next.js (TypeScript, App Router), Tailwind, pnpm, @xyflow/react. Dev: eslint,
  vitest.
- LLM access: a thin own client over the OpenAI-compatible `/v1/chat/completions` API with
  native tool calling. Provider, base URL and model come from the environment. Default target:
  vLLM (Docker image `vllm/vllm-openai`, started by `make dev-llm`) at `http://localhost:8001/v1`,
  bound to 127.0.0.1. Ollama remains supported as an alternative OpenAI-compatible endpoint.
- Layout: monorepo with `backend/`, `frontend/`, `specs/`, `.specify/`.

## Development Workflow

- Each milestone is one Spec Kit feature: constitution → specify → clarify → plan → tasks →
  implement.
- Commit after each Spec Kit phase and after each completed task group. Commit messages are
  short. No remote is created or pushed to without the owner's request.
- `AGENTS.md` is the runtime guide for coding agents (commands, gates, layout, contracts);
  `CLAUDE.md` points to it.

## Governance

- This constitution supersedes other project practices. Plans MUST include a Constitution
  Check against these principles; any violation MUST be justified in the plan's Complexity
  Tracking table or removed.
- Amendments are made via the constitution command, recorded with a version bump:
  MAJOR for removed or redefined principles, MINOR for new principles or sections, PATCH for
  wording.
- Reviews verify gate results, span coverage of new LLM/tool calls, and requirement → test
  mapping.

**Version**: 1.4.0 | **Ratified**: 2026-10-30 | **Last Amended**: 2026-10-31
