# Feature Specification: M3 — Agent Builder

**Feature Branch**: `main` (feature directory `003-agent-builder`)

**Created**: 2026-10-30

**Status**: Draft

**Input**: Agent Lab milestone M3: Agent Builder. In the UI the owner builds custom agents from
templates (the six existing agents), edits node prompts and settings, changes the structure each
template allows, and saves the result as a named agent that runs like the built-in ones.

## Context

M1 and M2 delivered six hand-built agents: ReAct and the five workflow patterns. Each has a
fixed configuration (prompts, limits, reasoning on/off) and a graph. To learn how prompts and
structure change behavior, the owner today has to edit code. M3 adds a builder: the six agents
become read-only **templates**, and the owner makes **custom agents** from them in the UI,
saves them by name and runs them with the same live graph, waterfall, replay and totals.

All M1/M2 core contracts apply unchanged: every model call and tool call emits a span on a node
of the run's graph; the graph and `config_version` are derived on the server from the
configuration; spans are persisted and streamed; secrets are redacted; servers stay on
127.0.0.1; tests use the scripted fake model.

### What each template lets the owner change

| Template | Prompts | Structure and limits |
|---|---|---|
| **ReAct** | system prompt | which existing tools it may use (none, some or all); max iterations |
| **Prompt chaining** | one prompt per step | ordered list of model steps (add, remove, reorder); code gate after the first step on or off, with its minimum bullet count |
| **Routing** | router prompt; one handler prompt per route | list of routes, each with a name, a description the router sees and an optional existing tool; which route is the fallback |
| **Parallelization** | review prompt (filled per aspect); merge prompt | list of aspects, each with a name and a focus |
| **Orchestrator-workers** | orchestrator, worker and synthesizer prompts | max number of subtasks |
| **Evaluator-optimizer** | generator and evaluator prompts | max rounds |

Every agent also has a name, a one-line description, a sample prompt and the reasoning setting.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Customize a template and run it (Priority: P1)

The owner opens the builder, picks a template, gets an editable copy with the template's
settings and graph, clicks a node to edit its prompt, names the agent, saves it and runs it.
The run looks like any other: live graph, waterfall, totals, replay.

**Why this priority**: editing prompts and seeing the effect is the core of the builder;
structure editing and agent management build on it.

**Independent Test**: create a custom agent from each template with one changed prompt, save
it, run it with the scripted fake model; the model request contains the changed prompt, every
span's node is in the custom agent's graph, and the run is listed under the custom agent's name.

**Acceptance Scenarios**:

1. **Given** the builder is open, **When** the owner picks a template, **Then** an editable copy
   appears with the template's graph, prompts, limits and reasoning setting, named after the
   template (e.g. "Routing (copy)").
2. **Given** an editable copy, **When** the owner clicks a model node, **Then** that node's
   prompt opens for editing; clicking the gate shows its minimum bullet count; clicking a tool
   node shows the tool's description.
3. **Given** a changed prompt, **When** the owner saves, **Then** the agent appears in the agent
   picker next to the templates, and a run of it sends the changed prompt to the model.
4. **Given** a template is selected in the picker, **When** the owner clicks its nodes, **Then**
   the settings are shown read-only with an action to customize a copy.

---

### User Story 2 - Change the structure a template allows (Priority: P2)

The owner adds, removes and reorders chain steps, adds or removes routes and parallel aspects,
picks the ReAct tools, turns the chain's gate on or off, and changes limits (iterations,
subtasks, rounds). The graph redraws as soon as the structure changes, before saving.

**Why this priority**: changing structure is what turns prompt tweaking into building; it makes
the patterns' trade-offs (more branches, more steps, more rounds) observable.

**Independent Test**: for each structural change, the graph derived from the saved config has
the expected nodes and edges, and a scripted run takes only declared edges.

**Acceptance Scenarios**:

1. **Given** a chaining copy, **When** the owner adds a fourth step "translate to German" and
   saves, **Then** the graph shows the new step in order and a run calls the model once more,
   ending with the new step's output.
2. **Given** a routing copy, **When** the owner adds a route "poem" with its description and
   handler prompt, **Then** the graph shows a fourth branch, the router can choose "poem", and
   a run classified as "poem" marks only that branch's edges.
3. **Given** a parallel copy, **When** the owner removes "tone" and adds "length", **Then** the
   graph shows the new aspect set and a run reviews exactly those aspects concurrently.
4. **Given** a ReAct copy, **When** the owner removes the weather tool, **Then** the graph has
   no weather tool node and the model is offered only the calculator.
