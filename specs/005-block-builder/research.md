# Research: M5 — Composable Block Builder

No new dependencies and no external services; every decision below is about shapes and rules
inside the existing stack. Code references are to the M4 tree (commit `1cfcecf`).

## 1. Where block agents live

- **Decision**: a block agent is an M3 custom agent whose `template_id` is `"blocks"`. Its
  stored `config` is `{reasoning, blocks, model?, provider?}`. A seventh `AgentSpec` (`BLOCKS`)
  provides `config_model`, `graph` and `create`; the registry keeps `AGENTS` (the six templates,
  listed and runnable by id) and adds `KINDS = {**AGENTS, "blocks": BLOCKS}` for looking up a
  custom agent's kind.
- **Rationale**: create, update, delete, list, validation on save and run, the graph preview,
  run snapshots, `config_version`, the M4 model setting and redaction all work through the
  existing paths unchanged. No table or column is added.
- **Alternatives**: a separate `block_agents` table and endpoints (duplicates M3); converting
  templates into blocks (rejected in clarify, Q1).

## 2. Block shapes

- **Decision**: one pydantic discriminated union `Block` on `kind`:
  `model | tool | check | router | parallel | loop` (field list in
  [data-model.md](data-model.md)). Containers hold `list[Block]` (recursive models). The
  parallel group has `mode: "branches" | "per_item"` (clarify Q2: a mode, not a kind).
- **Rationale**: field limits (prompt length, list sizes, ranges) are checked by pydantic with
  exact locs, as M3 configs are, so errors already land at the block and field.
- **Alternatives**: a flat node list with parent ids (needs a second validator for tree shape,
  harder to edit).

## 3. Cross-block rules and their error locations

- **Decision**: after pydantic, `layout_errors(config) -> list[(loc, msg)]` walks the tree once
  and checks: total blocks ≤ 30, nesting ≤ 3 levels, unique block names, reserved names, the
  router fallback, tool argument keys, check values per rule, and every reference. Each error
  carries the loc of the offending field, e.g. `("blocks", 2, "routes", 0, "blocks", 1,
  "message")`. `validate_config` raises `LayoutError(errors)` for block agents; the API turns
  both pydantic errors and `LayoutError` into the usual 422 under `("body", "config", ...)`;
  `resolve` (run start) runs the same check. Pydantic puts the union tag into locs
  (`("blocks", 0, "model", "system")`); the API removes a kind name that follows a list index,
  so every loc is a path into the draft. A stored agent that no longer validates (pydantic or
  layout) is rejected at run start with 422, not a server error.
- **Rationale**: a pydantic `model_validator` can only report at the model's own loc; the walk
  gives every error the exact path the builder maps to a field (FR-016, FR-017).
- **Alternatives**: one model validator with the path in the message text (the UI could not
  place it).

## 4. References

