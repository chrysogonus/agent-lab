# Data Model: M2

M1 entities (Span, Run, Graph) are unchanged except where noted.

## Graph node kinds
`start | llm | tool | code | end` — `code` is new (code-only steps such as the chain gate).

## Span attributes added in M2
| Key | Type | On | Meaning |
|---|---|---|---|
| `lab.came_from` | list[str] | first span of each node visit | node ids control came from; every pair is a declared edge |
| `lab.reasoning` | bool \| null | llm spans | reasoning setting sent |
| `gen_ai.request.response_format` | object | llm spans of decisions | the JSON schema request |
| `lab.round` | int | evaluator generator/evaluator spans | 1..3 |
| `lab.worker.index` | int | orchestrator worker spans | 0..3 |

## Decisions (pydantic models; JSON schema sent to the model)
| Decision | Fields | Validation | On invalid |
|---|---|---|---|
| Route | `label: "math" \| "weather" \| "general"` | enum | route span error; use `general` |
| GateResult | `passed: bool, reason: str` | code-computed (≥ 3 bullet lines) | n/a (code) |
| Plan | `subtasks: list[str]` | 1..4 items, each non-empty, ≤ 200 chars | plan span error; run `error` |
| Verdict | `approved: bool, feedback: str` | feedback non-empty when not approved | verdict span error; treat as not approved |

## Workflow configuration (each a pydantic model, hashed into `config_version`)
Common: `model: str`, `reasoning: bool` (default False; ReAct True), prompts (str).
Caps: chain — none; parallel — aspects (fixed 3); orchestrator — `max_subtasks = 4`;
evaluator — `max_rounds = 3`.

## AgentInfo (API)
`id, name, description, sample_prompt, graph`

## RunTotals (API, on Run)
| Field | Definition |
|---|---|
| llm_calls | count of spans with kind `llm` |
| tool_calls | count of spans with kind `tool` |
| tokens_in / tokens_out | sum over spans (null treated as 0) |
| wall_ms | (run.ended_at − run.started_at) × 1000, null while running |

## Run status (unchanged values)
`running | completed | max_iterations | error`. Mapping: chain gate fail → `error`; orchestrator
invalid plan → `error`; all parallel branches failed → `error`; evaluator cap → `max_iterations`.
