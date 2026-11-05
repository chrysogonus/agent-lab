# Research: M17 — The Evaluation Harness

The starting point:
- **One path to the model and the tools**: every call goes through `steps.chat`, `steps.call_tool`
  or `steps.decide`. Agents build their own `StepContext` in seven constructors.
- **Runs**: `execute_run` runs an agent in a task and maps its result to a status. There is no way
  to stop a task, and nothing marks a run left "running" by a restart.
- **`config_version`** hashes the whole config dump, and `test_config_versions` pins the hashes.
- **Model errors**: both clients raise a plain `LLMError` for every failure, with no retries.
- **The village** also goes through `execute_run` and `steps`, so anything added there must stay
  off for its runs (FR-023).
- **`runs.eval_id`** exists since M13, and hides a run from the run lists. Only the village's turn
  checks set it, in their own copy of the database.

Items 4, 5 and 6 rest on a throwaway probe under Python 3.12: cancelling through a nested
`gather(return_exceptions=True)`, ending it with `asyncio.timeout`, and pausing that timeout with
`reschedule`.

## 1. Where budgets and ask-first tools live

- **Decision**: a new nullable `agents.harness` column (JSON: `budget`, `ask_first`), outside
  `config`. A run snapshots what it ran under in `runs.harness`.
- **Rationale**: adding fields to the config models changes every dump, so every existing agent's
  `config_version` and the pinned hashes change too (SC-001). A budget limits a run and does not
  change what the agent asks the model, so results show it beside the config version instead of
  inside it. The seven config models also stay as they are.
- **Alternatives**:
  - Fields on each config model, excluded from the hash: seven models change, and `editable`, the
    run snapshot and the builder's config all gain fields that are not config.
  - A separate table: more code for one row per agent.

## 2. How the harness reaches `steps`

- **Decision**: a `RunGuard` in a `ContextVar`, set by `execute_run` for the length of the run.
  With no guard (the village, direct agent tests, the golden tests), `steps` behaves exactly as
  today.
- **Rationale**: `tracer.py` already keeps the current span this way, and `asyncio.gather` copies
  the context into each branch, so parallel branches share one guard. No agent, workflow or
  `AgentSpec.create` signature changes. `execute_run` always sets the variable, also to `None`, so
  a village run can never inherit a guard.
- **Alternatives**: a `guard` field on `StepContext` means changing seven constructors and every
  `create` lambda. Wrapping `llm` and the tools would hide retries inside one span, which FR-014
  forbids.

## 3. Run states and reasons

- **Decision**: `RunStatus` gains `waiting_approval`, `over_budget`, `stopped` and `interrupted`.
  A new `runs.stop_reason` column holds the text, for example "model calls: 3 of 3".
- **The live states** are `running` and `waiting_approval`. `WS /runs/{id}/stream` keeps a run open
  in both, and sends a new `run_status` event on each change.
- **Rationale**: `Record<Run["status"], …>` in the frontend makes `tsc` find every place that shows
  a state. The village only compares with `completed`, so it is unaffected.

## 4. Counting budgets, also in parallel (Clarification 3)

- **Decision**: the guard counts in `steps`, on the event loop, without awaiting between the check
  and the count:
  - **Model and tool calls** count when they start. A call that would pass its limit raises
    `OverBudget` and never goes out.
  - **Tokens** add up when a call returns: `tokens_in + tokens_out`, a missing value counting as 0.
    `tokens_in` already includes cached prompt tokens (`llm/base.py`), so a token budget counts
    what was sent, not what was billed.
  - **The first limit reached stays**: once `OverBudget` is raised the guard is over budget for
    good, so every later step raises too.
- **The status comes from the guard**, not from the agent's outcome. This matters for
  `workflows/parallel.py`, which swallows failed reviews and may answer "all reviews failed", and
  for branches that end before they see the limit.
- **Answer on the way out**: the guard keeps the last model text, which becomes the run's answer
  when it ends over budget or stopped, so checks on the answer see what the run produced (spec,
  Edge Cases).
- **A needed fix**: `workflows/orchestrator.py:106` uses a plain `gather`. The probe confirmed the
  first error returns while the other branches keep running, past the end of the run. It gets
  `return_exceptions=True` and re-raises the first error, as `blocks/run.py` does.
- **No end span on this path**: like a provider error today, `OverBudget` ends the run through the
  open spans, each recording it as its error. `runs.stop_reason` carries the reason to the UI.

## 5. The time budget, and the clock during approvals (FR-019)

- **Decision**: `asyncio.timeout` around `agent.run`. A `TimeoutError` becomes `over_budget` only when
  the timeout's `expired()` says the budget caused it; one raised inside the agent stays a failure. While
  **any** call in the run waits for approval, the clock is paused with `reschedule(None)`; it
  resumes with the time that was left when the last wait ends.
