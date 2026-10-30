---
description: "Task list for M3 — Agent Builder"
---

# Tasks: M3 — Agent Builder

**Input**: `specs/003-agent-builder/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-022, FR-023, SC-002–SC-006); every FR maps to a test or
manual check (see Traceability). Tests use `FakeLLM` only.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16). Visual work on builder components
uses the frontend-design skill.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 / US2 / US3 from spec.md

## Conventions used by every task

- Template `Config` classes are the only definition of editable fields, defaults and limits
  (data-model.md). Their defaults are the templates; never duplicate limits elsewhere in the
  backend. The UI reads limits from `422` errors, not from its own copy.
- Message rules for templates must reproduce M2 requests exactly (research.md, "Template
  behavior after the refactor"); the golden test (T001) is the judge.
- Prompts with placeholders are filled with `fill()` (plain `str.replace`), never `str.format`.
- Every rejection is `422 {"detail": [{"loc", "msg", "type"}]}` with `loc` into the request
  body (contracts/http-api.md).
- M2 trace conventions apply unchanged (`specs/002-workflow-patterns/contracts/trace-conventions.md`).

---

## Phase 1: Setup — capture M2 behavior before any change

- [ ] T001 Golden test in new backend/tests/test_templates.py, written and run on the current M2 code before any other task: `run_template(case) -> dict` runs a template through `AGENTS[id]` (`make_config`, `graph`, `create`) with a fixed `FakeLLM` script and returns `{"config_version", "graph" (model_dump), "requests" (per call: messages from `FakeLLM.calls` + `tools`/`response_format`/`reasoning` from `FakeLLM.requests`), "taken_edges" (sorted), "status", "answer"}`; requests of concurrent templates (parallel, orchestrator) are compared as a list sorted by their JSON dump. Cases: react (calculator call, then answer); chain (3-bullet outline, draft, polish); chain gate fail (2-bullet outline); routing math (calculator call, answer), routing weather (get_weather call, answer), routing general, routing invalid label (`{"label": "sports"}` → general); parallel (callable answering per aspect); orchestrator (plan of 2 subtasks); evaluator (reject with feedback, then approve). `test_templates_match_m2` compares against backend/tests/golden/templates.json; with env `UPDATE_GOLDEN=1` it writes the file instead. Generate the file once now and commit it with the test

---

## Phase 2: Foundational — list-based configs, tool catalog, storage (blocks all stories)

**Purpose**: the final config shapes (stored custom agents depend on them), server-side
resolution of custom agents, and the storage changes. Templates must stay golden-equal.

- [ ] T002 [P] New backend/src/agent_lab/tools/catalog.py: `TOOLS: dict[str, Tool] = {t.name: t for t in (CALCULATOR, WEATHER)}`; switch backend/src/agent_lab/agents/registry.py (`REACT_TOOLS`) and backend/src/agent_lab/workflows/routing.py (`HANDLER_TOOLS`) to it
- [ ] T003 [P] New backend/src/agent_lab/agents/config_fields.py: `Prompt` = str stripped, "1–4000 characters after trimming"; `ShortText` = str stripped, "1–300 characters after trimming"; `ItemName` = `^[a-z0-9-]{1,30}$`, "not `start`, `end`, `gate`, `router`, `merge`"; `known_tool(name)` (a key of `TOOLS`, else `ValueError("unknown tool ...")`); `unique(names, what)`; `fill(text, **values)` replacing each `{key}` by `str.replace`; tests in new backend/tests/test_config_fields.py (limits at 0/1/4000/4001 characters, reserved names, pattern, unknown tool, `fill` leaves other braces such as `{"a": 1}` intact)
- [ ] T004 ReAct limits in backend/src/agent_lab/agents/react.py: `system_prompt: Prompt`, `tools: list[str] = ["calculator", "get_weather"]` ("tools ⊆ `TOOLS`, unique, 0–2"), `max_iterations: int` 6 ("iterations 1–10"); registry `create` builds the tool list from `config.tools` via `TOOLS`; change backend/tests/test_react.py::test_ungranted_scope_rejected to build its config with `ReActConfig.model_construct(model="m", tools=["read_file"])` (the scope check stays in `ReActAgent`)
- [ ] T005 [P] Chain in backend/src/agent_lab/workflows/chain.py: `ChainStep{name: ItemName, prompt: Prompt, include_input: bool = False}`; `Config.steps` default outline / draft (`include_input=True`) / polish with the M2 prompts ("1–6 steps", unique names), `input_label: str` "Product" ("label 1–30 characters"), `gate: bool = True`, `gate_min_bullets: int` 3 ("bullets 1–10"); `check_outline(text, min_bullets)`; `build_graph(config)`: start (0, 0), steps and the gate (after the first step, when on) at x = 200 per node, y 0, end at (last x + 200, 110); edges along the path plus gate→end when the gate is followed by a step; flow: first step gets the input, a later step gets the previous output as is, or with `include_input` on `f"{input_label}: {input}\n\n{prev_name.capitalize()}:\n{prev_output}"`; answer = last output; failed gate as in M2
- [ ] T006 [P] Routing in backend/src/agent_lab/workflows/routing.py: `RouteSpec{name: ItemName, description: ShortText, prompt: Prompt, tool: str | None (known_tool)}`; `Config.router_prompt` "Classify the user's question.", `routes` default math (description "arithmetic or a calculation", M2 math prompt, calculator), general ("anything else", M2 general prompt), weather ("the weather or temperature in a city", M2 weather prompt, get_weather) ("2–6 routes", unique names), `fallback: str` "general" ("`fallback` is one of the route names"); `router_system(config)` = `router_prompt` + `f" {name}: {description.rstrip('.')}."` for non-fallback routes in order, then the fallback; `route_model(names)` with `pydantic.create_model` (label = `Literal` of the names; one commented type-ignore allowed for pyright); `build_graph(config)`: one column at x = 450, each route then its tool node `tool:{name}` (only where the tool first appears) 110 px apart from y = 0, start (0, mid), router (200, mid), end (700, mid) with mid = (column nodes − 1) × 55; edges start→router, router→route, route→end, route↔its tool; invalid label → `fallback`
- [ ] T007 [P] Parallel in backend/src/agent_lab/workflows/parallel.py: `aspects: dict[ItemName, ShortText]` ("1–6 aspects"), `review_prompt`/`merge_prompt: Prompt`; fill `{aspect}`/`{focus}` with `fill()` instead of `str.format`
- [ ] T008 [P] Orchestrator in backend/src/agent_lab/workflows/orchestrator.py: `max_subtasks: int` 4 ("subtasks 1–6"); default `orchestrator_prompt` uses `{min_subtasks} to {max_subtasks}` in place of `2 to 4`; filled with `fill(min_subtasks=min(2, n), max_subtasks=n)`; `plan_model(n)` (subtasks: 1..n items, each stripped 1–200 characters) via `create_model`; prompts typed `Prompt`
- [ ] T009 [P] Evaluator in backend/src/agent_lab/workflows/evaluator.py: `max_rounds: int` 3 ("rounds 1–5"); prompts typed `Prompt`
- [ ] T010 Root span name from the run: `steps.invoke` names the root `invoke_agent {ctx.tracer.agent_id}` (drop its `agent_id` parameter, update the five workflows) and `ReActAgent.run` uses `self.tracer.agent_id`, in backend/src/agent_lab/agents/steps.py and backend/src/agent_lab/agents/react.py
- [ ] T011 Make the suite green on the new shapes: registry `graph` lambdas pass the config to chain/routing `build_graph(config)`; update `build_graph()` call sites in backend/tests/test_workflow_chain.py and backend/tests/test_workflow_routing.py; `test_templates_match_m2` passes with the golden file unchanged, except `config_version`, which must stay equal for react, parallel and evaluator and must differ for chain, routing and orchestrator (assert both explicitly in backend/tests/test_templates.py)
- [ ] T012 Registry in backend/src/agent_lab/agents/registry.py: `AgentSpec.config_model: type[BaseModel]`; `validate_config(template_id, raw: dict[str, Any], model: str) -> BaseModel` (rejects a `model` key with loc `config.model`, else `config_model.model_validate({**raw, "model": model})`); `editable(config) -> dict` (dump without `model`)
- [ ] T013 Store in backend/src/agent_lab/store.py: table `agents` (`agent_id` text PK "`custom-` + 12 hex characters", `template_id`, `name` "1–60 characters after trimming", `name_key` UNIQUE "`lower(trim(name))`", `description` "0–200 characters", `sample_prompt` "1–4000 characters", `config` JSON "the template's config without `model`", `created_at`, `updated_at`); `CustomAgent` model; `create_agent`, `update_agent`, `delete_agent`, `get_agent`, `list_agents`; `NameInUse` raised on the UNIQUE violation; `runs` gains `agent_name` and `template_id` (nullable), added with `ALTER TABLE ... ADD COLUMN` when `PRAGMA table_info(runs)` lacks them; `Run` model gains both fields; tests in backend/tests/test_store.py: `test_migrates_m2_database` (runs table in M2 shape → columns added, old run lists with nulls), agent CRUD, `test_name_unique_ignoring_case_and_spaces`
- [ ] T014 Runs in backend/src/agent_lab/runs.py and backend/src/agent_lab/api.py: `resolve(agent_id, store, llm) -> (spec, config, name)` (template → `make_config`; custom → `validate_config` on the stored config); `new_run(prompt, agent_id, llm, store, secrets)` stores `agent_name`, `template_id` (= agent id for templates), `redact(config.model_dump(), secrets)` and the derived graph; `execute_run` gets the resolved spec; `POST /runs` with an unknown id → 422 loc `["body", "agent_id"]`; tests in backend/tests/test_api.py: existing tests pass, `test_template_run_records_name_and_template`

**Checkpoint**: `make check` passes; templates golden-equal; old databases open.

---

## Phase 3: User Story 1 — Customize a template and run it (P1) 🎯 MVP

**Goal**: pick a template, edit prompts and agent settings in the builder, save, run.

**Independent test**: per template, a custom agent with one changed prompt, saved through the
API and run on `FakeLLM`, sends the changed prompt; every span is on its graph; the run carries
the agent's name.

### Backend

- [ ] T015 [US1] API in backend/src/agent_lab/api.py: `GET /agents` → `AgentInfo{id, kind ("template" | "custom"), template_id, name, description, sample_prompt, config (editable), graph}`, templates in registry order then custom agents sorted by name case-insensitively; `GET /tools` → `[ToolInfo{name, description}]` from `TOOLS`
- [ ] T016 [US1] API in backend/src/agent_lab/api.py: `POST /agents {template_id, name, description, sample_prompt, config}` → 201 `AgentInfo`; `PUT /agents/{id} {name, description, sample_prompt, config}` → 200, unknown or template id → 404; `POST /graph {template_id, config}` → server-derived `Graph`; agent fields "name 1–60 characters after trimming", "description 0–200 characters", "sample prompt 1–4000 characters"; unknown template → 422 loc `["body", "template_id"]`; config errors keep pydantic locs under `["body", "config", ...]`; `NameInUse` → 422 loc `["body", "name"]`; CORS `allow_methods` = GET, POST, PUT, DELETE
- [ ] T017 [US1] Tests in new backend/tests/test_agents_api.py: `test_customize_each_template` (parametrized over the six templates: create with one changed prompt, run on `FakeLLM`, the changed prompt is in the model request, `assert_trace_valid`, run `agent_name` = the custom name and `template_id` = the template); `test_update_agent`; `test_template_is_read_only` (PUT on a template id → 404); `test_list_agents_order_and_kinds`; `test_tools`; `test_graph_preview_matches_saved_graph` (preview graph = graph stored with the next run, SC-003); `test_model_key_rejected`; `test_cors_allows_put_delete` in backend/tests/test_api.py

### Frontend

- [ ] T018 [P] [US1] frontend/src/lib/api.ts: `AgentInfo` gains `kind`, `template_id`, `config`; `ToolInfo`; `Run` gains `agent_name`, `template_id` (nullable); `listTools()`, `createAgent()`, `updateAgent()`, `previewGraph()`; a `ValidationError` carrying the 422 `detail` list
- [ ] T019 [P] [US1] Pure builder state in new frontend/src/lib/builder.ts: `Draft{agentId: string | null, templateId, name, description, samplePrompt, config, dirty}`; `draftFromTemplate(template, agents)` (name via `copyName(template.name, names)`), `draftFromAgent(agent)`; `setField(draft, path, value)` (path into the draft, marks dirty); `nodeSettings(templateId, config, nodeId)` → which panel section a node opens (model node → its prompt or list item; gate → bullets; `tool:*` → tool info; start or none → agent settings); `fieldErrors(detail)` → map from dotted path (`config.routes.1.name`, `name`) to message; `copyName(name, names)` ("<name> (copy)", then "(copy 2)", …, case-insensitive); tests in new frontend/src/lib/builder.test.ts
- [ ] T020 [P] [US1] frontend/src/components/GraphView.tsx: optional `selected?: string` (drawn highlighted) and `onNodeClick?: (id: string) => void` (pointer cursor and keyboard focus on nodes when set)
- [ ] T021 [P] [US1] frontend/src/components/AgentPicker.tsx: two labelled groups, "Templates" and "My agents" (the latter hidden when empty)
- [ ] T022 [US1] Builder UI in new frontend/src/components/AgentBuilder.tsx and frontend/src/components/builder/ (`AgentSettings.tsx`: name, description, sample prompt, reasoning, the template's limits; `NodeSettings.tsx`: the prompt of the clicked node, gate bullets, tool name and description): graph left, settings panel right (stacked on narrow screens); read-only for templates with a "Customize" action; editable for custom agents with Save and Discard and a visible unsaved marker; after 300 ms without edits call `previewGraph` and show its graph (keep the last valid one); field errors from `fieldErrors` next to their inputs
- [ ] T023 [US1] Wire in frontend/src/app/page.tsx: the preview area renders `AgentBuilder` for the selected agent; Customize creates a draft (`draftFromTemplate`); Save → `createAgent`/`updateAgent`, refresh agents, select the saved agent; the header Run (frontend/src/components/PromptForm.tsx gets an `onRun(prompt)` prop instead of calling `startRun` itself) saves a dirty draft first and starts no run when the save is rejected; `confirm()` before discarding a dirty draft (switching agent, opening a past run) plus a `beforeunload` guard; frontend/src/components/RunViewer.tsx gets an optional `onEdit` shown when the run's agent is an existing custom agent (FR-024); frontend/src/components/RunList.tsx shows `run.agent_name`, falling back to `agentName(agents, id)` for M1/M2 runs

**Checkpoint**: a custom agent can be made from any template, edited, saved and run from the UI.

---

## Phase 4: User Story 2 — Change the structure a template allows (P2)

**Goal**: add, remove and reorder steps, routes and aspects; pick tools; toggle the gate;
change limits; the graph redraws before saving.

**Independent test**: for each structural change, the graph derived from the config has the
expected nodes and edges and a scripted run takes only declared edges; each template runs at its
minimum and maximum limits (SC-002).

- [ ] T024 [P] [US2] Chain tests in backend/tests/test_workflow_chain.py: `test_single_step_with_gate` (start→s1→gate→end), `test_six_steps_gate_off` (no gate node, six calls, answer = sixth output), `test_include_input_message` (on: `"{input_label}: …\n\n{Prev}:\n…"`; off: previous output as is), `test_gate_min_bullets` (1 and 10), `test_added_step_runs_last` (US2-1)
- [ ] T025 [P] [US2] Routing tests in backend/tests/test_workflow_routing.py: `test_custom_route_poem` (route without tool; classified `poem` → only router→poem and poem→end taken, US2-2), `test_route_schema_lists_custom_routes`, `test_router_prompt_lists_fallback_last`, `test_shared_tool_is_one_node` (two routes with calculator → one `tool:calculator` with edges to both), `test_invalid_label_uses_custom_fallback`, `test_two_and_six_routes`
- [ ] T026 [P] [US2] Parallel tests in backend/tests/test_workflow_parallel.py: `test_one_and_six_aspects` (graph and concurrent review spans match the aspects), `test_replaced_aspect` (remove tone, add length, US2-3), `test_review_prompt_with_braces` (a prompt containing `{"x": 1}` runs)
- [ ] T027 [P] [US2] Orchestrator tests in backend/tests/test_workflow_orchestrator.py: `test_subtask_limit_renders_prompt_and_schema` (limits 1, 4, 6: rendered `1 to 1` / M2 text / `2 to 6`, schema `maxItems` = limit), `test_plan_above_limit_invalid` (limit 2, plan of 3 → run `error`)
- [ ] T028 [P] [US2] Evaluator and ReAct limits: `test_one_and_five_rounds` in backend/tests/test_workflow_evaluator.py; `test_no_tools` (graph without tool nodes, request offers no tools) and `test_calculator_only` (US2-4) in backend/tests/test_react.py
- [ ] T029 [US2] Structural edits in frontend/src/lib/builder.ts: `addItem` (new step `step-N`/route `route-N`/aspect `aspect-N` with the first free N and a placeholder prompt), `removeItem`, `moveItem` (steps only), `renameItem` (renaming the fallback route updates `fallback`), `setFallback`, `toggleTool` (ReAct), `canRemove` (steps ≥ 1, routes ≥ 2, aspects ≥ 1, the fallback route only after another is chosen); tests in frontend/src/lib/builder.test.ts
- [ ] T030 [US2] Structure forms in frontend/src/components/builder/: `ChainSteps.tsx` (list with add, remove, move up/down, include-input switch; gate switch and bullets), `RouteList.tsx` (add, remove, rename, description, tool select from `listTools()`, fallback radio), `AspectList.tsx` (add, remove, rename, focus), `ToolPicker.tsx` (ReAct checkboxes); shown in the agent settings and opened by node clicks via `nodeSettings`; every change goes through the debounced `previewGraph` so the graph redraws before saving (FR-014)

**Checkpoint**: every structural change in US2 is possible in the UI and covered by tests.

---

## Phase 5: User Story 3 — Manage custom agents and keep history intact (P3)

**Goal**: edit, duplicate and delete saved agents; past runs never change; invalid input is
rejected per field.

**Independent test**: run a custom agent, edit and re-run it, delete it; both runs replay with
their own graph and config, show different `config_version`s and keep the agent's name.

- [ ] T031 [US3] `DELETE /agents/{id}` → 204, unknown or template id → 404, in backend/src/agent_lab/api.py; tests in backend/tests/test_agents_api.py: `test_delete_keeps_runs` (runs still list and replay with their stored graph, config and `agent_name`, US3-3), `test_delete_while_running` (the run finishes and stays listed)
- [ ] T032 [P] [US3] History tests in backend/tests/test_agents_api.py: `test_edit_changes_version_not_history` (US3-1, SC-004), `test_duplicate_is_independent` (copy via `POST /agents` with copied fields; editing one leaves the other, US3-2)
- [ ] T033 [P] [US3] Validation tests in backend/tests/test_agents_api.py, each asserting 422, the expected `loc` and no change in `GET /agents` (US3-4, SC-005): empty prompt, empty and 61-character name, name in use (different case and spaces), 0 and 7 chain steps, duplicate step name, reserved name `start`, name with uppercase letters, 1 and 7 routes, unknown tool, fallback not a route, 7 aspects, `max_subtasks` 0 and 7, `max_rounds` 6, `max_iterations` 11, unknown template, `model` key
- [ ] T034 [US3] UI in frontend/src/components/AgentBuilder.tsx and frontend/src/app/page.tsx: Duplicate (`copyName` → `createAgent`, select the copy) and Delete (`confirm()`, then `deleteAgent` added to frontend/src/lib/api.ts; the selection falls back to the agent's template); pure `runAgentLabel(run, agents) -> {name, custom: boolean}` in frontend/src/lib/run-state.ts with tests in frontend/src/lib/run-state.test.ts (stored `agent_name` wins, deleted agents keep their name, M1/M2 runs fall back to the agents list); frontend/src/components/RunList.tsx uses it and shows a "custom" tag (FR-019); `onEdit` hidden once the agent is deleted

**Checkpoint**: history survives every edit and deletion; every listed invalid input is rejected.

---

## Phase 6: Polish

- [ ] T035 [P] Update AGENTS.md: current feature `specs/003-agent-builder/` (M2 and M1 as earlier features); layout adds `tools/catalog.py`, `agents/config_fields.py`, `components/AgentBuilder.tsx`, `components/builder/`; contracts: template `Config` classes define editable fields and limits, custom agents resolve to (template, config), templates are pinned by the golden test
- [ ] T036 [P] Update README.md: builder usage (Customize, Save, Run saves first, Duplicate, Delete) and the API table (`/tools`, `/agents` CRUD, `/graph`)
- [ ] T037 Run quickstart.md manual checks on vLLM (`qwen3.5-9b`) and record results under "Manual check results" in this file; record anything not verified
- [ ] T038 Final `make check`; fill in any missing rows of the Traceability table below

---

## Dependencies

- T001 first, on unchanged M2 code; nothing else starts before the golden file is committed.
- Phase 2: T002 ∥ T003 → T004–T009 (in parallel, different files) → T010 → T011 → T012 → T013 → T014.
- US1: T015 → T016 → T017; T018 ∥ T019 ∥ T020 ∥ T021 → T022 → T023.
- US2: T024–T028 need only Phase 2 (in parallel); T029 needs T019; T030 needs T022 + T029.
- US3: T031 needs T016; T032 ∥ T033 need T016; T034 needs T023 (and T031 for delete).
- Polish after all stories.

## Parallel opportunities

- Phase 2: T005–T009, one workflow module each.
- US1: backend T015–T017 alongside frontend T018–T021.
- US2: the five backend test tasks T024–T028 together, beside T029.
- US3: T032 ∥ T033.

```bash
# Phase 2 example
Task: "Chain in backend/src/agent_lab/workflows/chain.py"
Task: "Routing in backend/src/agent_lab/workflows/routing.py"
Task: "Parallel in backend/src/agent_lab/workflows/parallel.py"
Task: "Orchestrator in backend/src/agent_lab/workflows/orchestrator.py"
Task: "Evaluator in backend/src/agent_lab/workflows/evaluator.py"
```

## Implementation strategy

1. Capture the golden file first (T001), then refactor the configs until it matches again
   (Phase 2). This is the riskiest step and protects SC-006.
2. MVP = US1: customize prompts and settings of any template, save, run; stop and run
   quickstart steps 1–4.
3. US2 adds structure editing on top of the same builder.
4. US3 adds delete and duplicate and hardens validation and history.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_templates.py::test_templates_match_m2; quickstart step 8 |
| FR-002 | test_agents_api.py::test_customize_each_template; builder.test.ts (draftFromTemplate) |
| FR-003 | test_agents_api.py validation tests (T033); test_store.py::test_name_unique_ignoring_case_and_spaces |
| FR-004 | test_store.py agent CRUD; test_agents_api.py::test_update_agent, test_delete_keeps_runs, test_duplicate_is_independent |
| FR-005 | test_agents_api.py::test_list_agents_order_and_kinds; quickstart step 1 |
| FR-006 | test_config_fields.py (Prompt limits); T033 empty prompt |
| FR-007 | test_react.py::test_no_tools, test_calculator_only; T033 max_iterations |
| FR-008 | test_workflow_chain.py (T024); test_templates.py (chain cases) |
| FR-009 | test_workflow_routing.py (T025); T033 routes, tool, fallback |
| FR-010 | test_workflow_parallel.py (T026) |
| FR-011 | test_workflow_orchestrator.py (T027) |
| FR-012 | test_workflow_evaluator.py::test_one_and_five_rounds |
| FR-013 | builder.test.ts (nodeSettings); quickstart steps 1–2 |
| FR-014 | test_agents_api.py::test_graph_preview_matches_saved_graph; quickstart step 2 |
| FR-015 | builder.test.ts (dirty flag); quickstart step 3 |
| FR-016 | builder.test.ts (fieldErrors); T033; quickstart step 4 |
| FR-017 | test_agents_api.py::test_model_key_rejected, test_graph_preview_matches_saved_graph; T033 |
| FR-018 | test_agents_api.py::test_customize_each_template, test_edit_changes_version_not_history, test_delete_keeps_runs |
| FR-019 | run-state.test.ts (runAgentLabel); quickstart step 7 |
| FR-020 | `assert_trace_valid` in every workflow test and test_customize_each_template; T024–T028 |
| FR-021 | test_store.py::test_migrates_m2_database, test_m1_run_still_lists |
| FR-022 | T017, T024–T028, T031–T033 |
| FR-023 | `make check` (T038) |
| FR-024 | quickstart step 4 (back to editing) |

| SC | Test / check |
|---|---|
| SC-001 | quickstart steps 1–3 (real model, timed) |
| SC-002 | T024–T028 (minimum and maximum limits, `assert_trace_valid`) |
| SC-003 | test_agents_api.py::test_graph_preview_matches_saved_graph |
| SC-004 | test_edit_changes_version_not_history, test_delete_keeps_runs |
| SC-005 | T033 |
| SC-006 | test_templates.py::test_templates_match_m2 |
