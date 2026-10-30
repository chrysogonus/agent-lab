# Implementation Plan: M3 — Agent Builder

**Branch**: `main` (feature directory `003-agent-builder`) | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-agent-builder/spec.md`

## Summary

The six M2 agents become templates. Their pydantic `Config` models already hold the prompts; M3
generalises the three whose structure is fixed in code: chain steps become a list, routing
routes become a list, and the orchestrator gets a `max_subtasks` field. Each template's graph
and decision schemas are then derived from its config. A custom agent is a stored row: a
template id, a name, a description, a sample prompt and a config validated by that template's
`Config` model. Runs resolve an agent id to (template, config) and snapshot the name, template,
config and graph as today. The API gains agent CRUD, a tool list and a graph preview for unsaved
configs. The UI turns the preview area into the builder (graph plus settings panel), with view
logic in a pure, vitest-covered module.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged (FastAPI, uvicorn, pydantic, httpx; Next.js, React,
Tailwind, @xyflow/react; dev ruff, pyright strict, pytest, httpx2, eslint, vitest). No new
dependencies.

**Storage**: SQLite. New `agents` table; `runs` gains `agent_name` and `template_id` columns,
added in place on old databases (`ALTER TABLE ... ADD COLUMN` when missing).

**Testing**: pytest with `FakeLLM`; golden graphs of the six templates captured before the
refactor; vitest for builder state and naming logic.

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: graph preview after an edit appears within 1 s locally (debounced
request); create, edit and run in under 1 minute (SC-001).

**Constraints**: templates behave as in M2 (SC-006); the server derives every graph and
`config_version`; no agent frameworks, no graph engine; M1/M2 runs keep replaying.

**Scale/Scope**: single owner; tens of custom agents; lists up to 6 items, rounds up to 5,
iterations up to 10.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Workflows stay plain async modules, now looping over config lists; no engine, no new deps. Route and plan decision models are built per config with `pydantic.create_model` (one small factory per decision, see research) |
| II. Observable by default | Pass | No new model or tool path; every call still goes through `steps.chat`/`call_tool`/`decide`; graphs derived from config so every span's node exists; root span named after the run's agent id |
| III. Secure local defaults | Pass | Configs validated server-side by the template's `Config` model (counts, lengths, names, known tools); client graphs never accepted; run config snapshot redacted like the prompt; CORS adds only `PUT`/`DELETE`; prompts are filled by plain string replacement, never `str.format` or eval |
| IV. Smallest change | Pass | Custom agent = template id + config row; no versioning, no import/export; the graph preview endpoint exists only because FR-014 requires server-derived graphs before saving |
| V. Gates + traceability | Pass | `make check` unchanged; builder logic in `lib/builder.ts` with vitest; FR → test map in `tasks.md` |

Post-design re-check: passes; no Complexity Tracking entries.

## Design

### Template configs (`backend/src/agent_lab/workflows/*.py`, `agents/react.py`)

Each `Config` class is the single source of the editable shape and its limits (pydantic
`Field` constraints and validators); its defaults are the template. Full field list:
[data-model.md](data-model.md).

| Template | Change | Template `config_version` |
|---|---|---|
| ReAct | limits only (`tools` ⊆ known tools, unique; `max_iterations` 1–10); tools resolved from config names instead of the fixed list | unchanged |
| Chain | `outline/draft/polish_prompt` → `steps: list[ChainStep]` (name, prompt, `include_input`), `gate: bool`, `gate_min_bullets` | changes once |
| Routing | four prompt fields → `router_prompt` + `routes: list[RouteSpec]` (name, description, prompt, tool) + `fallback` | changes once |
| Parallel | `aspects` dict keeps its shape; limits and name rules added | unchanged |
| Orchestrator | `max_subtasks: int = 4` added; prompt uses a `{max_subtasks}` placeholder | changes once |
| Evaluator | `max_rounds` limited to 1–5 | unchanged |

Node ids for named items (chain steps, routes, aspects) are their names: lowercase letters,
digits and hyphens, up to 30 characters, unique, not `start`, `end`, `gate`, `router` or
`merge`. The M2 node ids (`outline`, `math`, `clarity`, …) are therefore the template defaults.

### Graphs from config

`build_graph(config)` for every template (parallel and ReAct already work this way). Layout is
computed: items in a column 110 px apart, the decision/merge node centred. For routing, a
route's tool node `tool:{name}` is placed under the first route that uses it; a tool shared by
two routes is one node with edges to both. Golden tests assert the six template graphs equal the
M2 graphs (node ids, kinds, positions, edge set).

### Workflow changes

- **Chain**: loop over `steps`; the first step gets the input; a later step gets the previous
  output under its step name, plus the input when `include_input` is on; the gate (when on) runs
  after the first step with `gate_min_bullets`. Answer = last step's output.
- **Routing**: router system prompt = `router_prompt` + one line per route
  (`- name: description`); decision model `Route{label: <enum of route names>}` built per config;
  invalid label → fallback route. A route with a tool runs the M2 tool handler, without one
  answers in one call.
- **Parallel**: `{aspect}`/`{focus}` filled by `str.replace` (a custom prompt containing other
  braces no longer raises).
- **Orchestrator**: `Plan.subtasks` max length = `max_subtasks` (model built per config);
  `{max_subtasks}` in the orchestrator prompt filled by `str.replace`.
- **All**: the root span is named `invoke_agent {run agent id}` (unchanged for templates).

### Custom agents and runs (`store.py`, `agents/registry.py`, `runs.py`)

- `AgentSpec` gains `config_model` (the template's `Config` class); `create` builds tools from
  config names. `TOOLS: dict[str, Tool]` lists `calculator` and `get_weather`.
- Store: `create_agent`, `update_agent`, `delete_agent`, `get_agent`, `list_agents`; name
  uniqueness via a `name_key` column (`lower(trim(name))`, UNIQUE).
- `resolve(agent_id)`: a template → `(spec, spec.make_config(llm), spec.name)`; a custom agent
  → `(AGENTS[template_id], config_model.model_validate({**stored, "model": llm.model}),
  agent name)`. The stored config never contains `model`; runs always use the server's model.
- `new_run` stores `agent_name`, `template_id`, the redacted config and the derived graph;
  `execute_run` gets the resolved spec. Editing or deleting an agent never touches `runs`.

### API ([contracts/http-api.md](contracts/http-api.md))

- `GET /agents` → templates (M2 order) then custom agents by name; each with `kind`,
  `template_id`, editable `config`, graph.
- `GET /tools` → `[{name, description}]`.
- `POST /agents`, `PUT /agents/{id}`, `DELETE /agents/{id}`; templates are not stored, so they
  answer `404`.
- `POST /graph {template_id, config}` → derived graph or `422` (live preview and validation).
- `POST /runs {prompt, agent_id}` accepts custom ids; `Run` gains `agent_name`, `template_id`.
- Validation errors keep FastAPI's `422 {"detail": [{"loc", "msg", ...}]}` shape everywhere,
  including name conflicts (`loc: ["body", "name"]`), so the UI maps every error to a field.

### UI

- `lib/builder.ts` (pure): draft state (agent fields + config + dirty flag), edits (set field,
  add/remove/move list item, toggle, set limit), `nodeSettings(templateId, config, nodeId)` →
  which panel section a click opens, `copyName(name, existing)`, `fieldErrors(detail)` → map
  from field path to message, `canRemove` rules (routing ≥ 2 routes, fallback).
- `GraphView`: optional `selected` node and `onNodeClick`.
- `AgentPicker`: two groups, Templates and My agents.
- `AgentBuilder` (new) in the preview area: graph on the left, settings panel on the right
  (`components/builder/*`: agent settings plus one small form per template). Templates open
  read-only with a "Customize" action; custom agents open editable with Save, Discard,
  Duplicate, Delete. Unsaved edits: dirty marker, `confirm()` before discarding (switching
  agent, opening a run) and a `beforeunload` guard.
- Graph preview: each edit posts `POST /graph` after 300 ms of quiet; the last valid graph
  stays visible, field errors show next to their inputs.
- Run (header form): with unsaved changes, save first (`POST`/`PUT`), then `POST /runs`; a
  rejected save shows its errors and starts no run.
- `RunViewer`: "Back to editing" when the run's agent is an existing custom agent. `RunList`:
  `agent_name` (falls back to the agents list for M1/M2 runs) and a "custom" tag.
- Visual work on the builder follows the frontend-design skill (owner's global rule).

## Project Structure

### Documentation (this feature)

```text
specs/003-agent-builder/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
backend/src/agent_lab/
├── workflows/chain.py, routing.py, orchestrator.py   # list-based configs, graphs from config
├── workflows/parallel.py, evaluator.py               # limits, safe placeholder fill
├── agents/react.py                                   # limits; tools from config
├── agents/registry.py                                # config_model, TOOLS, resolve
├── agents/steps.py                                   # root span name from the run's agent id
├── store.py                                          # agents table, run columns, migration
├── runs.py, api.py                                   # resolve custom agents, new endpoints
backend/tests/
├── golden/template_graphs.json                       # M2 graphs, captured before the refactor
├── test_templates.py, test_agents_api.py             # new
├── test_workflow_*.py, test_store.py, test_api.py    # extended
frontend/src/
├── lib/api.ts, lib/builder.ts (+ test), lib/run-state.ts (+ test)
├── components/AgentBuilder.tsx, components/builder/*.tsx
└── components/AgentPicker.tsx, GraphView.tsx, RunViewer.tsx, RunList.tsx, PromptForm.tsx, app/page.tsx
```

**Structure Decision**: extend the M2 layout; builder components get their own folder.

## Complexity Tracking

None.
