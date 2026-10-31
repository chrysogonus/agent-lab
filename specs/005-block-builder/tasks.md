---
description: "Task list for M5 — Composable Block Builder"
---

# Tasks: M5 — Composable Block Builder

**Input**: `specs/005-block-builder/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-018, SC-002–SC-005); every FR maps to a test or manual check
(see Traceability). Tests use `FakeLLM` only.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16). Visual work on the block outline and
block settings uses the frontend-design skill, keeping the M3/M4 identity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 / US2 / US3 from spec.md

## Conventions used by every task

- Templates, their workflows and backend/tests/golden/templates.json are not changed (FR-014).
- The block runner reaches the model and the tools only through `steps.chat`, `steps.call_tool`
  and `steps.decide`; the first span of each node visit records `lab.came_from` with the node
  ids that actually ran before it (research.md §5).
- Placeholders are filled with `config_fields.fill`; never `str.format` or eval.
- Every rejection is `422 {"detail": [{"loc", "msg", "type"}]}` with `loc` into the request body;
  block errors start `["body", "config", "blocks", …]` (contracts/http-api.md).
- Block test helpers (a `blocks_config(*blocks)` builder and per-kind constructors with valid
  defaults) live in backend/tests/helpers.py and are reused by every block test file.

---

## Phase 1: Setup

- [ ] T001 Create the package backend/src/agent_lab/blocks/ (`__init__.py` with a one-line docstring); in backend/src/agent_lab/agents/config_fields.py add `BLOCK_RESERVED = frozenset({"start", "end", "input", "previous", "feedback", "item"})` and `BlockName` = the item-name pattern `^[a-z0-9-]{1,30}$` "not `start`, `end`, `input`, `previous`, `feedback`, `item`"; in backend/src/agent_lab/agents/steps.py give `call_tool` an optional `node_id: str | None = None` that, when set, replaces `tool:<name>` as the span's node (default behavior unchanged); tests in backend/tests/test_config_fields.py (`BlockName` reserved words) and backend/tests/test_steps.py (`call_tool` with `node_id`)

---

## Phase 2: Foundational — block types, layout rules, wiring (blocks all stories)

**Purpose**: the full stored shape of block agents and their validation, reachable through the
existing agent API, so every story builds on saved, validated configs.

- [ ] T002 Block types in new backend/src/agent_lab/blocks/model.py (data-model.md): `CheckRule{rule: "min_bullets" | "max_words" | "contains" | "valid_json", value: int | str | None}`; `ModelBlock{kind: "model", name: BlockName, system: Prompt, message: Prompt = "{previous}", tools: list[str] = [] ("known tool names, unique, 0–2"), max_iterations: int = 4 ("1–10")}`; `ToolBlock{kind: "tool", name, tool: known tool, arguments: dict[str, Prompt]}`; `CheckBlock{kind: "check", name, rule, value}`; `Route{name: BlockName, description: ShortText, blocks: list[Block] (1 or more)}`; `RouterBlock{kind: "router", name, prompt: Prompt, routes: 2–6, fallback: str}`; `Branch{name: BlockName, blocks: 1 or more}`; `ParallelBlock{kind: "parallel", name, mode: "branches" | "per_item", branches: list[Branch] | None (1–6), planner: Prompt | None, max_items: int | None ("1–6"), body: list[Block] | None (1 or more)}`; `LoopBlock{kind: "loop", name, body: 1 or more, exit: "judge" | "check", judge: Prompt | None, check: CheckRule | None, max_rounds: int = 3 ("1–5")}`; `Block` = `Annotated[ModelBlock | … | LoopBlock, Field(discriminator="kind")]` with `model_rebuild()`; `BlocksConfig{model: str, provider: Provider = LOCAL, reasoning: bool = False, blocks: list[Block] (1 or more)}`; `DEFAULT_BLOCKS` = one `ModelBlock(name="answer", system="Answer the user's question briefly.")`; tests in new backend/tests/test_blocks_model.py: each kind's field limits at their bounds (pydantic locs point at the field, e.g. `blocks.0.routes.1.blocks.0.system`)
- [ ] T003 Layout rules in backend/src/agent_lab/blocks/model.py: `class LayoutError(Exception)` holding `errors: list[tuple[tuple[str | int, ...], str]]`; `layout_errors(config) -> list[(loc, msg)]` walking the tree once: "at most 30 blocks" (routes and branches are not blocks; loc `("blocks",)`), "nesting at most 3 levels" (a container at level 3; loc of that block's `kind`), unique block names (loc of the second `name`), route names unique within a router and branch names within a group, `fallback` one of the route names, mode fields present for their mode and absent for the other, `exit` fields (`judge` for judge, `check` for check), `CheckRule.value` per rule ("integer 1–1000 for `min_bullets`/`max_words`, text 1–300 characters for `contains`, absent for `valid_json`"), tool `arguments` keys exactly the tool's parameter names, and references: every `\{[a-z0-9-]{1,30}\}` token in `system`, `message`, `prompt`, `planner`, `judge` and argument templates must be `input`, `previous`, a visible earlier block (research.md §4: earlier siblings, and blocks before each enclosing container), `feedback` inside a loop body, or `item` inside a per-item body (loc of the field, message "unknown reference {x}" or "{x} is not available here"); tests in backend/tests/test_blocks_model.py for each rule with its exact loc, including a reference to a block inside a route from after the router (rejected) and to the router itself (allowed)
- [ ] T004 Registry and validation path: in backend/src/agent_lab/agents/registry.py add `BLOCKS = AgentSpec(id="blocks", name="Block agent", description=…, sample_prompt="What is 17 times 23?", config_model=BlocksConfig, graph=…, create=…)` (graph and create filled in US1; until then `graph` returns start → end and `create` raises `NotImplementedError`) and `KINDS = {**AGENTS, "blocks": BLOCKS}`; `validate_config` looks up `KINDS` and, for `"blocks"`, raises `LayoutError` when `layout_errors` is not empty; in backend/src/agent_lab/api.py `checked_config` accepts `template_id in KINDS` and turns `LayoutError` into `RequestValidationError` with locs `("body", "config", *loc)`; `custom_info` and `POST /graph` use `KINDS`; in backend/src/agent_lab/runs.py `resolve` uses `KINDS` for stored agents (validation may raise `LayoutError`), and `POST /runs` catches `LayoutError` → 422 at `["body", "agent_id"]` with the first error's message; `"blocks"` stays out of `AGENTS` (not listed as a template, not runnable by id); `GET /blocks/new` → unsaved `AgentInfo` (`id: ""`, `kind: "custom"`, `template_id: "blocks"`, name "New block agent", description "", the BLOCKS sample prompt, `config = editable(BlocksConfig(default model, blocks=DEFAULT_BLOCKS))`, `model: null`, graph); tests in new backend/tests/test_blocks_api.py: `test_new_block_agent_draft`, `test_save_block_agent` (POST with `template_id: "blocks"` → 201, listed with `kind: "custom"`, `template_id: "blocks"`), `test_layout_error_locs` (an unknown reference → 422 at `["body", "config", "blocks", 1, "message"]`, nothing stored), `test_blocks_is_not_a_template` (absent from templates in `GET /agents`; `POST /runs` with `agent_id: "blocks"` → 422)

**Checkpoint**: `make check` passes; block agents can be saved and are validated; templates and
M3 agents unchanged.

---

## Phase 3: User Story 1 — Build a sequence of blocks and run it (P1) 🎯 MVP

**Goal**: model-call and tool-call blocks in sequence with references, built in the UI and run.

**Independent test**: model call → calculator tool call with argument `{previous}` → model call
using `{input}` and the tool's output, run on `FakeLLM`: expected prompts, expected tool
argument, `completed` with the last output, every span on a node of the derived graph.

### Backend

- [ ] T005 [US1] Graph for sequences in new backend/src/agent_lab/blocks/graph.py: `build_graph(config)` with `entries(block)`/`exits(block)`; nodes: model `llm` labelled `"<name> (LLM)"`, tool block `tool` labelled `"<name> (<tool>)"`; shared `tool:<name>` nodes for model calls with tools (edges both ways) and a terminal edge model-with-tools → `end`; consecutive blocks `exits(a) × entries(b)`, `start` → first, last → `end`; layout: columns 200 px apart, `start` at x 0, `end` one column after the last, tool nodes one row (110 px) below their model; hook into `BLOCKS.graph`; tests in new backend/tests/test_blocks_graph.py (one block; model → tool → model; a model with two tools; node ids unique, every edge's ends exist)
- [ ] T006 [US1] Runner for sequences in new backend/src/agent_lab/blocks/run.py: `BlockAgent(llm, config, tracer)` with `run(prompt) -> Outcome` via `steps.invoke`; `run_list(blocks, input, scope, came) -> (output, last_nodes)` where `scope` maps `input`, `previous` and earlier block names to their outputs; model block: `steps.chat` with `steps.messages(fill(system, **scope), fill(message, **scope))`, without tools one call, with tools the ReAct loop (each tool call via `steps.call_tool` on `tool:<name>` with `caller=<block>`, next chat `came_from` the tool nodes) up to `max_iterations` model calls, then `Stop(Outcome("max_iterations", None, [block], "max iterations (<n>) reached in <block>"))`; tool block: arguments filled per parameter, JSON-encoded with `json.dumps`, `steps.call_tool(..., node_id=<block>)`, output = the result text (tool errors become the output, M1 rule); `Stop` caught in the flow → its outcome; hook into `BLOCKS.create` with `reasoning=config.reasoning`; tests in new backend/tests/test_blocks_run.py: the independent test above (requests and tool argument asserted), a tool error as output, the ReAct loop at `max_iterations` 1 and 10 (cap stops `max_iterations`, end span `came_from` the block), a cap in a non-final block, `assert_trace_valid` in every test
- [ ] T007 [US1] API round trip in backend/tests/test_blocks_api.py: `test_build_and_run_three_blocks` (save via API, run, run `template_id: "blocks"`, `agent_name`, stored config has the blocks, graph equals `POST /graph` for the same config), `test_block_agent_on_pinned_model` (M4 `model` pinned → every model span on that model)

### Frontend

- [ ] T008 [P] [US1] frontend/src/lib/api.ts: block types (`Block` union mirroring data-model.md, `BlocksConfig`), `newBlockAgent()` (`GET /blocks/new`), `blocksFrom(agentId)` (`GET /agents/{id}/blocks`)
- [ ] T009 [P] [US1] Pure block tree edits in new frontend/src/lib/blocks.ts with tests in new frontend/src/lib/blocks.test.ts: `blockAt(config, path)`, `findBlock(config, name) -> Path | null`, `defaultBlock(kind, name)` (valid defaults per kind, e.g. a router with two routes each holding one model block), `freeName(config, base)` (`<base>-N`, first unused), `addBlock(draft, listPath, index, kind)`, `removeBlock(draft, path)`, `moveBlock(draft, path, delta)` (within its list), `renameBlock(draft, path, name)` (rewrites `{old}` to `{new}` in every prompt, message, planner, judge and argument template), `outline(config)` → flat entries `{path, name, kind, depth, listPath}` plus list headers for routes/branches/body, `blockErrors(errors, path)`; edits mark the draft dirty and never mutate their input
- [ ] T010 [US1] Outline and settings in new frontend/src/components/builder/BlockOutline.tsx (nested entries with kind and name, move up/down and remove buttons with accessible labels, a native "Add block…" select after each entry and at the end of each list) and new frontend/src/components/builder/BlockSettings.tsx (model: name via `renameBlock`, system and message prompts (mono), tool checkboxes, max iterations; tool: tool select, one argument field per tool parameter from `listTools()`); errors from `blockErrors` next to their fields; in frontend/src/lib/builder.ts add `Section` kind `{kind: "block", path}` and make `nodeSettings("blocks", config, nodeId)` return it via `findBlock`
- [ ] T011 [US1] Wire in frontend/src/components/AgentBuilder.tsx and frontend/src/app/page.tsx: for `template_id === "blocks"` the panel shows agent settings (name, description, sample prompt, model, reasoning) plus `BlockOutline`, and the selected block's `BlockSettings`; node clicks select blocks; a "New block agent" button (next to the agent picker in frontend/src/components/AgentPicker.tsx or the page header) loads `newBlockAgent()` as an unsaved draft via `draftFrom`; Save, Discard, Duplicate, Delete, the debounced preview and run-saves-first work unchanged

**Checkpoint**: a three-block agent can be built, saved and run from the UI.

---

## Phase 4: User Story 2 — Nest routers, parallel groups, loops and checks (P2)

**Goal**: control-flow blocks with nesting, each traced on declared nodes.

**Independent test**: for each control block, a scripted run takes exactly the expected branch,
branches or rounds; every taken edge is declared; caps and failing checks stop with an end span
from the stopping node.

- [ ] T012 [US2] Graph for control blocks in backend/src/agent_lab/blocks/graph.py: check `code` node `"<name> (check)"` with a terminal edge → `end`; router `llm` node → each route's entries, each route's last exits → next; parallel branches: no node, previous exits → each branch's entries, each branch's exits → next; per-item: planner `llm` node → body entries, body exits → next, terminal edge planner → `end`; loop: body inline, exit node (`llm` judge or `code` check) named after the loop, body exits → exit node, exit node → body entries (repeat), → next, and terminal edge → `end`; layout: routes and branches stack in rows, a container is as wide as its widest list, single nodes centred in their container's height; tests in backend/tests/test_blocks_graph.py per kind, a router inside a loop inside a parallel branch (3 levels), and the 30-block, 3-level fixture building in under 1 s (SC-006, measured with `time.perf_counter`)
- [ ] T013 [US2] Runner for control blocks in backend/src/agent_lab/blocks/run.py: check (pure `check(rule, value, text) -> str | None` reason; `min_bullets` via `chain.check_outline`; `max_words` counts whitespace-separated words; `contains` case-sensitive substring; `valid_json` via `json.loads`) as a `STEP` span on its node, failing → `Stop(Outcome("error", None, [check], "check <name> failed: <reason>"))`, passing passes its input on; router: `steps.decide(..., kind=SpanKind.ROUTE)` with `routing.route_model` over the route names (fallback last) and the router prompt plus `" <name>: <description>."` per route (fallback last), unusable decision → fallback, then the route's list with `came=[router]`; parallel branches: `asyncio.gather(..., return_exceptions=True)` over branch lists, then raise the first exception, output `"<branch>:\n<output>"` joined by blank lines, last nodes = all branch exits; per-item: `steps.decide` with `orchestrator.plan_model(max_items)` on the planner node (unusable → `Stop(Outcome("error", None, [group], …))`), body per item concurrently with `item` in scope, output `"<item>:\n<output>"`; loop: rounds up to `max_rounds`, body with `feedback` in scope (empty in round 1, then `"Previous answer:\n<last>\n\nFeedback:\n<feedback>"`), exit by check (failed check text is the feedback) or `steps.decide` with `evaluator.Verdict` (unusable verdict = rejection, its error is the feedback), cap → `Stop(Outcome("max_iterations", <last body output>, [loop], …))`; container outputs as data-model.md "Outputs"
- [ ] T014 [P] [US2] Tests in backend/tests/test_blocks_run.py: check pass and fail for each rule (fail ends `error`, no later block runs, end span `came_from` the check); router picks a route, invalid label → fallback, a route of two blocks; parallel branches start together (delayed `FakeLLM`, overlapping spans) and a failing branch ends `error` after the others finish; per-item at `max_items` 1 and 6, a plan above the max → `error` from the planner; loop approved in round 1, approved in round 3 with `{feedback}` reaching the body, unusable verdict treated as rejection, cap at 1 and 5 → `max_iterations`, check exit; a cap or failing check inside a nested container; references to container outputs (`{router-name}`, `{group-name}`); `assert_trace_valid` everywhere (SC-003)
- [ ] T015 [US2] Settings forms in frontend/src/components/builder/BlockSettings.tsx: check (rule select, value field per rule); router (prompt, routes as a list of name + description + fallback radio, add/remove route); parallel (mode switch; branches mode: branch names, add/remove branch; per-item mode: planner prompt, max items); loop (exit choice judge/check, judge prompt or check rule and value, max rounds); and frontend/src/components/builder/BlockOutline.tsx shows each route, branch and body as a nested list with its own "Add block…"; list operations for routes and branches in frontend/src/lib/blocks.ts (`addRoute`, `removeRoute`, `addBranch`, `removeBranch`, `setMode` keeping one block in the new list) with tests in frontend/src/lib/blocks.test.ts

**Checkpoint**: every block kind can be added, nested, edited and run, and traces stay valid.

---

## Phase 5: User Story 3 — Start from a template, keep history and limits safe (P3)

**Goal**: "Open as blocks" for every template and template-based agent; validation and history
hold.

**Independent test**: each template converted and run on its golden script (and on a malformed
decision script) matches the template's status, answer, call counts and taken edges; every
invalid layout in the list is rejected at its block and field; past runs replay after edit and
delete.

- [ ] T016 [US3] Conversions in new backend/src/agent_lab/blocks/convert.py: `to_blocks(template_id, config) -> BlocksConfig` per research.md §7 (ReAct → model `llm`; chain → models per step plus check `gate` after the first step when the gate is on, `include_input` messages; routing → router `router` with one model per route, tools with `max_iterations` 2; parallel → group `reviews` (branches per aspect, filled review prompts) then model `merge` with message `"Text:\n{input}\n\n{reviews}"`; orchestrator → per-item group `orchestrator` (filled orchestrator prompt, `max_items` = `max_subtasks`, body model `worker` with message `"Request: {input}\n\nSubtask: {item}"`) then model `synthesizer` with message `"Request: {input}\n\n{orchestrator}"`; evaluator → loop `evaluator` (judge = evaluator prompt) with body model `generator`, message `"{input}\n\n{feedback}"`); model, provider and reasoning copied; colliding item names renamed to the first free `<name>-<n>` and references updated
- [ ] T017 [US3] Conversion tests in new backend/tests/test_blocks_convert.py: for each case in `test_templates.CASES`, the converted agent run on the same script reaches the same status and answer with the same number of model and tool calls and the same taken edges; its graph has the template's `llm`/`tool`/`code` node ids and a subset of its edges; malformed decisions: routing invalid label (fallback), orchestrator plan above the limit (`error` from `orchestrator`), evaluator unreadable verdict then approval (rejection, then `completed`); collisions: a chain step named `input` and an aspect named `reviews` convert with renamed blocks and valid layouts; an M3 custom agent's edited prompt appears in its converted blocks (SC-002)
- [ ] T018 [US3] `GET /agents/{agent_id}/blocks` in backend/src/agent_lab/api.py → unsaved `AgentInfo` draft (`id: ""`, `template_id: "blocks"`, the source's name, description, sample prompt and model, converted config, graph); 404 unknown, 409 for a block agent; tests in backend/tests/test_blocks_api.py (`test_open_template_as_blocks`, `test_open_custom_agent_as_blocks`, `test_open_block_agent_conflict`)
- [ ] T019 [P] [US3] Validation list in new backend/tests/test_blocks_validation.py, each asserting 422, the expected loc and no change in `GET /agents` on create and update (SC-004): empty system prompt, empty message, 31 blocks, a container at level 3, duplicate block name, reserved name `input`, unknown tool, tool arguments with a missing and an extra key, check `min_bullets` with text value, router with 1 and 7 routes, fallback not a route, empty route, parallel branches mode with 7 branches and with planner fields, per-item with `max_items` 0, loop with judge exit and no judge, `max_rounds` 6, reference to a later block, reference to a block inside a route from after the router, `{feedback}` outside a loop, `{item}` outside a per-item body, `model`/`provider` keys inside config
- [ ] T020 [P] [US3] History in backend/tests/test_blocks_api.py: `test_edit_keeps_past_runs` (run, rename a block and change a prompt, run again: two `config_version`s, the first run replays its own blocks and graph) and `test_delete_keeps_past_runs` (SC-005); `test_templates_and_m3_agents_unchanged` (GET /agents output for templates and an M3 agent equals the M4 shape; golden test untouched)
- [ ] T021 [US3] "Open as blocks" in frontend/src/components/AgentBuilder.tsx (header action for templates and template-based custom agents) and frontend/src/app/page.tsx (loads `blocksFrom(id)`, opens it unsaved via `draftFrom`, unsaved-changes guard as for Customize); server validation errors shown at their block and field via `blockErrors`, including the outline entry of a block with errors

**Checkpoint**: all six templates open as blocks; validation and history verified.

---

## Phase 6: Polish

- [ ] T022 [P] Docs: README.md (block agents: New block agent, Open as blocks, block kinds, references `{input}` `{previous}` `{name}` `{feedback}` `{item}`, limits; API rows for `GET /blocks/new` and `GET /agents/{id}/blocks`); AGENTS.md (layout: `blocks/` package; rule: the block runner uses only the traced step helpers)
- [ ] T023 `make check` passes; FR → test map below complete
- [ ] T024 Manual checks from quickstart.md steps 1–8 on vLLM (and one block agent on OpenAI if the key is configured); record results in a "Manual check results" section of this file

---

## Dependencies

- Phase 1 → Phase 2 → stories. T002 → T003 → T004.
- US1 needs Phase 2. US2 needs T005/T006 (graph and runner modules). US3 needs US1 and US2
  (conversions use every block kind).
- Frontend: T008 ∥ T009, then T010, T011; T015 after T010; T021 after T011.

## Parallel opportunities

- US1: backend T005–T007 alongside frontend T008–T009.
- US2: T014 (tests) alongside T015 (UI) once T012–T013 are done.
- US3: T019 ∥ T020 after T018.

```bash
# US1 example
Task: "Graph for sequences in backend/src/agent_lab/blocks/graph.py"
Task: "frontend/src/lib/api.ts: block types"
Task: "Pure block tree edits in frontend/src/lib/blocks.ts"
```

## Implementation strategy

1. Phase 2 first: the stored shape and its validation are the contract for everything else.
2. MVP = US1: model and tool blocks in sequence, built and run from the UI; stop and run
   quickstart steps 1–2.
3. US2 adds control flow (most of the runner and graph logic).
4. US3 converts the templates, which exercises every block kind against known-good behavior.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_blocks_api.py::test_save_block_agent, test_edit_keeps_past_runs, test_delete_keeps_past_runs; quickstart step 1 |
| FR-002 | test_blocks_run.py (sequence test: each block gets the previous output) |
| FR-003 | test_blocks_model.py (unique names, `BlockName`); test_blocks_graph.py (node ids) |
| FR-004 | test_blocks_run.py (model without tools, ReAct loop at 1 and 10) |
| FR-005 | test_blocks_run.py (tool argument, tool error as output) |
| FR-006 | test_blocks_run.py (check rules pass/fail) |
| FR-007 | test_blocks_run.py (router, fallback) |
| FR-008 | test_blocks_run.py (branches, per-item at 1 and 6, failing branch) |
| FR-009 | test_blocks_run.py (loop rounds, feedback, cap, check exit) |
| FR-010 | test_blocks_model.py (reference rules); test_blocks_run.py (filled prompts); blocks.test.ts (rename rewrites references) |
| FR-011 | test_blocks_graph.py; `assert_trace_valid` in test_blocks_run.py |
| FR-012 | test_blocks_api.py::test_edit_keeps_past_runs, test_delete_keeps_past_runs |
| FR-013 | test_blocks_convert.py; test_blocks_api.py::test_open_template_as_blocks |
| FR-014 | test_templates.py (golden unchanged); test_blocks_api.py::test_templates_and_m3_agents_unchanged |
| FR-015 | blocks.test.ts; quickstart steps 1–2, 4 |
| FR-016 | blocks.test.ts (blockErrors); quickstart step 2 |
| FR-017 | test_blocks_model.py (layout rules); test_blocks_validation.py |
| FR-018 | T006, T007, T014, T017, T019, T020 |
| FR-019 | `make check` (T023) |

| SC | Test / check |
|---|---|
| SC-001 | quickstart step 1 (timed) |
| SC-002 | test_blocks_convert.py |
| SC-003 | test_blocks_run.py (`assert_trace_valid` at limits) |
| SC-004 | test_blocks_validation.py |
| SC-005 | test_blocks_api.py history tests; quickstart step 8 |
| SC-006 | test_blocks_graph.py (30-block fixture under 1 s); quickstart step 7 |
