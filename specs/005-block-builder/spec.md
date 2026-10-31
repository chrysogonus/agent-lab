# Feature Specification: M5 — Composable Block Builder

**Feature Branch**: `main` (feature directory `005-block-builder`)

**Created**: 2026-10-31

**Status**: Draft

**Input**: Agent Lab milestone M5: the owner builds agents from composable blocks instead of
only editing the fixed shape of a template: add extra model calls, tool calls, checks, routers,
parallel groups and loops anywhere in an ordered, nestable list. The six templates become
starting layouts that open as blocks.

## Context

M3 lets the owner edit a template's prompts and the structure that template allows (chain
steps, routes, aspects); M4 adds a model choice per agent. The owner now wants more freedom:
"add extra tool calls or nodes or LLM calls". In clarify for M4 the owner chose **composable
blocks** over a free-form graph editor.

A **block agent** is an ordered list of **blocks** that run top to bottom. Some blocks hold
other blocks (a router's routes, a parallel group's branches, a loop's body), so layouts nest.
The graph is derived from the blocks, as today from template configs. Every M1–M4 core contract
applies unchanged: every model and tool call is a span on a node of the run's graph; graphs and
`config_version` come from the server; secrets are redacted; servers bind to 127.0.0.1; tests
never call a real model; the agent's model (M4) applies to every model call of the agent.

## Clarifications

### Session 2026-10-31

- Q: Should block agents be a new kind next to templates and M3 agents, or should everything
  become blocks? → A: A new kind. Templates and M3 agents stay as they are; "Open as blocks"
  makes an editable block copy.
- Q: Should a parallel group also run its blocks once per item a model plans at run time? → A:
  Yes, as a second mode of the parallel group (no separate block kind), so all six templates
  open as blocks.
- Q: Where are blocks added and arranged: an outline in the settings panel, "+" buttons on the
  graph, or both? → A: An outline in the settings panel (add menu after any block and inside each
  container, remove, move up/down); the graph is a live view whose nodes open block settings.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Build a sequence of blocks and run it (Priority: P1)

The owner creates a block agent, adds a model call, then a tool call, then another model call,
writes their prompts (referring to the user's input and earlier outputs), saves and runs it.
The graph shows one node per block; the run streams spans onto those nodes.

**Why this priority**: adding model and tool calls in sequence is the most direct answer to
the owner's request and the base every other block builds on.

**Independent Test**: a block agent of three blocks (model call → calculator tool call whose
argument comes from the first output → model call using both outputs), run on the scripted
model, sends the expected prompts, calls the tool with the expected argument, ends `completed`
with the last block's output, and every span is on a node of the derived graph.

**Acceptance Scenarios**:

1. **Given** the builder, **When** the owner chooses "New block agent", **Then** an unsaved
   agent with one model-call block and the default model opens, its graph showing start → that
   block → end.
2. **Given** a block agent, **When** the owner adds, removes or moves a block, **Then** the
   graph redraws before saving.
3. **Given** a prompt that refers to the user's input, the previous block's output or an
   earlier block by name, **When** the agent runs, **Then** the model receives the prompt with
   those values filled in.
4. **Given** a tool-call block with an argument built from earlier outputs, **When** the agent
   runs, **Then** the tool runs with that argument and its result is that block's output.
5. **Given** a saved block agent, **When** the owner runs it, **Then** it appears in the
   past-runs list and replays like any other run.

---

### User Story 2 - Nest routers, parallel groups, loops and checks (Priority: P2)

The owner composes control flow: a check that stops the run when an output is unusable, a
router whose routes are block lists, a parallel group whose branches run at the same time, and
a loop that repeats its body until a check passes or a judge approves.

**Why this priority**: control flow is what turns a sequence into an agent pattern; it lets the
owner rebuild and vary the M2 patterns.

**Independent Test**: for each control block, a scripted run takes exactly the expected branch,
branches, or number of rounds; the graph shows the nesting; every taken edge is declared.

**Acceptance Scenarios**:

1. **Given** a check block (for example "at least 3 bullet lines") after a model call, **When**
   the output fails the check, **Then** the run ends `error` with a message naming the check,
   and no later block runs.
2. **Given** a router block with routes, each a list of blocks, **When** the model's decision
   picks a route, **Then** only that route's blocks run; an invalid decision falls back to the
   route marked as fallback.
3. **Given** a parallel group with fixed branches, **When** it runs, **Then** the branches start
   together, and the group's output lists each branch's output under its name.
4. **Given** a parallel group in "one branch per planned item" mode, **When** its planning model
   call returns a list of items, **Then** the body runs once per item, concurrently, up to the
   group's maximum.
5. **Given** a loop with a body, an exit condition (a check or a judge model call that approves
   or gives feedback) and a maximum number of rounds, **When** it runs, **Then** it repeats the
   body until the condition holds or the maximum is reached; the judge's feedback is available
   to the next round's prompts; reaching the maximum ends the run `max_iterations`.
6. **Given** a model-call block with tools and a maximum number of iterations, **When** the model
   calls tools, **Then** the block loops model call → tool calls until the model answers or the
   maximum is reached (the ReAct pattern as one block).

---

### User Story 3 - Start from a template, keep history and limits safe (Priority: P3)

The owner opens any template or M3 custom agent "as blocks", gets an equivalent block layout to
edit, and finds that invalid layouts are rejected per block while past runs never change.

**Why this priority**: templates as starting layouts make the six patterns the first examples
of block agents; validation and history keep experiments safe.

**Independent Test**: each of the six templates opened as blocks and run on the same script as
its template run completes with the same status and answer and visits the equivalent nodes;
each invalid layout in the validation list is rejected with an error naming its block and
field, and nothing is stored.

**Acceptance Scenarios**:

1. **Given** any template or template-based custom agent, **When** the owner chooses "Open as
   blocks", **Then** an unsaved block agent opens with the same prompts, settings and model,
   expressed as blocks, and its graph has the same shape.
2. **Given** an invalid layout (an empty prompt, a reference to a later or unknown block, a
   router with one route, more than the allowed blocks or nesting), **When** the owner saves or
   runs it, **Then** it is rejected, each error is shown at its block and field, and nothing is
   stored.
3. **Given** runs of a block agent, **When** the owner edits or deletes the agent, **Then** the
   past runs still list and replay with the blocks, graph and config they ran with.
4. **Given** templates and M3 custom agents, **When** M5 is in place, **Then** they still list,
   edit and run exactly as in M4.

### Edge Cases

- A block is renamed while later prompts refer to it → the references are updated with it; a
  reference to a removed block is a validation error at the referring field.
- Two blocks get the same name → rejected; names are unique across the whole layout because
  they are also graph node ids.
- A route, branch or loop body is left empty → rejected (each holds at least one block).
- A parallel group's planner returns more items than the maximum or an unusable list → the run
  ends `error`, as an invalid orchestrator plan does in M2.
- A loop's judge returns an unusable verdict → the run ends `error` naming the loop.
- A tool-call argument evaluates to text the tool rejects → the tool's error is the block's
  output and is recorded on the span, as tool errors are in M1.
- A parallel branch fails → the group fails, the run ends `error`; branches already running
  finish and stay in the trace.
- A loop inside a parallel branch or a router inside a loop → allowed up to the nesting limit;
  node ids stay unique because block names are unique.
- A block agent on an external model (M4) → every model call of every block goes to that model.
- A layout at the maximum size → the graph stays readable (laid out by nesting level).

## Requirements *(mandatory)*

### Functional Requirements

**Block agents**

- **FR-001**: The owner MUST be able to create, edit, save, duplicate and delete block agents;
  they appear in the agent picker next to templates and M3 custom agents and run like them.
- **FR-002**: A block agent MUST have a name, description, sample prompt, the M4 model setting,
  the reasoning setting and an ordered list of blocks; blocks run top to bottom, each receiving
  the previous block's output.
- **FR-003**: Every block MUST have a name that is unique in the agent and is its graph node id;
  names follow the M3 rules for node ids.

**Block kinds**

- **FR-004**: **Model call**: a system prompt and a message template; optionally tools it may
  call and a maximum number of tool iterations (1–10), in which case it loops until the model
  answers; its output is the final answer text.
- **FR-005**: **Tool call**: one tool from the tool catalog and an argument template; its output
  is the tool result.
- **FR-006**: **Check**: one built-in check on the previous output (at least N bullet lines, at
  most N words, contains a text, is valid JSON); failing ends the run `error` naming the check;
  passing passes the output on unchanged. No user-written code runs.
- **FR-007**: **Router**: a router prompt and 2–6 routes, each with a name, a description for the
  router and a list of blocks, one marked fallback; the decision is requested as structured
  output listing the route names (M2 decision rules); the output is the chosen route's output.
- **FR-008**: **Parallel group**: either 1–6 named branches, each a list of blocks, or a planning
  model call plus a body that runs once per planned item (maximum 1–6); branches and items run
  concurrently; an optional merge prompt combines the outputs, otherwise the output lists each
  branch's or item's output under its name or number.
- **FR-009**: **Loop**: a body (a list of blocks), an exit condition (a check, or a judge prompt
  answering approved/feedback as structured output) and a maximum of 1–5 rounds; the judge's
  last feedback is available to the body's prompts in the next round.

**Data flow**

- **FR-010**: Prompts and argument templates MUST be able to refer to the user's input, the
  previous block's output, the output of any earlier block by name, and inside loops the last
  feedback and inside per-item groups the current item; values are filled by plain text
  replacement; references to unknown or not-yet-run blocks MUST be rejected on save.

**Graph, runs and tracing**

- **FR-011**: The server MUST derive the graph (nodes, edges, layout) from the blocks; a
  container block appears with its children so that every model call, tool call and decision is
  a span on a declared node and every taken edge is declared.
- **FR-012**: A run of a block agent MUST store a snapshot of its blocks, graph and config, and
  get a `config_version` from them; editing or deleting the agent never changes past runs.

**Templates**

- **FR-013**: "Open as blocks" MUST convert any of the six templates, and any M3 custom agent
  built on one, into an equivalent unsaved block agent: same prompts, settings, model and graph
  shape; run on the same scripted model it MUST reach the same status and answer.
- **FR-014**: Templates and M3 custom agents MUST keep working unchanged (golden requests,
  versions, editing as in M3–M4).

**Builder UI**

- **FR-015**: The builder MUST show a block agent as its graph plus an outline of its blocks
  (with nesting) in the settings panel. All editing happens in the outline: an add menu (any
  block kind) after any block and inside each container, remove, and move up or down within its
  list; the graph has no editing controls. Clicking a node or an outline entry opens that block's
  settings; the graph redraws from the server before saving.
- **FR-016**: Validation errors MUST be shown at the block and field they belong to.

**Limits and validation**

- **FR-017**: The server MUST validate every layout on save and on run start: at most 30 blocks
  in total, nesting at most 3 levels deep, the per-kind limits above, non-empty prompts and
  lists, unique names, known tools, valid references; every rejection names its block and field.

**Quality**

- **FR-018**: Tests MUST use the scripted fake model only; they MUST cover each block kind,
  nesting, data references, the template conversions, validation and history.
- **FR-019**: All quality gates MUST pass; every requirement maps to a test or an explicit
  manual check in `tasks.md`.

### Key Entities

- **Block agent**: name, description, sample prompt, model setting (M4), reasoning setting,
  blocks; stored like M3 custom agents and listed with them.
- **Block**: kind (model call, tool call, check, router, parallel group, loop), unique name, the
  kind's settings, and for containers their lists of child blocks.
- **Reference**: a placeholder in a prompt or argument template naming the input, the previous
  output, an earlier block, the loop feedback or the current item.
- **Run**: as in M4, with a snapshot of the blocks it ran.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can build a three-block agent (model call → tool call → model call) from
  scratch and start a run in under 3 minutes.
- **SC-002**: Each of the six templates, opened as blocks and run on the same script, reaches the
  same status and answer as the template, with the same number of model and tool calls.
- **SC-003**: For every block kind, at its minimum and maximum limits, 100% of spans of a
  scripted run lie on declared nodes and every taken edge is declared.
- **SC-004**: 100% of the invalid layouts in the validation test list are rejected with an error
  naming their block and field, and none is stored.
- **SC-005**: Past runs of an edited or deleted block agent replay exactly as recorded.
- **SC-006**: A block agent at the maximum size (30 blocks, 3 levels) shows its graph after an
  edit within 1 second on the owner's machine.

## Future Scope (not planned in M5)

- Drag and drop, a free-form graph editor, per-block model choice, user-written code in checks,
  new tools, import/export, version history of an agent.
- **M6 MCP**, **M7 Harness** (budgets, retries, approvals), **M8 Agent memory**, **M9 RAG**,
  **Phase 2 Village**.

## Assumptions

- Block agents are a new kind next to templates and M3 custom agents (clarified); templates and
  M3 agents are not migrated and the template editor stays. "Open as blocks" makes a block copy
  and leaves the original as it is.
- A converted template's requests need not be byte-identical to the template's (for example the
  router prompt may list routes slightly differently); equivalence means same prompts and
  settings, same status, answer and call counts on the same script.
- Checks are a fixed set of built-in checks; anything that needs code waits for a later
  milestone (the constitution forbids running model output as code).
- Moving blocks uses up/down buttons within a list; moving a block into another container means
  removing and re-adding it.
- The agent's model and reasoning settings apply to every model call in the agent.
- Limits (30 blocks, 3 levels, per-kind ranges) keep graphs readable and runs bounded; they can
  be raised later.
