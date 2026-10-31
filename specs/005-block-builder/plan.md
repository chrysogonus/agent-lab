# Implementation Plan: M5 — Composable Block Builder

**Branch**: `main` (feature directory `005-block-builder`) | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-block-builder/spec.md`

## Summary

A block agent is an M3 custom agent with `template_id: "blocks"` whose config is a tree of
blocks (model call, tool call, check, router, parallel group, loop). A new `blocks/` package
defines the block types (pydantic discriminated union) and layout rules, derives the graph,
runs the tree with the existing traced helpers, and converts the six templates into blocks.
Because block agents ride on the M3 agent store and M4 model setting, saving, listing, running,
history and the model choice need no new endpoints; two small endpoints hand the builder an
unsaved draft (new, or converted). The builder gets a block outline (add, remove, move, rename)
and per-kind settings forms, with tree edits in a pure, vitest-covered module.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged; no new dependencies

**Storage**: SQLite, no schema change: block agents are rows of the M3 `agents` table with
`template_id = "blocks"`

**Testing**: pytest with `FakeLLM` (each block kind, nesting, references, conversions,
validation, history); golden template file unchanged; vitest for block tree edits

**Target Platform**: local Linux/WSL, loopback only

**Project Type**: web app (backend + frontend)

**Performance Goals**: graph preview of a 30-block, 3-level layout within 1 s of an edit
(SC-006; debounced 300 ms as in M3, derivation is a single tree walk); build and start a
three-block agent in under 3 minutes (SC-001)

**Constraints**: every model, tool and decision call through `steps.chat`/`call_tool`/`decide`;
no user code is executed (checks are built-in); templates and M3 agents unchanged (FR-014)

**Scale/Scope**: single owner; up to 30 blocks, 3 nesting levels per agent

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | A small hand-written tree runner and graph builder in four modules (`model`, `graph`, `run`, `convert`), each readable in one sitting; no graph engine, no dependency |
| II. Observable by default | Pass | The runner only uses the traced helpers; graph derived from the same config, every span on a declared node, `lab.came_from` from actual last nodes; tested with `assert_trace_valid` per block kind |
| III. Secure local defaults | Pass | Checks are fixed functions (no `eval`); references filled by `str.replace`; tool arguments built as a dict and JSON-encoded, then checked by the tool as in M1; layouts validated server-side on save, preview and run start; client graphs never accepted |
| IV. Smallest change | Pass | Block agents reuse the M3 store, API and M4 model setting; no migration; the template editor stays (clarify Q1); one mode instead of a new kind (Q2); outline editing only (Q3) |
| V. Gates + traceability | Pass | `make check` unchanged; `lib/blocks.ts` pure with vitest; FR → test map in `tasks.md` |

Post-design re-check: passes; no Complexity Tracking entries.

## Design

Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md).

### `backend/src/agent_lab/blocks/`

- `model.py`: `ModelBlock`, `ToolBlock`, `CheckBlock`, `RouterBlock` (+ `Route`),
  `ParallelBlock` (+ `Branch`), `LoopBlock`, `CheckRule`; `Block` = annotated union on `kind`;
  `BlocksConfig(model, provider, reasoning, blocks)`; `DEFAULT_CONFIG`; `layout_errors(config)`
  (limits, names, references, per-kind cross-field rules) and `LayoutError`.
- `graph.py`: `build_graph(config)` with `entries`/`exits` per block and the column/row layout.
- `run.py`: `BlockAgent(llm, config, tracer)` with `run(prompt)` → `Outcome` via `steps.invoke`;
  `run_list` per list; `Stop(outcome)` for checks and caps; `check(rule, value, text)`.
- `convert.py`: `to_blocks(template_id, config) -> BlocksConfig` for the six templates.

### Existing code

- `agents/steps.py`: `call_tool(..., node_id=None)` so a tool-call block's span sits on its own
  node.
- `agents/config_fields.py`: `BlockName` (item-name pattern plus the reserved words).
- `agents/registry.py`: `BLOCKS` spec, `KINDS`; `validate_config` looks up `KINDS` and raises
  `LayoutError` for block agents; `AGENTS` stays the six templates (listing, running by id).
- `runs.py`: `resolve` uses `KINDS` for stored agents; a `LayoutError` at run start becomes 422 at
  `body.agent_id`.
- `api.py`: `checked_config` maps `LayoutError` locs under `("body", "config", ...)`;
  `GET /blocks/new`, `GET /agents/{id}/blocks`; `POST /graph` and agent create/update accept
  `"blocks"`.

### UI

- `lib/api.ts`: `newBlockAgent()`, `blocksFrom(agentId)`; block types.
- `lib/blocks.ts` (pure, vitest): `blockAt(config, path)`, `findBlock(config, name)` → path,
  `addBlock(draft, listPath, index, kind)` (default fields, first free name `<kind>-N`),
  `removeBlock`, `moveBlock` (within its list), `renameBlock` (rewrites `{old}` references),
  `outline(config)` → flat entries with depth and list paths for rendering, `blockErrors` (errors
  under a block's path).
- `builder/BlockOutline.tsx`: the nested outline with move/remove buttons and "Add block…"
  selects; `builder/BlockSettings.tsx`: one small form per kind (prompts mono, tool picker,
  argument fields per tool parameter, check rule/value, routes and branches as `ItemList`-like
  lists of names with their own outlines, loop exit choice).
- `AgentBuilder.tsx`: for `template_id === "blocks"` the panel shows agent settings + outline
  and the selected block's settings; node clicks select the block (`findBlock`); the existing
  header actions (Save, Discard, Duplicate, Delete) and the debounced preview stay.
- `AgentPicker`/`page.tsx`: "New block agent" button; "Open as blocks" in the builder header for
  templates and template-based custom agents; both open the fetched draft unsaved
  (`draftFrom`).
- Visual work follows the frontend-design skill (owner's global rule), keeping the M3 identity.

## Project Structure

### Documentation (this feature)

```text
specs/005-block-builder/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
backend/src/agent_lab/
├── blocks/__init__.py, model.py, graph.py, run.py, convert.py   # new
├── agents/steps.py, agents/config_fields.py, agents/registry.py # small changes
├── runs.py, api.py                                              # kinds lookup, 2 endpoints
backend/tests/
├── test_blocks_model.py      # shapes, limits, layout errors, references
├── test_blocks_graph.py      # nodes, edges, layout per kind
├── test_blocks_run.py        # each kind on FakeLLM, nesting, stops, assert_trace_valid
├── test_blocks_convert.py    # six templates: status, answer, call counts, nodes, edges
├── test_blocks_api.py        # endpoints, save/preview/run validation, history
frontend/src/
├── lib/api.ts, lib/blocks.ts (+ test)
└── components/AgentBuilder.tsx, AgentPicker.tsx, builder/BlockOutline.tsx,
    builder/BlockSettings.tsx, app/page.tsx
README.md, AGENTS.md
```

**Structure Decision**: one new backend package for blocks; templates and their workflows stay
untouched.

## Complexity Tracking

None.