- **Rationale**: the spec does not say what happens when one branch waits while another works.
  One rule covers both and is easy to explain: time spent with a question open to the owner does
  not count. The other limits still apply to the working branch, so a paused clock cannot run
  away. The cost is a branch working for free during a wait, at most 10 minutes per request.
- **Alternatives**: counting only when every branch waits needs tracking each branch for a rare
  case.
- **Retry waits**: a wait longer than the time left ends the run as over budget at once (User
  Story 3, scenario 4).

## 6. Stopping a run (FR-012)

- **Decision**: `task.cancel()`, with a "stop requested" mark on the guard. `execute_run` catches
  `CancelledError`, and ends the run as `stopped` when the mark is set; otherwise it re-raises, as a
  server shutdown needs.
- **Rationale**: the probe shows cancellation reaches every branch at once, so 2 seconds is easily
  met. Open spans record the cancellation through the tracer. `call_tool` sets the tool span's
  error to "stopped; the tool's answer was not awaited" (spec, Edge Cases). A late stdio answer is
  dropped, since `Stdio.send` removes its future in a `finally`.
- **Which runs**: a registry of live lab runs (`harness/live.py`) holds each task and guard. The
  village never registers, so stopping one of its runs answers 409. An evaluation's attempt can be
  stopped too; it then counts as an error (FR-004).

## 7. Retries (FR-013, FR-014)

- **Decision**: a subclass `PassingLLMError(LLMError)` carrying an optional `wait_hint`. Both clients
  raise it for:
  - any `httpx.TransportError` (timeouts, dropped and refused connections);
  - HTTP 408, 429, 500, 502, 503, 504 and 529, except a 429 whose body says `insufficient_quota`,
    which waiting will not fix.
- **Everything else stays a plain `LLMError`**, including a declined request and an unreadable
  answer. The error text does not change, so existing tests and messages hold.
- **The loop is in `steps.chat`**, only with a guard. Each attempt is its own LLM span: the run's
  totals count it, its failure and wait are on it (`lab.retry.*`), and the existing `came_from`
  repeats on the same declared edge.
- **Waits**: 2 s, then 8 s. The provider's `retry-after-ms` or `retry-after` (seconds) replaces them,
  up to 30 s. A date in `retry-after` is ignored, and the schedule applies. No jitter: attempts run
  one at a time, so nothing stampedes, and tests stay exact.
- **Tests** inject the sleep through the guard, so no test waits.

## 8. Approvals (FR-015 to FR-021)

- **Decision**: in `steps.call_tool`, after the arguments parse and before the tool span, a tool in
  `ask_first` goes through `guard.approve(...)`. Each decision gets its own span:
  - kind `step`, name `approval <tool>`, on the tool's node with its `lab.came_from`;
  - `lab.approval.decision` (`approved`, `denied`, `timed_out`) and `lab.approval.by` (`owner`,
    `timeout`, `case`).
- **A denied call has an approval span and no tool span.** So `totals.tool_calls`, the "tool was
  called" check and SC-005 all read the same fact: a tool span means the tool was called.
- **The denial text is the result**: "denied by the owner", then ": <reason>" if there is one; "denied
  by the owner: no answer from the owner" on a timeout; "denied by the test case" in an evaluation.
  `call_tool` returns it where a tool's result goes, so the model and tool blocks need no change.
- **Pending requests live in memory** (`harness/approvals.py`), as futures. A restart ends the run as
  interrupted, so no request has to survive one (FR-022).
- **In order**: ReAct and the model-call block await tool calls one by one, so requests of one model
  answer come one at a time (scenario 5). Parallel branches can each have one open.
- **The budget is checked again after an approval**, so a run that went over during the wait ends as
  over budget and the call stays unsent (spec, Edge Cases). A call counts against the tool call
  limit only when it goes out.
- **`POST /approvals/{id}` checks `Origin`** like `/mcp`, since it lets a tool run, and ids are
  random. Arguments are redacted before they are shown.
- **Showing them from any page** (FR-018): `GET /approvals`, polled every 2 s by the page. A socket
  is not worth it for one owner on loopback.

## 9. Evaluations

- **Attempts are ordinary runs**: `new_run` and `execute_run`, tagged with the existing `eval_id`.
  That also keeps hundreds of attempts out of the run list, which shows the latest 100.
- **The copy** (FR-003a): the validated config object and the cases stay in the evaluation's task,
  so attempts never read the agent again. A redacted copy is stored for the record. Evaluations do
  not resume, so nothing needs to rebuild them.
- **The chosen model** replaces the config's: `validate_config(template, {**stored, model, provider})`.
  Agents have one model per run, so there is nothing else to override. It changes the config version,
  as a model change does today, so a comparison of two models shows two versions.
