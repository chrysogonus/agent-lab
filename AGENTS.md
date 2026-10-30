# AGENTS.md

Agent Lab: hand-built agent fundamentals (ReAct now; workflows, MCP, harness, memory, RAG
later) with a live trace view. Rules for every change: `.specify/memory/constitution.md`.
Current feature spec, plan and tasks: `specs/001-react-walking-skeleton/`.

## Commands

```bash
make install        # uv sync + pnpm install
make check          # all gates; must pass before a task is marked done
make dev-backend    # FastAPI on 127.0.0.1:8000 (reads ./.env if present)
make dev-frontend   # Next.js on 127.0.0.1:3000
cd backend && uv run pytest tests/test_react.py -k max_iterations   # one test
```

Gates in `make check`: backend `ruff check`, `ruff format --check`, `pyright`, `pytest`;
frontend `eslint`, `next typegen && tsc --noEmit`, `vitest run`. When a gate keeps failing, stop and
report; keep every gate at its current strictness.

## Layout

- `backend/src/agent_lab/`: `agents/` (agent loops), `tools/`, `llm/` (client seam + `FakeLLM`),
  `tracing/` (span, tracer, redaction), `store.py` (SQLite), `bus.py`, `runs.py`, `api.py`.
- `backend/tests/`: pytest; `helpers.py` builds scripted runs.
- `frontend/src/`: `app/page.tsx` (the one page), `components/`, `lib/run-state.ts` (pure view
  logic, tested in `lib/run-state.test.ts`; keep testable logic there, not in components). Next.js 16 differs from older versions: read `frontend/AGENTS.md` before editing.

## Contracts

1. **Every LLM and tool call runs inside `Tracer.span(...)`.** Span fields are fixed by
   `tracing/span.py`; extra metadata goes in `attributes` under OpenTelemetry GenAI names
   (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, ...).
2. **Agents declare a static graph** (`graph.py`: nodes with x/y, edges). Every span's
   `node_id` is a node of that graph; the UI derives the active node and route from it.
3. **Spans are upserted to SQLite on start and end and published on the bus.** The UI reads
   only `WS /runs/{id}/stream` (stored spans, then live), so live view and replay share one path.
4. **Security.** Bind to 127.0.0.1. The tracer redacts before any sink sees a span. Tools get
   parsed arguments only and declare `scopes`; agents reject ungranted scopes. The API checks
   `Host`, CORS origin and WebSocket `Origin`.
5. **Phase 2 seams**: `agent_id`, `config_version` (hash of agent config) and
   `ReActAgent.step()` (one iteration, so a tick runner can drive it). Add no other
   forward-looking abstractions.

## Working rules

- Hand-write agent logic; agent frameworks and MCP SDKs stay out. Ask the owner before adding
  any dependency.
- Tests use `FakeLLM` or `httpx.MockTransport`, never a real model.
- Each milestone is one Spec Kit feature: `speckit-specify` → `clarify` → `plan` → `tasks` →
  `implement`. Map every requirement to a test in `tasks.md`. Commit after each phase and task
  group; never push.
- `.env` holds `LLM_API_KEY`; keep it out of git.
