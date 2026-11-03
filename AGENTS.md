# AGENTS.md

Glasshouse: hand-built agent fundamentals (ReAct, five workflow patterns, a template and block
builder, per-agent models) with a live trace view, plus a village of four villager agents
(M6–M15). Rules for every change: `.specify/memory/constitution.md`. Current feature:
`specs/015-daily-happenings/`; earlier milestones in `specs/001-…` to `specs/014-…`. Human
documentation: `README.md` and `docs/` (keep both in step with user-visible changes).

## Commands

```bash
make install        # uv sync + pnpm install
make check          # all gates; must pass before a task is marked done
make dev-llm        # vLLM (Docker, detached) on 127.0.0.1:8001, model "qwen3.5-9b"; needs the GPU
make eval-checks    # turn checks on the real model (not a gate); results in backend/data/evals.db
make eval-scenarios # scenarios on fresh copies of the database (not a gate)
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
  `village/` (`world.py` map, homes, clock, villagers with sleeping hours and routines;
  `turn.py` observations (facts before claims), actions and beliefs text; `intention.py` what a
  villager set out to do and its next step; `affordances.py` what it can do where it stands;
  `plan.py` daily plans
  and the planner agent; `work.py` work, baskets, giving and the festival stalls; `trade.py`
  the daily trader and what villagers carry; `build.py` the catalogue, the building site and
  building work; `meeting.py` the town hall meeting and the meeting agent; `meeting_runs.py`
  the meeting's runs (a mixin of the runner); `happenings.py` the day's happenings; `boat.py`
  boat trips; `happening_runs.py` their runner part and whispers (a mixin); `memory.py`
  lasting memories, recall and reflection; `seasons.py` calendar, light, weather and growth;
  `chronicle.py` the nightly chronicle; `runner.py` the step loop, background decisions,
  plans, meetings, reflections, the chronicle and the day trail; `health.py` and
  `health_view.py` village health per day; `evals/` turn checks, scenarios and their results,
  run with `python -m agent_lab.village.evals`; specs/007-village-life/ to
  specs/015-daily-happenings/), `backend/evals/` (the shipped checks and scenarios, JSON),
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
   Village decisions are ordinary runs of the villagers' block agents, tagged with
   `village_tick` (the step they started in) and `villager`; the village never calls the model
   directly, and model answers become a validated action (anything else is `wait` with a
   reason). Steps hold one lock; decisions apply on the event loop without awaiting in between.
   Reflections are runs of the shared reflection agent, tagged the same way; they never count as
   decisions, and their answer is validated into learnings and views. Plans are runs of the
   shared planner agent, tagged the same way, when a villager wakes and after a conversation of
   at least 4 lines (two revisions a day at most); they never count as decisions, and their
   answer is validated into today's plan. Meeting runs (Hilde's proposals, decision and work
   plan, each villager's vote) are runs of the shared meeting agent, tagged the same way, every
   third day; they never count as decisions, and each answer is validated against the
   catalogue, the proposals and known names. The chronicle is a run of
   the shared chronicler agent, tagged with `village_tick` and no villager, once a night for the
   day its record began; it never counts as a decision. Calendar, light and weather are derived
   from the day, never stored.
6. **Phase 2 seams**: `agent_id`, `config_version` (hash of agent config) and
   `ReActAgent.step()` (one iteration, so a tick runner can drive it). Add no other
   forward-looking abstractions.

## Working rules

- Hand-write agent logic; agent frameworks and MCP SDKs stay out. Ask the owner before adding
  any dependency.
- Tests use `FakeLLM` or `httpx.MockTransport`, never a real model or provider. The real-model
  evals (`make eval-checks`, `make eval-scenarios`) never run in `make check`; they report and
  never gate. They only read the owner's database and write under `backend/data/`.
- Before editing the store or the runner while `make dev` runs, stop it or back up
  `backend/data/agent_lab.db`: the reloading backend runs half-finished edits on the owner's
  village.
- Each milestone is one Spec Kit feature: `speckit-specify` → `clarify` → `plan` → `tasks` →
  `implement`. Map every requirement to a test in `tasks.md`. Commit after each phase and task
  group; push to `origin` only when the owner asks.
- `.env` holds `LLM_API_KEY` and `OPENAI_API_KEY`; keep it out of git. Both are passed to the
  tracer as secrets; never return a key or provider URL from the API.
