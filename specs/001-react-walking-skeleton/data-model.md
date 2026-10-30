# Data Model: M1

## Span (core contract 1)

| Field | Type | Notes |
|---|---|---|
| trace_id | str (32 hex) | = run's trace; one trace per run |
| span_id | str (16 hex) | PK |
| parent_span_id | str \| null | null for the root span |
| run_id | str | FK → Run |
| agent_id | str | `react` |
| node_id | str | must be a node of the run's graph |
| config_version | str (12 hex) | from agent config |
| kind | `llm \| tool \| route \| retrieve \| rerank \| memory \| step` | M1 uses step, llm, tool |
| name | str | GenAI-style, e.g. `chat qwen3:8b` |
| input, output | JSON \| null | redacted |
| error | str \| null | redacted |
| started_at, ended_at | float epoch s | `ended_at` null while running |
| tokens_in, tokens_out | int \| null | llm spans |
| model | str \| null | llm spans |
| attributes | JSON object | GenAI semantic-convention keys |

## Run

| Field | Type | Notes |
|---|---|---|
| run_id | str (uuid4 hex) | PK |
| agent_id, config_version | str | |
| prompt | str | 1..4000 chars, redacted before storage |
| status | `running \| completed \| max_iterations \| error` | `running` → one terminal state |
| answer | str \| null | final model answer |
| graph | Graph | snapshot at run start |
| config | JSON | agent config used (system prompt, model, tools, max_iterations) |
| started_at, ended_at | float | |

## Graph

- `Node {id, label, kind: start|llm|tool|end, x, y}`
- `Edge {source, target}`

## SQLite

`runs(run_id PK, agent_id, config_version, prompt, status, answer, graph, config, started_at, ended_at)`
`spans(span_id PK, run_id, trace_id, parent_span_id, agent_id, node_id, config_version, kind,
name, input, output, error, started_at, ended_at, tokens_in, tokens_out, model, attributes)`,
index on `spans(run_id, started_at)`. JSON columns stored as text.
