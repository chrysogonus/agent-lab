# AGENTS.md

Agent Lab: hand-built agent fundamentals (ReAct, five workflow patterns and a builder for
custom agents now; MCP, harness, memory, RAG later) with a live trace view. Rules for every
change: `.specify/memory/constitution.md`. Current feature spec, plan and tasks:
`specs/003-agent-builder/` (M2: `specs/002-workflow-patterns/`, M1:
`specs/001-react-walking-skeleton/`).

## Commands

```bash
make install        # uv sync + pnpm install
make check          # all gates; must pass before a task is marked done
make dev-llm        # vLLM (Docker, detached) on 127.0.0.1:8001, model "qwen3.5-9b"; needs the GPU
make stop-llm       # remove the vLLM container (next dev-llm recreates it with current flags)
make dev            # dev-backend and dev-frontend together; Ctrl-C stops both
make dev-backend    # FastAPI on 127.0.0.1:8000 (reads ./.env if present)
make dev-frontend   # Next.js on 127.0.0.1:3000
cd backend && uv run pytest tests/test_react.py -k max_iterations   # one test
```

Gates in `make check`: backend `ruff check`, `ruff format --check`, `pyright` (strict), `pytest`;
frontend `eslint`, `next typegen && tsc --noEmit`, `vitest run`. When a gate keeps failing, stop and
report; keep every gate at its current strictness.

## Layout

- `backend/src/agent_lab/`: `agents/` (`react.py`; `steps.py`: traced `chat`, `call_tool`,
  `decide`; `registry.py`: the six templates by id; `config_fields.py`: shared field rules),
  `workflows/` (chain, routing, parallel, orchestrator, evaluator), `blocks/` (block agents:
  `model.py` types and layout rules, `graph.py`, `run.py`, `convert.py` templates as blocks),
  `tools/` (`catalog.py`:
  every tool by name), `llm/` (client seam, `models.py`: the configured models, `FakeLLM`),
  `tracing/` (span, tracer, redaction), `store.py` (SQLite: runs, spans, custom agents),
  `bus.py`, `runs.py`, `api.py`.
- `backend/tests/`: pytest; `helpers.py` builds scripted runs and `assert_trace_valid`;
  `test_templates.py` pins the templates to `golden/templates.json` (M2 behavior).
- `frontend/src/`: `app/page.tsx` (the one page), `components/` (`AgentBuilder.tsx` and
  `builder/`), `lib/run-state.ts` and `lib/builder.ts` (pure view and builder logic, tested next
  to them; keep testable logic there, not in components). Next.js 16 differs from older
  versions: read `frontend/AGENTS.md` before editing.

## Contracts

1. **Every LLM and tool call runs inside `Tracer.span(...)`**, reached only through
   `agents/steps.py` (`chat`, `call_tool`, `decide`). Span fields are fixed by
   `tracing/span.py`; extra metadata goes in `attributes` under OpenTelemetry GenAI names
   (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, ...) or `lab.*`.
2. **Agents and workflows declare a static graph** (`graph.py`: nodes with x/y, edges). Every
   span's `node_id` is a node of that graph. The first span of each node visit records
   `lab.came_from` (the node ids control came from); every such pair must be a declared edge,
   including error exits. The UI marks taken edges from it
   (`specs/002-workflow-patterns/contracts/trace-conventions.md`).
3. **Spans are upserted to SQLite on start and end and published on the bus.** The UI reads
   only `WS /runs/{id}/stream` (stored spans, then live), so live view and replay share one path.
4. **Security.** Bind to 127.0.0.1. The tracer redacts before any sink sees a span. Tools get
   parsed arguments only and declare `scopes`; agents reject ungranted scopes. The API checks
   `Host`, CORS origin and WebSocket `Origin`.
5. **Templates and custom agents.** Each template's pydantic `Config` is the only definition of
   its editable fields, defaults and limits; graphs and decision schemas are derived from it.
   A custom agent is a stored (template id, config) that the server validates with that model;
   runs snapshot name, template, config and graph. Templates must keep sending exactly their
   M2 requests: `test_templates.py` fails otherwise (`UPDATE_GOLDEN=1` only for intended
   changes). Fill prompt placeholders with `config_fields.fill`, never `str.format`.
   Block agents are custom agents with `template_id` `"blocks"`: `blocks/run.py` reaches the
   model and the tools only through `steps.chat`, `call_tool` and `decide`, and every node that
   can stop a run has an edge to `end` in `blocks/graph.py`.
6. **Run identity**: every run records its `agent_id` and `config_version` (hash of the
   agent's config), so runs of different configs stay apart. The only forward-looking seam is
   the provider seam for a future Anthropic adapter; add no other.

## Working rules

- Hand-write agent logic; agent frameworks and MCP SDKs stay out. Ask the owner before adding
  any dependency.
- Tests use `FakeLLM` or `httpx.MockTransport`, never a real model or provider.
- Each milestone is one Spec Kit feature: `speckit-specify` → `clarify` → `plan` → `tasks` →
  `implement`. Map every requirement to a test in `tasks.md`. Commit after each phase and task
  group; never push.
- `.env` holds `LLM_API_KEY` and `OPENAI_API_KEY`; keep it out of git. Both are passed to the
  tracer as secrets; never return a key or provider URL from the API.