- **Decision**: placeholders `{input}` (the user's prompt), `{previous}` (the previous block's
  output; for the first block of a list, the list's input), `{<block name>}` (an earlier
  block's output), `{feedback}` (inside a loop body) and `{item}` (inside a per-item body).
  Filled with `config_fields.fill` (plain `str.replace`). Validation finds tokens matching
  `\{[a-z0-9-]{1,30}\}`; other braces (JSON examples) are text. `input`, `previous`, `feedback`
  and `item` are reserved block names, as are `start` and `end` (graph nodes).
- **Visibility** (what a block may refer to): earlier siblings in its own list, and the blocks
  before each enclosing container in that container's list. Blocks inside a route, branch or
  body are not visible after their container; the container's own name gives its output.
- **Container outputs**: router → the chosen route's last output; parallel group (branches) →
  `"<branch>:\n<output>"` sections joined by blank lines; per-item → `"<item>:\n<output>"`
  sections; loop → the last round's body output; check → its input unchanged.
- **`{feedback}`**: empty in the first round, then `"Previous answer:\n<last body output>\n\n
  Feedback:\n<judge feedback or the failed check>"`, so a body prompt needs one reference to
  revise (the M2 evaluator's behavior).
- **Default message template** of a model call: `{previous}` (the spec left it open; this
  matches M3 chain steps, where a later step receives the previous output).
- **Rename**: the builder rewrites `{old}` to `{new}` in every prompt and argument template.

## 5. Running blocks

- **Decision**: `blocks/run.py` executes the tree with the existing traced helpers only:
  `steps.chat`, `steps.call_tool` (gains an optional `node_id`, for tool-call blocks),
  `steps.decide`, `steps.invoke`. `run_list(blocks, input, scope, came) -> (output, last_nodes)`
  carries the actual last node ids so every first span of a node visit records `lab.came_from`
  (M2 convention).
  - Model call with tools: the ReAct loop (chat with tools → each tool call → chat), at most
    `max_iterations` model calls; hitting the cap stops the run `max_iterations`.
  - Router: `decide` with a `Route` schema of the route names (`routing.route_model`), router
    prompt plus route descriptions, fallback last (the `routing.router_system` rule
    generalised); an invalid label runs the fallback.
  - Parallel branches / per-item bodies: `asyncio.gather(..., return_exceptions=True)`, then the
    first exception is raised, so every branch finishes and stays in the trace before the run
    ends `error` (spec edge case). Per-item: `decide` with `orchestrator.plan_model(max_items)`;
    an unusable plan stops the run `error` from the planner node (as `OrchestratorWorkflow`).
  - Loop: body, then the exit: a check, or `decide` with the evaluator's `Verdict`; an unusable
    verdict counts as a rejection whose error becomes the feedback (as `EvaluatorWorkflow`); at
    the cap the run stops `max_iterations` with the last body output as the answer.
  - Check: a pure function per rule (`min_bullets` reuses `chain.check_outline`); failing stops
    the run `error` naming the check.
- **Stops**: a failing check, an unusable plan and an iteration or round cap raise
  `Stop(outcome)` from any depth; the flow returns that outcome, so the end span records
  `came_from` the stopping node (every such node has an edge to `end`, §6). Model and tool
  transport errors propagate as in M2 (run `error`, no end span, so no edge needed). Decision
  handling matches the templates: router → fallback, judge → rejection, planner → stop.
- **Rationale**: no new model or tool path (constitution II); every behavior already exists in
  one of the six workflows.

## 6. Graph and layout

- **Decision**: `blocks/graph.py` derives the graph in one recursive pass.
  - Nodes: model call `llm`, tool call `tool`, check `code`, router `llm` (its decision),
    per-item group `llm` (its planner), loop exit `llm` (judge) or `code` (check); tools of a
    model call are shared `tool:<name>` nodes (as in routing). A parallel group in branches mode
    has no node of its own.
  - Edges: `entries(b)` and `exits(b)` per block; consecutive blocks connect
    `exits(a) × entries(b)`; `start` → the first block, the last block → `end`; router and
    per-item planner → each route's/the body's entries; loop: body exits → exit node, exit node
    → body entries (repeat) and → next; model call ↔ its tool nodes. Terminal edges to `end`
    from every node that can stop the run wherever it sits: checks (failure), model calls with
    tools (iteration cap), loop exit nodes (round cap) and per-item planners (unusable plan).
  - Layout: a list runs left to right in 200 px columns; routes and branches stack in 110 px
    rows; a container is as wide as its widest child list; single nodes centre in their
    container's height.
- **Template equivalence (FR-013)**: with the conversions below, a converted template's graph
  has exactly the template's model, tool and check node ids, and its edges are a subset of the
  template's (the templates also declare error edges such as `orchestrator → end`); on the
  same script the taken edges are equal.

## 7. Template conversions (`blocks/convert.py`)

| Template | Blocks |
|---|---|
| ReAct | model `llm` (system prompt, tools, `max_iterations`); reasoning as the template |
| Chain | one model per step (`include_input` → message `"<label>: {input}\n\n<Prev>:\n{previous}"`), check `gate` (`min_bullets`) after the first step whenever the gate is on, also for a single step |
| Routing | router `router` (router prompt, fallback); each route: model `<route>` with the route's prompt and its tool (with tools: `max_iterations` 2 and `answer_on_last_call`, the M2 handler's tool call then an answer call without tools) |
| Parallel | parallel `reviews` (branches: one per aspect, model `<aspect>` with the filled review prompt), then model `merge` (merge prompt, message `"Text:\n{input}\n\n{reviews}"`) |
| Orchestrator | parallel `orchestrator` per-item (filled orchestrator prompt, `max_items` = `max_subtasks`, body: model `worker` with the worker prompt and message `"Request: {input}\n\nSubtask: {item}"`), then model `synthesizer` with message `"Request: {input}\n\n{orchestrator}"` |
| Evaluator | loop `evaluator` (judge = evaluator prompt plus `"Product: {input}"`, as the template's judge message; `max_rounds`), body: model `generator` with message `"{input}\n\n{feedback}"` |

Prompts and settings come from the agent's current config (template defaults or an M3 custom
agent's edits) and its model setting. Requests are not byte-identical to the template's (spec
assumption); SC-002 compares status, answer, call counts and taken edges on the same script, for
the golden template scripts and for malformed decisions (an invalid route label, an invalid
plan, an unreadable verdict).

**Name collisions**: M3 item names (steps, routes, aspects) become block names. A name that is a
reserved block name (`input`, `previous`, `feedback`, `item`) or collides with a fixed name the
conversion adds (`reviews`, `merge`, …) gets the first free `<name>-<n>`; references in converted
prompts use the new name, and the graph equals the template's up to that rename. Tests cover a
chain step named `input` and an aspect named `reviews`.

## 8. Spec adjustments made with this plan

- FR-008: the parallel group has no merge prompt of its own; merging is a model call after the
  group referring to its output (keeps the parallel and orchestrator graphs equal to the
  templates' and removes a duplicate prompt concept).
- FR-013 / US3-1: "same graph shape" is made testable as in §6.

## 9. UI

- **Decision**: block agents open in the existing `AgentBuilder` (graph left, panel right). The
  panel shows agent settings and a **block outline**: nested entries with kind, name, move
  up/down, remove, and a native `<select>` "Add block…" after each entry and at the end of each
  route, branch list and body (clarify Q3). Selecting an entry or clicking its node opens that
  block's settings form. Tree edits are pure functions in `lib/blocks.ts` (add, remove, move,
  rename with reference rewrite, find by name, default block per kind, error paths), covered by
  vitest. "New block agent" and "Open as blocks" fetch an unsaved draft from the server
  ([contracts/http-api.md](contracts/http-api.md)).
- **Rationale**: one place to edit (the outline), keyboard accessible, no drag and drop library;
  server-side conversion keeps prompts defined once, in Python.