5. **Given** a chaining copy, **When** the owner turns the gate off, **Then** the graph has no
   gate node and the steps run without the check.

---

### User Story 3 - Manage custom agents and keep history intact (Priority: P3)

The owner edits, duplicates and deletes saved agents. Past runs of an agent keep replaying with
the graph and configuration they ran with, even after the agent is edited or deleted.

**Why this priority**: experimenting means many variants; history must stay trustworthy while
the variants change.

**Independent Test**: run a custom agent, edit and re-run it, then delete it; both runs still
replay with their own graph and stored configuration, show different `config_version`s, and
the list still names the agent.

**Acceptance Scenarios**:

1. **Given** a saved agent, **When** the owner edits a prompt and saves, **Then** later runs get
   a new `config_version` and earlier runs keep their stored configuration and graph.
2. **Given** a saved agent, **When** the owner duplicates it, **Then** an independent copy named
   "<name> (copy)" appears; editing one does not change the other.
3. **Given** a saved agent with runs, **When** the owner deletes it after confirming, **Then**
   it leaves the picker and its runs still list (with the agent's name at run time) and replay.
4. **Given** invalid input (empty prompt, duplicate route name, too many aspects, unknown tool,
   a name already in use), **When** the owner saves, **Then** the save is rejected with a
   message naming the field, and nothing is stored.

### Edge Cases

- The owner leaves the builder or picks another agent with unsaved changes → asked to discard
  or keep editing; nothing is saved silently.
- A run is started while its agent is being edited → the run uses the last saved version.
- The agent is deleted while one of its runs is still running → the run finishes and stays in
  the past-runs list.
- A routing copy is reduced to its last two routes and one is removed → rejected: routing needs
  at least 2 routes; the fallback route cannot be removed without picking another.
- The router chooses a label that is not one of the custom routes → recorded as an invalid
  decision; the fallback route handles the question.
- A chaining copy with the gate on whose first step does not produce bullets → the gate stops
  the run with its reason, as in M2.
- The parallel review prompt omits the aspect or focus placeholder → saved as written; every
  reviewer then gets the same instruction (allowed, the owner may want that).
- Two custom agents with the same name → rejected; names are unique, ignoring case and
  surrounding spaces.
- An M1/M2 database → existing runs still list and replay; the six templates behave exactly as
  before.

## Requirements *(mandatory)*

### Functional Requirements

**Templates and custom agents**

- **FR-001**: The six existing agents MUST be available as read-only templates with unchanged
  behavior, ids, graphs and default configuration; runs of templates MUST behave as in M2.
- **FR-002**: The owner MUST be able to create a custom agent from any template; it starts as a
  copy of the template's configuration and keeps its template for life (a custom agent cannot
  change template).
- **FR-003**: A custom agent MUST have a name (1–60 characters, unique ignoring case and
  surrounding spaces), a one-line description (up to 200 characters), a sample prompt (up to
  4000 characters, as for run prompts) and the reasoning setting.
- **FR-004**: Custom agents MUST be stored in the local database and survive restarts; the owner
  MUST be able to edit, duplicate and delete them; deleting MUST ask for confirmation.
- **FR-005**: The agent picker MUST list templates and custom agents, visibly grouped, and MUST
  let the owner run a custom agent exactly like a template.

**What can be edited** (limits are inclusive)

- **FR-006**: Every prompt MUST be editable, 1–4000 characters.
- **FR-007**: ReAct: the set of allowed tools is any subset of the existing tools (including
  none); max iterations 1–10.
- **FR-008**: Prompt chaining: 1–6 model steps, each with a short name (unique within the agent)
  and a prompt; steps can be added, removed and reordered; each step gets the previous step's
  output and the first step gets the user's input; the code gate, when on, sits after the first
  step and requires 1–10 bullet lines.
- **FR-009**: Routing: 2–6 routes, each with a name (unique, lowercase letters, digits and
  hyphens, up to 30 characters), a description of up to 300 characters that the router sees,
  a handler prompt and at most one existing tool; exactly one route MUST be the fallback. The
  router MUST be asked to choose only among the agent's route names.
- **FR-010**: Parallelization: 1–6 aspects, each with a name (unique, same rule as route names)
  and a focus of up to 300 characters; the review prompt is filled per aspect with its name and
  focus.
- **FR-011**: Orchestrator-workers: max subtasks 1–6; an orchestrator plan above the max MUST be
  handled as an invalid plan, as in M2.
- **FR-012**: Evaluator-optimizer: max rounds 1–5.

**Builder UI**

