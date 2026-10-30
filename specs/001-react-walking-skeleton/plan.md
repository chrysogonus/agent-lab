# Implementation Plan: M1 — ReAct Walking Skeleton

**Branch**: `main` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-react-walking-skeleton/spec.md`

## Summary

A hand-written ReAct agent (two tools) runs as a background task in a FastAPI process. A small
tracer wraps every iteration, model call and tool call in a span (core contract 1), redacts it,
upserts it into SQLite and publishes it on an in-process bus. A WebSocket endpoint sends a run's
stored spans and then live events; the Next.js page consumes only that stream, so live view and
replay share one code path. The agent declares its graph as data; the UI derives the active node
and the route taken from span `node_id`s.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js App Router (frontend)

**Primary Dependencies**: FastAPI, uvicorn[standard], pydantic, httpx; Next.js, React,
Tailwind, @xyflow/react. Dev: ruff, pyright (strict), pytest (+ anyio plugin shipped with anyio), httpx2 (for
Starlette's test client), eslint, vitest.

**Storage**: SQLite via stdlib `sqlite3`, one file (`AGENT_LAB_DB`, default `backend/data/agent_lab.db`)

**Testing**: pytest with `FakeLLM`; FastAPI `TestClient` for HTTP and WebSocket;
`httpx.MockTransport` for the model client; vitest for `frontend/src/lib/run-state.ts`

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: span visible in UI < 1 s after start/end (SC-002); nothing else

**Constraints**: no agent frameworks or MCP SDKs; no `eval`; loopback binding; no real model in
tests

**Scale/Scope**: single user, runs of ≤ 6 iterations, hundreds of stored runs

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Loop, tool calling, tracer, client, parser all hand-written; each module < ~200 lines; only approved deps |
| II. Observable by default | Pass | Tracer context manager is the only way the agent calls the model or a tool; graph declared as data; spans upserted to SQLite + streamed over WS |
| III. Secure local defaults | Pass | uvicorn/next bound to 127.0.0.1; CORS + WS `Origin` check + trusted-host check; redaction in the tracer before any sink; tools receive only parsed args, declare scopes, agent refuses ungranted scopes |
| IV. Smallest change | Pass | Seams limited to `LLMClient` protocol, `agent_id`/`config_version`, `agent.step()` |
| V. Gates + traceability | Pass | `make check`; FR → test map in `tasks.md` |

Post-design re-check: still passes; no Complexity Tracking entries.

## Design

### Backend modules (`backend/src/agent_lab/`)

| Module | Responsibility |
|---|---|
| `config.py` | `Settings` dataclass from env (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `AGENT_LAB_DB`) |
| `llm/base.py` | `LLMClient` protocol (`model`, `async chat(messages, tools) -> ChatResponse`), `ChatResponse`, `ToolCall`, `LLMError` — the provider seam |
| `llm/openai_compat.py` | httpx client for `POST {base}/chat/completions`, non-streaming, native tools |
| `llm/fake.py` | `FakeLLM`: replays scripted `ChatResponse`s / exceptions, records calls |
| `tracing/span.py` | `SpanKind`, `Span` (contract 1 + `attributes` with GenAI names) |
| `tracing/redact.py` | recursive redaction: sensitive keys, bearer/`sk-` patterns, known secret values |
| `tracing/tracer.py` | `Tracer.span(...)` async context manager; parent via `contextvars`; redacts, then calls the sink on start and end |
| `graph.py` | `Node`, `Edge`, `Graph` (nodes carry hand-set x/y for the UI) |
| `tools/base.py`, `tools/calculator.py`, `tools/weather.py` | `Tool`, `ToolError`; recursive-descent calculator; deterministic weather |
| `agents/react.py` | `ReActConfig`, `config_version()`, `build_graph()`, `ReActAgent.start()/step()`, `run_to_completion()` |
| `store.py` | sqlite: `runs`, `spans`; upsert span; list/get |
| `bus.py` | per-run `asyncio.Queue` fan-out |
| `runs.py` | `execute_run()`: wires tracer → store + bus, runs agent, finishes run, publishes `run_ended` |
| `api.py` | `create_app(store, llm, settings)`: routes, CORS, trusted hosts, WS origin check |
| `main.py` | `app = create_app(...)` from env (uvicorn entry) |

### Span tree for one run

```
step  "invoke_agent react"   node=start   input=prompt         output=answer
├─ step "iteration 1"        node=llm
│  ├─ llm  "chat qwen3:8b"   node=llm     input=messages        output=assistant msg, tokens
│  └─ tool "execute_tool calculator" node=tool:calculator input=args output=result | error
├─ step "iteration 2"        node=llm
│  └─ llm  "chat qwen3:8b"   node=llm
└─ step "final answer"       node=end     output=answer | error="max iterations (6) reached"
```

Spans are emitted (and upserted) on start and on end. Tool and argument errors are set on the
tool span and fed back to the model; only exceptions escaping the agent (model transport errors)
propagate, marking every open ancestor span with the error, and set run status `error`.
Unknown-tool spans use `node_id=llm` (the requesting node), since they have no graph node.

### Graph (ReAct)

Nodes: `start`, `llm`, `tool:calculator`, `tool:get_weather`, `end`.
Edges: `start→llm`, `llm→tool:*`, `tool:*→llm`, `llm→end`.
UI route = span `node_id`s ordered by `started_at`, consecutive duplicates collapsed, kept where
the pair is a declared edge. Active node = node of the deepest span without `ended_at`.

### Phase 2 seams (only these)

- `agent_id` + `config_version` (sha256 of canonical config JSON, 12 hex chars) on every span/run.
- `ReActAgent.step(state)` performs one iteration; `run_to_completion` is a plain loop a future
  tick runner replaces.
- `LLMClient` protocol; an Anthropic adapter implements it later.

### Security

- `uvicorn --host 127.0.0.1`, `next dev -H 127.0.0.1`.
- CORS allow-list `http://127.0.0.1:3000`, `http://localhost:3000`; WebSocket handshakes with any
  other `Origin` are rejected (CORS does not cover WS); `TrustedHostMiddleware` limits `Host` to
  loopback names (DNS rebinding).
- Redaction runs in the tracer, before store and bus. Known secret values (`LLM_API_KEY`) are
  also scrubbed from strings. The model client never puts headers in spans.
- Calculator: hand-written parser, input ≤ 200 chars, `|exponent| ≤ 64`, overflow/zero-division
  → `ToolError`.

## Project Structure

### Documentation (this feature)

```text
specs/001-react-walking-skeleton/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md  contracts/stream-events.md
└── tasks.md
```

### Source Code (repository root)

```text
Makefile             # install, check, check-backend, check-frontend, dev-backend, dev-frontend
.env.example
AGENTS.md  CLAUDE.md  README.md
backend/
├── pyproject.toml   # uv project, ruff + pyright + pytest config
├── src/agent_lab/   # modules above
└── tests/           # test_tools, test_llm_client, test_react, test_redaction, test_store, test_api
frontend/
├── package.json
└── src/
    ├── app/page.tsx             # the single page
    ├── lib/api.ts               # types + fetch/ws helpers
    ├── lib/run-state.ts         # span upsert, route, active node
    └── components/              # PromptForm, RunList, GraphView, Waterfall, SpanDetail
```

**Structure Decision**: web-app layout with `backend/` (uv package `agent_lab`) and `frontend/`
(Next.js), per the constitution.

## Complexity Tracking

None.
