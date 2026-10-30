# Research: M2 — Workflow Patterns

## Structured decisions
- Decision: OpenAI-compatible `response_format: {"type": "json_schema", "json_schema": {"name",
  "schema", "strict": true}}`, schema generated from a pydantic model per decision, result
  validated by the same model. Fallback parser extracts one JSON object from prose or a code fence.
- Rationale: chosen in clarify. Verified on 2026-10-30 against local Ollama 0.21.2 + `qwen3:8b`:
  a route schema with an enum returned `{"label": "math"}`. Validation stays because other servers
  may ignore the schema.
- Alternatives: forced tool call (Ollama cannot force it), plain-text parsing (fragile).

## Reasoning control
- Decision: client parameter `reasoning: bool | None`; `False` → `reasoning_effort: "none"`.
- Rationale: verified locally: `reasoning_effort: "none"` returned 0 reasoning characters and 7
  output tokens for a classification. Provider-neutral name so an Anthropic adapter can map it to
  its own thinking setting.
- Alternatives: Ollama's native `think` flag (only on the native API, not `/v1`).

## Recording edges
- Decision: the span that starts a node visit carries `lab.came_from` (list of node ids).
- Rationale: fan-in (merge after three branches), dynamic fan-out (workers) and loops (evaluator →
  generator) cannot be inferred reliably from timing; the workflow code knows where control came
  from. It also makes edges testable in Python. M1 runs lack the attribute and keep the M1
  inference in the UI.
- Alternatives: generalized inference from span overlap (ambiguous for sequential tool calls vs.
  concurrent branches); a tracer-maintained frontier in a contextvar (forks correctly but loses
  the fan-in after `gather`).

## Concurrency
- Decision: `asyncio.gather(*branches, return_exceptions=True)`; each branch opens its own span.
- Rationale: tasks copy the context, so the tracer's contextvar parenting is correct per branch.
  `return_exceptions` gives the partial-failure behavior from the spec.

## Testing concurrent workflows
- Decision: `FakeLLM` script items may be callables that answer based on the messages; optional
  `delay` makes branch overlap measurable.
- Rationale: concurrent branches pop scripted responses in nondeterministic order.

## Totals
- Decision: aggregate query over `spans` per run (counts by kind, token sums); wall time from the
  run row. UI computes the same totals live from spans.
- Rationale: no migration, works for M1 runs, one obvious definition (documented in data-model).

## Workflow structure
- Decision: each workflow is plain async code in its own module, using `chat`, `call_tool`,
  `decide`; no graph-execution engine.
- Rationale: readable in one sitting (principle I); the declared graph is for observation, not
  execution. An engine would be a speculative abstraction (principle IV).

## ReAct and reasoning
- Decision: `ReActConfig.reasoning = True`; new ReAct runs get a new `config_version`.
- Rationale: the config really changed (it now states the setting); old runs keep their stored
  config and version.