- **FR-013**: The builder MUST show the agent's graph; clicking a node MUST open that node's
  settings (model node → prompt; gate → minimum bullets; tool node → tool name and description;
  start or empty area → agent-level settings).
- **FR-014**: Structural edits and limit changes MUST redraw the graph before saving; the graph
  shown MUST be the one the server derives from the configuration.
- **FR-015**: The builder MUST show whether there are unsaved changes and MUST ask before
  discarding them.
- **FR-016**: Invalid values MUST be reported next to the field they belong to; a rejected save
  MUST store nothing.

**Validation, runs and history**

- **FR-017**: The server MUST validate every custom agent configuration (counts, lengths, names,
  known tools, exactly one fallback) and MUST derive the graph and `config_version` from it; a
  graph or version sent by the client MUST NOT be used.
- **FR-018**: Runs of a custom agent MUST record its id, its name at run time and a snapshot of
  its configuration, graph and `config_version`; editing or deleting the agent MUST NOT change
  stored runs.
- **FR-019**: The past-runs list MUST show the agent's name for every run, including runs of
  deleted custom agents, and MUST distinguish custom agents from templates.
- **FR-020**: Every model and tool call of a custom agent MUST be a span on a node of its graph,
  with taken edges recorded as in M2; the M2 decision spans (route, gate, plan, verdict) and
  failure handling MUST apply with the custom routes, steps, aspects and limits.
- **FR-021**: Runs stored by M1 and M2 MUST still list and replay.

**Quality**

- **FR-022**: Tests with the scripted fake model MUST cover, per template, a custom agent with
  changed prompts and each structural change in User Story 2, the validation failures in User
  Story 3 and the history guarantees (edit, duplicate, delete).
- **FR-023**: All quality gates (`make check`) MUST pass; every requirement maps to a test or an
  explicit manual check in `tasks.md`.

### Key Entities

- **Template**: one of the six built-in agents: id, name, description, sample prompt, default
  configuration, and the rules for what may be changed.
- **Custom agent**: id, template id, name, description, sample prompt, configuration (prompts,
  structure, limits, reasoning), created and updated times. Its graph is derived from its
  configuration.
- **Run**: as in M2, plus the agent's name at run time; its configuration and graph are a
  snapshot and never change afterwards.
- **Span, Graph, Decision**: as in M2. No new node kinds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Starting from the app, the owner can create a custom agent from any template,
  change one prompt, save it and start a run in under 1 minute.
- **SC-002**: For every template, a custom agent with the structure at its minimum and at its
  maximum limit runs end to end with the scripted fake model, and 100% of its spans are on
  nodes of its graph.
- **SC-003**: After a structural change, the graph shown in the builder matches the graph stored
  with the next run of that agent in 100% of tested cases.
- **SC-004**: After editing or deleting a custom agent, 100% of its earlier runs replay with the
  configuration and graph they ran with.
- **SC-005**: Every invalid input listed in User Story 3 and the edge cases is rejected with a
  message naming the field, and the stored agents are unchanged afterwards.
- **SC-006**: Runs of the six templates produce the same spans, edges and end states as before
  M3 (the M2 test suite passes unchanged in substance).

## Future Scope (not planned in M3)

- **M4 MCP**: hand-written MCP JSON-RPC server and host.
- **M5 Harness**: budgets, timeouts, retries, context compaction, approval gates.
- **M6 Agent memory**: store, retrieve, reflect.
- **M7 RAG**: small retrieval pipeline with retrieve/rerank spans.
- **Phase 2 Village**: tick-driven runner over the same agents and workflows.
- Free-form graph editor, new tools, new node kinds, import/export of agents, configuration
  version history, side-by-side run comparison.

## Assumptions

- One owner, one browser; concurrent edits of the same agent are not coordinated (last save
  wins).
- Runs always use the saved version of an agent; unsaved builder changes are never run.
- The model stays the configured default for every agent; choosing a model per agent or per node
  is out of scope.
- Templates cannot be edited or deleted; to change one, the owner customizes a copy.
- The chain gate stays the M2 bullet check; only whether it runs and its minimum count change.
- Routing handlers with a tool behave like the M2 math and weather handlers (one model call with
  the tool, its tool calls, then the answer); handlers without a tool answer in one call.
- Orchestrator workers stay plain model calls without tools; evaluator verdicts keep the M2
  approve-or-feedback shape.
- Limits (steps, routes, aspects, subtasks, rounds, iterations) are chosen to keep graphs
  readable and runs short on the local model; they can be raised in a later milestone.
- Custom agents are kept until deleted; no retention policy.