- **Refused attempts**: tools are resolved per attempt. `ToolsUnavailable` records an error attempt
  with no run.
- **Outcome and rates** are pure functions (`evaluation/results.py`) over stored attempts, following
  FR-004 and FR-004a exactly.
- **One at a time**: the evaluation runs in one task. Starting another answers 409.
- **The agent is deleted during its evaluation**: refused with 409, since its results are about to
  be deleted with it (spec, Edge Cases). The spec does not cover this case.
- **Deleting an agent** deletes its cases, evaluations and attempts, plus the attempts' runs and
  spans, which no list shows any more. Other runs stay, as today.

## 10. The judge (FR-005)

- **Decision**: each judge call is its own run with `agent_id` `judge`, `eval_id` set, and a small
  static graph (`start → judge → end`), through `steps.decide` with a schema allowing only `yes` or
  `no`. `steps.decide` raising `DecisionError` or a provider error makes the check an error.
- **Rationale**: a judge span inside the attempt's run would have no node in the agent's graph
  (contract 2), and would add to the attempt's totals and budget. A separate run gets tracing,
  redaction and a link for free, and the attempt's averages stay about the agent.
- **Guard**: retries on, no budget. Judge runs are not attempts, and are left out of the averages.
- **Empty answers**: a judge check on a run with no answer fails without a model call.

## 11. Example cases (Clarification 2)

- **Decision**: `evaluation/examples.py` holds at least two cases per template, in code, with ids
  such as `example-react-1`. They are read-only, and their ids stay stable so comparisons can match
  them. A changed example shows as changed.
- **New agents**: `POST /agents` takes `cases_from`, the id of the template or agent it came from.
  The server copies those cases under new ids. Without it, the agent starts with no cases. "Open as
  blocks" passes the source's id too; its checks read answers and tools, which a block copy keeps.
- **A template's own cases** are not copied, only its examples.
- **Tests** run every example against a scripted `FakeLLM` (FR-009). SC-007 runs the ReAct examples on
  a real model too, so their checks ask for stable facts: `391` and the `calculator` tool, not exact
  wording.

## 12. New agents and budgets (FR-010)

- **Decision**: `POST /agents` fills in the default budget when the field is absent, and an explicit
  `null` means none. `PUT /agents/{id}` leaves it alone when absent, so older clients and tests lose
  nothing. The village creates agents through the store and gets none (FR-023).
- **Copies keep their source's budget and ask-first tools**, also no budget: a large old agent is the
  reason budgets are opt-in. A new agent from a template has no source budget, so it gets the default.
- **Unsaved drafts must not turn a template's `null` into "no budget"**: `draftFrom` leaves `budget`
  unset for a template, so the save omits it and the server fills in the default. `GET /blocks/new`
  and `GET /agents/{template}/blocks` answer with the default budget, and
  `GET /agents/{saved agent}/blocks` with that agent's budget and ask-first tools. These block drafts
  have no id of their own, so the page passes the source's id as `cases_from`.
- **`ask_first` is pruned on save** to the config's current tools, using `config_tools`.
- **Limits in one place**: `harness/budget.py`, served by `GET /budget-limits`, so the frontend repeats
  no numbers.

## 13. The checks

- **Pydantic discriminated union** (`evaluation/model.py`), as blocks do. An invalid pattern is refused
  on save (422, spec Edge Cases), with patterns at most 500 characters.
- **Pure function of the run and its spans**, except the judge: `tool_called` reads tool spans, cost
  checks read `totals`, `end_state` reads the status.
- **A provider reports no tokens** (some local servers): a token budget simply never trips, and a token
  check is an **error** ("the provider reported no tokens"), not a pass.
- **Patterns** come from the owner, run with `re.search` on one answer, and are a local risk only.

## 14. The village warning (FR-008, Clarification 5)

- **Decision**: `GET /evaluations/notice?provider=…` answers whether the village is running on that
  provider, reading the provider of the villagers' and shared agents through `resolve`. The server
  knows which agents the village uses, so the frontend does not guess from the default model.
- It warns and never blocks. Nothing in the village changes.

## 15. Left out

- **An overall spending cap, or a worst-case total on the start page**: the owner was asked and did not
  ask for either. One evaluation can reach 100 million tokens at the default budget (500 × 200,000), or
  1 billion with budgets at their maximum, plus judge calls. Stop is the only brake. Adding a total
  later is a small change to the start page.
- **The default numbers** stay as the spec has them: the default budget, 2 retries, 30 s, 10 minutes,
  50 cases and 10 attempts. The checklist listed them to confirm; they were not raised in clarify.
- **Live evaluation progress over a socket**: the page polls while one runs.
