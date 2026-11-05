# Interfaces: M17 — The Evaluation Harness

Field rules are in [data-model.md](../data-model.md). Refusals use the API's existing shapes: 404 for
an unknown id, 409 with a `detail` reason, and FastAPI's 422 with the field's `loc`.

## Budgets and ask-first tools

`AgentInfo` gains:

```json
{"budget": {"model_calls": 30, "tokens": 200000, "tool_calls": 30, "seconds": 600},
 "ask_first": ["notes/write_note"]}
```

Templates always have `"budget": null, "ask_first": []`.

| Request | Field | Absent | `null` or `[]` |
|---|---|---|---|
| `POST /agents` | `budget` | the default budget | no budget |
| `PUT /agents/{id}` | `budget` | unchanged | no budget |
| `POST /agents` | `ask_first` | none | none |
| `PUT /agents/{id}` | `ask_first` | unchanged | none |
| `POST /agents` | `cases_from` | no cases | no cases; otherwise a template or agent id to copy from |

`GET /budget-limits` answers `{"default": <budget>, "max": <budget>}`.

`DELETE /agents/{id}` answers 409 while an evaluation of that agent is running.

## Runs

`Run` gains `stop_reason` and `harness`, and its `status` gains `waiting_approval`, `over_budget`,
`stopped` and `interrupted`.

| Request | Answer |
|---|---|
| `POST /runs/{id}/stop` | 202 and the run; 409 if it is not a live lab run (finished, or the village's) |

### Stream events

`WS /runs/{id}/stream` keeps its events and adds one, sent on each change and in the snapshot of a
run that is waiting:

```json
{"type": "run_status", "run_id": "…", "status": "waiting_approval"}
```

`run_ended` still closes the stream. A run counts as ended unless its status is `running` or
`waiting_approval`.

## Approvals

| Request | Answer |
|---|---|
| `GET /approvals` | every open request, oldest first |
| `POST /approvals/{id}` | body below; 204; 404 if no longer open; 403 for a foreign `Origin` |

```json
{"decision": "deny", "reason": "not now"}
```

`decision` is `approve` or `deny`. `reason` is optional, at most 500 characters.

```json
{"approval_id": "…", "run_id": "…", "agent_name": "Notes", "prompt": "…",
 "tool": "notes/write_note", "server": "notes", "arguments": {"name": "a", "text": "b"},
 "asked_at": 1793875000.0, "expires_at": 1793875600.0}
```

## Test cases

| Request | Answer |
|---|---|
| `GET /agents/{id}/cases` | a template's examples first, then the owner's cases by name |
| `POST /agents/{id}/cases` | 201 and the case; 409 at 50 cases |
| `PUT /cases/{id}` | the case; 409 for an example |
| `DELETE /cases/{id}` | 204; 409 for an example |

```json
{"case_id": "case-1a2b", "agent_id": "react", "name": "Multiplies", "read_only": false,
 "prompt": "What is 17 times 23?", "approvals": "deny",
 "checks": [{"kind": "contains", "text": "391"}, {"kind": "tool_called", "tool": "calculator"}]}
```

`read_only`, `case_id` and `agent_id` are the server's; the rest is what a client sends.

## Evaluations

| Request | Answer |
|---|---|
| `POST /agents/{id}/evaluations` | 202 and the evaluation; 409 if one runs; 422 for an unavailable model or an unknown case |
| `GET /agents/{id}/evaluations` | that agent's evaluations with their summaries, newest first |
| `GET /evaluations/{id}` | the evaluation, its summary, and every attempt |
| `POST /evaluations/{id}/stop` | 202 and the evaluation; 409 if it is not running |
| `GET /evaluations/compare?earlier=…&later=…` | the comparison; 422 if they are of different agents |
| `GET /evaluations/notice?provider=…` | `{"village_shares_provider": true}` |

Start body. Without `case_ids` it runs them all; without `model` it uses the agent's own:

```json
{"repeats": 3, "case_ids": ["case-1a2b"], "model": {"provider": "anthropic", "model": "claude-haiku-5-5"}}
```

Summary, per case and overall:

```json
{"passed": 2, "failed": 1, "errors": 0, "pass_rate": 0.667,
 "avg_llm_calls": 2.0, "avg_tokens": 310.5, "avg_wall_ms": 1840}
```

`pass_rate` is `null` when every attempt is an error.

## Trace

Each model call attempt is one `llm` span, as today. These attributes are new, and only set by runs
with a guard:

| Attribute | On | Value |
|---|---|---|
| `lab.retry.attempt` | an attempt after the first, or a failed one that will be retried | 1, 2 or 3 |
| `lab.retry.reason` | a failed attempt that will be retried | the error's first line |
| `lab.retry.wait_s` | the same | seconds before the next attempt |

An approval decision is one `step` span named `approval <tool>`, on the tool's node, with `input` the
redacted arguments and `output` the decision's text:

| Attribute | Value |
|---|---|
| `gen_ai.tool.name` | the config name |
| `lab.approval.decision` | `approved`, `denied` or `timed_out` |
| `lab.approval.by` | `owner`, `timeout` or `case` |
| `lab.approval.reason` | the reason, when there is one |
| `lab.came_from` | as on the tool span it precedes |

A denied call has this span and no tool span. An approved call also has the usual tool span.

A judge's call is its own run: `agent_id` `judge`, the evaluation's `eval_id`, the graph
`start → judge → end`, and one `decide` step at `judge` with the answer `{"answer": "yes" | "no"}`.

## Model clients (`llm/base.py`)

```python
class PassingLLMError(LLMError):
    wait_hint: float | None  # seconds the provider asked for
```

`OpenAICompatClient` and `AnthropicClient` raise it for the failures in
[research.md](../research.md) §7. Its text is what a plain `LLMError` would have said.
