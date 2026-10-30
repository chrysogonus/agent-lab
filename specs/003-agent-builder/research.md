# Research: M3 — Agent Builder

## What a custom agent is
- Decision: a stored row with a template id, name, description, sample prompt and a config
  validated by the template's existing pydantic `Config` model. No new agent classes.
- Rationale: the M2 `Config` models already hold every prompt and cap and are hashed into
  `config_version`; making them the editable shape keeps one source of truth for defaults,
  limits and validation (FR-017).
- Alternatives: a generic node/edge description run by an engine (the out-of-scope free-form
  editor, and a speculative abstraction under principle IV); per-field overrides on top of the
  template (merging rules, and old overrides break when a template changes).

## Generalising the fixed structures
- Decision: chain `steps` and routing `routes` become lists in their configs; the orchestrator
  gets `max_subtasks`; parallel keeps its `aspects` dict (already ordered and name-unique);
  ReAct and the evaluator get limits only.
- Rationale: these are exactly the structures the spec lets the owner change. Keeping the
  parallel, ReAct and evaluator shapes leaves their template `config_version` unchanged.
- Consequence: the chain, routing and orchestrator templates get a new `config_version` once
  (the config was re-expressed, not changed in substance); old runs keep theirs, as with the
  ReAct reasoning change in M2.

## Template behavior after the refactor (SC-006)
- Decision: the generic message rules reproduce every M2 request byte for byte:
  - Chain: a step with `include_input` off gets the previous output unwrapped (M2 polish); with
    it on, `{input_label}: {input}\n\n{Previous step name, capitalised}:\n{previous output}`.
    The template's `input_label` is `Product`, so the draft message stays
    `Product: {input}\n\nOutline:\n{outline}`.
  - Router: system prompt = `router_prompt` followed by ` {name}: {description}.` per route,
    non-fallback routes in list order and the fallback last (trailing periods of descriptions
    stripped). Template: `Classify the user's question.` + math, weather, general gives the M2
    text exactly, while the routes list keeps the M2 graph order (math, general, weather).
  - Orchestrator: see placeholders below. Parallel, evaluator and ReAct messages are unchanged.
- Rationale: FR-001 and FR-008 require unchanged template behavior; matching requests exactly is
  cheap with these rules and needs no template-only special cases.
- Verification: before the refactor, scripted `FakeLLM` runs of all six templates record every
  request (messages, tools, response format) and the graphs into `tests/golden/`; after the
  refactor the same runs must produce identical requests, graphs, taken edges and end states.
- Not identical by design: the chain, routing and orchestrator configs change shape (same
  values), so their `config_version` changes once; old runs keep theirs.

## Decision models that depend on config
- Decision: `route_model(names)` and `plan_model(max_subtasks)` build the decision model per
  config with `pydantic.create_model` (route label: a `Literal` of the route names; plan:
  `Field(max_length=max_subtasks)`), each a few lines with one documented type-ignore if pyright
  strict needs it.
- Rationale: `steps.decide` derives the JSON schema sent to the model from the model class, so
  the schema lists exactly the agent's routes and subtask limit; validation and schema stay one
  object.
- Alternatives: hand-written JSON schema plus a separate validator (two definitions that can
  drift); `label: str` with a validator (schema loses the enum, the model then guesses labels).

## Filling placeholders in prompts
- Decision: `{aspect}`, `{focus}` (parallel) and `{max_subtasks}` (orchestrator) are filled with
  `str.replace`; no `str.format`.
- Rationale: custom prompts are free text; `str.format` raises on any other brace (e.g. a JSON
  example) and turns a prompt edit into a run crash. The template output is identical.
- Orchestrator: placeholders `{min_subtasks}` (= min(2, max_subtasks)) and `{max_subtasks}`.
  The template prompt becomes `... into {min_subtasks} to {max_subtasks} independent
  subtasks ...`: exactly the M2 text at the default of 4, `1 to 1` at the minimum and `2 to 6`
  at the maximum, always consistent with the plan schema (resolves the deferred clarify point).
  Tests check the rendered prompt and the schema's `maxItems` at limits 1, 4 and 6.

## Graph preview before saving
- Decision: `POST /graph {template_id, config}` validates the config and returns the derived
  graph; the UI calls it 300 ms after the last edit.
- Rationale: FR-014 requires the shown graph to be the server's; duplicating `build_graph` in
  TypeScript would drift. The same call reports field errors live. Loopback round trips are a
  few milliseconds.
- Alternatives: redraw only after saving (contradicts FR-014); port graph builders to the
  frontend (two implementations).

## Validation errors
- Decision: every rejection (pydantic errors, unknown template, name conflict) uses FastAPI's
  `422 {"detail": [{"loc": [...], "msg": ...}]}`; `loc` paths point into the request body
  (e.g. `["body", "config", "routes", 2, "name"]`).
- Rationale: one error shape lets `lib/builder.ts` map every message to its field (FR-016).
  The store's UNIQUE constraint on `name_key` catches races; the API turns it into the same
  shape.

## Model per agent
- Decision: stored configs omit `model`; `resolve` injects the server's configured model.
- Rationale: the spec keeps one model for every agent; a stored model would silently pin old
  agents to a model the server no longer serves.

## Storage migration
- Decision: `CREATE TABLE IF NOT EXISTS agents`; for `runs`, read `PRAGMA table_info` and add
  `agent_name` and `template_id` (nullable) when missing. Old runs keep NULL; the UI falls back
  to the agents list for their names, and a NULL `template_id` means "template run".
- Rationale: no migration framework needed for two nullable columns; M1/M2 databases open
  unchanged otherwise (FR-021).

## Run config snapshot
- Decision: `runs.config` stores the redacted config, like the redacted prompt.
- Rationale: custom prompts are owner input and may contain a pasted key; the agents table keeps
  the owner's text, the run snapshot (streamed and shown) is scrubbed.

## Duplicate and copy names
- Decision: duplication happens in the UI (`POST /agents` with the copied fields); `copyName`
  picks "<name> (copy)", then "(copy 2)", … avoiding names in the agents list.
- Rationale: no extra endpoint; the server still enforces uniqueness.

## Unsaved-changes guard
- Decision: `window.confirm` when switching agent or opening a run with a dirty draft, plus a
  `beforeunload` handler.
- Rationale: native, accessible, no dialog component; enough for one owner.
