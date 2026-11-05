---
description: "Task list for M17 — The Evaluation Harness"
---

# Tasks: M17 — The Evaluation Harness

**Input**: `specs/017-evaluation-harness/` (plan.md, spec.md, research.md, data-model.md,
contracts/interfaces.md, quickstart.md)

**Tests**: required by the constitution (every requirement maps to a test; see "Requirement → test"
at the end) and by the spec's independent tests. `FakeLLM`, `httpx.MockTransport`, the in-process lab
server and the notes server only. The failing test is written first.

**Gate**: a phase is done only when `make check` passes (check its exit code); commit after each
phase, with a short message. Read `frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **No new dependency**, and no agent framework (constitution).
- **Configs stay as they are.** No config model gains a field. No config version, graph or golden
  file changes (research §1); `UPDATE_GOLDEN` is not used.
- **The village is untouched** (FR-023). Its `execute_run` gets no guard, so `steps` behaves as today.
- **The owner's database.** Before editing `store.py` or running against it, stop `make dev` or back up
  `backend/data/agent_lab.db` (AGENTS.md). Tests use `tmp_path` or `:memory:` stores only.
- **Spans.** Every model and tool call stays inside `Tracer.span`, through `steps`. Every span's
  `node_id` is a declared node, and each `lab.came_from` pair a declared edge; check with
  `assert_trace_valid`.
- **Secrets.** Shown arguments, stored reasons and the evaluation's config copy go through `redact`
  with the run's secrets.
- **Waits in tests.** `RunGuard` takes the sleep as a parameter; no test really waits for a retry or an
  approval timeout.
- **Module size.** New modules stay under 300 lines; routes go in `api_harness.py` and
  `api_evaluations.py`, not `api.py`.

---

## Phase 1: Setup

- [X] T001 Create backend/src/agent_lab/harness/__init__.py (naming budget, guard, approvals, live) and
  backend/src/agent_lab/evaluation/__init__.py (naming model, checks, judge, results, examples,
  runner), each with only a module docstring.
  - Run `make check` first and note the baseline. It was 1,167 backend and 117 frontend tests at
    `0d19842`, and later commits only touched specs. A failure here is reported, not fixed in this
    milestone.

---

## Phase 2: Foundational

Every story needs these. No budget, retry or approval applies yet, and existing runs behave as before.

- [X] T002 Run states and new columns in backend/src/agent_lab/store.py, tests in
  backend/tests/test_store.py (data-model.md, "Run: changed", "Agent: changed").
  - `RunStatus` adds `waiting_approval`, `over_budget`, `stopped` and `interrupted`. Add
    `LIVE_STATUSES = ("running", "waiting_approval")`.
  - Columns added in place: `runs.stop_reason` (text, nullable), `runs.harness` (JSON, nullable),
    `agents.harness` (JSON, nullable).
  - `Run` gains `stop_reason` and `harness`. `CustomAgent` gains `harness: dict | None`, stored as raw
    JSON, and `create_agent` and `update_agent` take it, default `None`, so the village's calls are
    unchanged.
  - `finish_run(..., stop_reason=None)`; `set_run_status(run_id, status)`.
  - `mark_interrupted() -> list[str]`: live runs where `village_tick IS NULL` become `interrupted`, with
    `ended_at` set; returns their ids.
  - Tests: a database made before M17 opens and keeps its rows; `copy_agents_from` still works; village
    runs are left alone by `mark_interrupted`.

- [X] T003 [P] `Budget`, `Harness` and `OverBudget` in backend/src/agent_lab/harness/budget.py, tests in
  backend/tests/test_budget.py (data-model.md, "Budget").
  - `Budget`: `model_calls` default 30, range 1–200; `tokens` default 200,000, range 1–2,000,000;
    `tool_calls` default 30, range 1–200; `seconds` default 600, range 1–3,600. "All four are required
    in a budget. Unknown fields are refused."
  - `DEFAULT_BUDGET`, `MAX_BUDGET`. `Harness`: `budget: Budget | None`, `ask_first: list[str]`.
  - `OverBudget(Exception)` with `reason`, formatted `model calls: 3 of 3`, `tokens: 205,120 of 200,000`,
    `tool calls: 30 of 30`, `time: 600 s of 600 s`.

- [X] T004 `RunGuard` and live runs in backend/src/agent_lab/harness/guard.py and
  backend/src/agent_lab/harness/live.py, tests in backend/tests/test_stop.py.
  - `current_guard: ContextVar[RunGuard | None]`, default `None`.
  - `RunGuard(harness, *, sleep=asyncio.sleep)`: for now `stop_requested`, `last_text` and
    `after_model_call(response)` keeping the last non-empty model text. Later stories add the rest.
  - `LiveRuns`: `add(run_id, task, guard)`, `remove(run_id)`, and `stop(run_id) -> bool`, which sets
    `stop_requested` and cancels the task, False when the id is not live.

- [X] T005 `execute_run(guard=None)` in backend/src/agent_lab/runs.py and the model override in `new_run`,
  tests in backend/tests/test_stop.py (research §6, §9).
  - `execute_run` sets `current_guard` to its guard, also to `None`, and resets it in a `finally`.
  - It catches `CancelledError`: with `guard.stop_requested`, it finishes the run as `stopped`, with the
    guard's `last_text` as the answer and `stop_reason` "stopped by the owner", calls
    `current_task().uncancel()` and publishes `run_ended`; otherwise it re-raises.
  - Split `new_run` so a caller can start from an already validated config, name and client (an
    evaluation's copy). Add `model: ModelRef | None`, replacing the config's with
    `validate_config(template, {**stored, model, provider})`, and `eval_id` keeps its meaning.
  - In backend/src/agent_lab/agents/steps.py, `chat` calls `guard.after_model_call(response)` when a guard
    is set.
  - In `call_tool`, a cancelled tool call sets the span's error to "stopped; the tool's answer was not
    awaited".
  - Tests: stopping a run across parallel branches within 2 s with its spans kept; a stop during a tool
    call; a plain cancellation with no stop mark re-raises; no guard behaves as before.

- [X] T006 The stream and the lab's start in backend/src/agent_lab/api.py, tests in
  backend/tests/test_interrupted.py and backend/tests/test_api.py (contracts "Stream events").
  - `WS /runs/{id}/stream` keeps open for `LIVE_STATUSES`, and sends
    `{"type": "run_status", "run_id", "status"}` in the snapshot of a waiting run.
  - The lifespan calls `store.mark_interrupted()` before the host starts (FR-022).
  - Tests: an orphaned running run shows as interrupted after a start; a village run does not; a
    `TestClient` used without `with` still works.

- [X] T007 [P] Run states in the view: frontend/src/lib/api.ts, frontend/src/lib/run-state.ts,
  frontend/src/components/RunList.tsx and frontend/src/components/RunViewer.tsx, tests in
  frontend/src/lib/run-state.test.ts.
  - `RunStatus` grows; `Run` gains `stop_reason` and `harness`. `STATUS_TEXT`: "Waiting for approval", "Over
    budget", "Stopped", "Interrupted". `STATUS_DOT`: waiting uses `bg-signal`; the rest `bg-fault`.
  - `isLive(status)`; `RunView` gains `status`, and `applyEvent` handles `run_status` without touching
    `run`, so `onEnded` still fires only at the end.
  - `RunViewer` uses `view.run?.status ?? view.status ?? initial.status`, and shows `stop_reason`.
  - `RunList` shows `waiting_approval` with spaces: replace every `_`, not only the first.

**Checkpoint**: `make check` passes; nothing a user sees has changed unless a run was orphaned.

---

## Phase 3: User Story 1 — Test cases and pass rates (Priority: P1) 🎯 MVP

**Goal**: the owner writes cases for an agent, runs them, sees pass rates, and compares evaluations.

**Independent Test**: give a saved agent two cases and run them three times with a scripted fake model
whose answers pass one case and fail the other. The results show 100% and 0%, the failed check and its
reason, and a link to each run.

- [X] T008 [P] [US1] Cases and checks as data in backend/src/agent_lab/evaluation/model.py, tests in
  backend/tests/test_evaluation_checks.py (data-model.md, "Test case", "Check").
  - `Check`, a union on `kind`: `contains` and `not_contains` (`text`, 1–500), `matches` (`pattern`, 1–500,
    "must compile": an invalid pattern is refused with its reason), `tool_called` and `tool_not_called`
    (`tool`, a config name), `end_state` (`state`, a finished run state), `max_model_calls` and `max_tokens`
    (`limit` ≥ 1), `judge` (`question`, 1–500, optional `model`).
  - `CaseFields`: `name` 1–80 characters, `prompt` 1–4,000 characters, `checks` 1–10, `approvals`
    `approve` or `deny`, default `deny`. Unknown fields are refused.
  - `Case` adds `case_id`, `agent_id` and `read_only`. `Evaluation`, `Attempt`, `CheckResult`.

- [X] T009 [US1] Running checks in backend/src/agent_lab/evaluation/checks.py, tests in
  backend/tests/test_evaluation_checks.py (data-model.md, "Check"; research §13).
  - `run_check(check, run, spans) -> CheckResult` for all kinds but `judge`, pure.
  - A missing answer reads as empty, "so `contains` fails and `not_contains` passes". Tool checks read tool
    spans by `gen_ai.tool.name`.
  - `max_tokens` is an **error** ("the provider reported no tokens") when any LLM span has no tokens.
  - A result's `reason` says what it expected and what the run did.

- [X] T010 [P] [US1] Outcomes, rates and comparison in backend/src/agent_lab/evaluation/results.py, tests in
  backend/tests/test_evaluation_results.py (FR-004, FR-004a, FR-006, FR-007).
  - `attempt_outcome(run, results)`, in FR-004's order:
    1. **error**: no run (refused), or the run ended `error` or `stopped`;
    2. **fail**: any other end than `completed`, unless an `end_state` check expects that state;
    3. **fail**: any check failed;
    4. **error**: any check is an error;
    5. **pass** otherwise.
  - `summarize(attempts)`: per case and overall `passed`, `failed`, `errors`, `pass_rate` (passed ÷ attempts
    that are not errors; `None` when all are errors; overall pools the attempts) and averages over attempts
    with a run.
  - `fingerprint(case)`: a hash of the prompt, checks and approvals, not the name.
  - `compare(earlier, later)`: per case `new`, `removed`, `changed`, `up`, `down`, `same` or `no_rate`, as in
    data-model.md, plus both sides' config version, budget and model.

- [X] T011 [P] [US1] The judge in backend/src/agent_lab/evaluation/judge.py, tests in
  backend/tests/test_evaluation_judge.py (research §10; contracts "Trace").
  - `judge(question, answer, *, model, eval_id, ...) -> CheckResult`: its own run with `agent_id` `judge`, the
    graph `start → judge → end`, `steps.invoke` and `steps.decide` with `answer: Literal["yes", "no"]`, and a
    guard with no budget.
  - A provider failure or an answer that is neither yes nor no is an **error**. `no` fails. An empty answer
    fails with no model call. The result carries `judge_run_id`.
  - Tests: the call is traced and valid against the graph; it adds nothing to the attempt's totals; a judge
    run stays out of `GET /runs`.

- [X] T012 [P] [US1] Example cases in backend/src/agent_lab/evaluation/examples.py, tests in
  backend/tests/test_evaluation_examples.py (FR-009; research §11).
  - At least two cases for each of the six templates, with fixed ids such as `example-react-1`, as data.
  - ReAct, also used on the real model (SC-007): "What is 17 times 23?" (`contains` 391, `tool_called`
    `calculator`, `end_state` completed) and the weather in Berlin (`tool_called` `get_weather`, `end_state`
    completed). Other templates check stable facts, such as the routing template's `calculator` route with
    `1000`, and the parallel template's 4 model calls. No check asks for exact wording.
  - Tests: every example passes with a scripted `FakeLLM` through the real agent, in the style of
    `test_templates.py`.

- [X] T013 [US1] Tables in backend/src/agent_lab/store_evaluations.py as the mixin `EvaluationTables` of
  `Store`, deletion in backend/src/agent_lab/store.py, tests in backend/tests/test_store.py
  (data-model.md, "Test case", "Evaluation", "Attempt", "Deleting").
  - Tables `eval_cases`, `evaluations` and `eval_attempts`, with indexes on `agent_id`, plus `runs(eval_id)`.
  - `eval_cases`: `name` "unique per agent ignoring case"; "At most 50 cases per agent, counting a template's
    examples" is enforced in T015.
  - `mark_evaluations_interrupted()`.
  - `delete_agent` also deletes its cases, evaluations and attempts, and the runs and spans with those
    evaluations' `eval_id`. Its other runs stay, as today.

- [X] T014 [US1] The evaluation task in backend/src/agent_lab/evaluation/runner.py, tests in
  backend/tests/test_evaluation_runner.py (FR-003, FR-003a, FR-008, FR-022; research §9).
  - `Evaluations(store, models, host, bus, secrets, live)`.
  - `start(agent_id, repeats, case_ids, model) -> Evaluation`: refuses a second evaluation (`repeats` 1–10;
    only one may be `running`), an unavailable model, and an unknown case. It takes the copy: validated config,
    cases with fingerprints, harness (`default_budget` true when the agent has no budget), and a redacted config
    for the record. The agent is not read again.
  - The task runs attempts one by one, each case `repeats` times. Each attempt: resolve tools (`ToolsUnavailable`
    records an error attempt with no run), `new_run` with `eval_id` and the copy, `execute_run` with a guard and
    registered in `live`, the checks and judges, then the stored attempt with its totals.
  - `stop(eval_id)`: starts no further attempt, stops the running one, state `stopped`, finished attempts kept.
  - States `running → finished | stopped`; the lab's start marks `interrupted`.
  - Tests: the independent test above; editing the agent and a case mid-evaluation changes nothing; stopping keeps
    attempts; a second start is refused; an unavailable tool is an error, not a fail; every attempt's run is
    stored, traced and absent from `GET /runs`.

- [X] T015 [US1] Routes in backend/src/agent_lab/api_evaluations.py, wired in backend/src/agent_lab/api.py, tests in
  backend/tests/test_evaluation_api.py (contracts "Test cases", "Evaluations").
  - `GET` and `POST /agents/{id}/cases` (409 at 50), `PUT` and `DELETE /cases/{id}` (409 for an example), with a
    template's examples listed first as `read_only: true`.
  - `POST /agents/{id}/evaluations`, `GET /agents/{id}/evaluations`, `GET /evaluations/{id}`,
    `POST /evaluations/{id}/stop`, `GET /evaluations/compare` (422 across agents).
  - `GET /evaluations/notice?provider=`: `{"village_shares_provider": bool}`, from `Village.providers()`, added in
    backend/src/agent_lab/village/runner.py: the providers of its agents through `resolve`, when it is running.
  - `POST /agents` takes `cases_from` (a template's examples or a saved agent's cases, under new ids).
    `DELETE /agents/{id}` answers 409 during that agent's evaluation. The lifespan marks evaluations interrupted.

- [X] T016 [P] [US1] View logic in frontend/src/lib/evaluation.ts and calls in frontend/src/lib/api.ts, tests in
  frontend/src/lib/evaluation.test.ts.
  - Check labels, `blankCheck(kind)`, the case form's rules before sending, `rateText` (none when `null`, with the
    error count), `changeText`, and which failed checks to show for an attempt.

- [X] T017 [US1] Components in frontend/src/components/evaluation/EvaluationPanel.tsx, CaseForm.tsx,
  EvaluationResults.tsx and EvaluationCompare.tsx.
  - `EvaluationPanel`: the agent's cases (examples read-only), its evaluations, and the start form with repeats, a
    choice of cases and a model picker from `modelOptions`. Includes the notice from `GET /evaluations/notice`, warning
    "that they share its rate limits and that the village could lose turns or pause itself" (FR-008), which never
    blocks starting.
  - `EvaluationResults`: per case the rate, errors and failed checks with reasons and run links; overall the rate,
    averages, config version, model and budget, marked when default. Polls every 2 s while running, with Stop.
  - `EvaluationCompare`: per case both rates and the change, plus both versions, budgets and models.

- [X] T018 [US1] The switch in frontend/src/app/page.tsx and copying cases in frontend/src/lib/builder.ts, tests in
  frontend/src/lib/builder.test.ts.
  - A Build / Evaluate switch for a listed agent in the main area. An unsaved draft cannot be evaluated. An attempt's
    run link opens it in `RunViewer`.
  - `Draft` gains `casesFrom`: `draftFrom` sets it from `source.id`. `openBlocks(fromId)` sets it to `fromId`, since a
    block draft has no id of its own (research §12). `draftFields` sends it on create.

**Checkpoint**: US1 works alone. Attempts record their default budget, but nothing enforces it until US2.

---

## Phase 4: User Story 2 — Budgets and stopping a run (Priority: P2)

**Goal**: a run cannot pass its budget, and the owner can stop any lab run.

**Independent Test**: give an agent a budget of 3 model calls and a scripted fake model that keeps calling tools. The
run stops after 3 model calls as over budget, and the trace shows 3 model calls and the reason.

- [X] T019 [US2] Counting in backend/src/agent_lab/harness/guard.py, tests in backend/tests/test_budget.py (FR-011;
  research §4).
  - `before_model_call()` and `before_tool_call()` count on start and raise `OverBudget` if the call would pass its
    limit; no await between check and count. `after_model_call` adds `tokens_in + tokens_out`, missing as 0.
  - Before each step, tokens at or past the limit raise too. The first reason reached stays: later calls raise it again.

- [X] T020 [US2] Consulting the guard in backend/src/agent_lab/agents/steps.py and the fix in
  backend/src/agent_lab/workflows/orchestrator.py, tests in backend/tests/test_budget.py and
  backend/tests/test_workflow_orchestrator.py.
  - `chat` calls `before_model_call` before its span; `call_tool` calls `before_tool_call` before its span.
  - `orchestrator.py:106`: `gather(return_exceptions=True)`, re-raising the first error after all finish, as
    `blocks/run.py` does.
  - Tests for each template and a block agent: the limit is never passed. With parallel branches and a limit below their
    number, the extra calls never go out, those under way finish and appear, and then the run ends. `parallel.py`, which
    swallows failed reviews, still ends as `over_budget`. Golden tests are unchanged.

- [X] T021 [US2] Ending over budget in backend/src/agent_lab/runs.py, with the clock in
  backend/src/agent_lab/harness/guard.py, tests in backend/tests/test_budget.py (research §4, §5).
  - `execute_run` wraps the agent in `asyncio.timeout(budget.seconds)` when there is a budget and binds it to the guard.
    `pause_clock()` and `resume_clock()` use `reschedule`, counting open waits.
  - **The guard's state decides the status first**: over budget, whatever the agent returned. A `TimeoutError` counts as
    the time budget only when the timeout's `expired()` is true; any other stays a failure.
  - The answer is the guard's `last_text`, and `stop_reason` the `OverBudget` reason.
  - Tests: scenarios 1–3 and 5 of User Story 2; an inner `TimeoutError` is not a time budget; no budget runs as before.

- [X] T022 [US2] Budgets through the API in backend/src/agent_lab/api.py, and Stop and limits in
  backend/src/agent_lab/api_harness.py, tests in backend/tests/test_agents_api.py and backend/tests/test_stop.py (FR-010,
  FR-012; research §12; contracts "Budgets and ask-first tools").
  - `AgentInfo` gains `budget` and `ask_first`. `POST /agents`: absent budget means the default, `null` means none. `PUT`:
    absent means unchanged. Use `model_fields_set` to tell them apart.
  - `GET /blocks/new` and `GET /agents/{template}/blocks` answer with the default budget; `GET /agents/{saved agent}/blocks`
    with that agent's budget and ask-first tools.
  - `start_run` builds a guard from the agent's harness, snapshots it in `runs.harness`, and registers the run in `LiveRuns`,
    removing it when done. Templates get a guard with no budget.
  - `POST /runs/{id}/stop` answers 202 and the run, or 409 for a finished or village run. `GET /budget-limits`.
  - Tests: which budget each way of making an agent starts with; agents the village creates have none; an older agent keeps
    none; a stored-agent update without the field keeps it.

- [X] T023 [US2] Budgets in evaluations in backend/src/agent_lab/evaluation/runner.py, tests in
  backend/tests/test_evaluation_runner.py (FR-003a; Clarification 1).
  - Each attempt's guard uses the copy's budget, or the default when the agent has none, with the agent itself unchanged.
  - Tests: such an attempt fails as over budget with a reason naming the default; a check expecting `over_budget` makes it
    pass; a judge's call does not count (FR-005); results mark the default.

- [X] T024 [US2] Budgets and Stop on the page in frontend/src/components/builder/BudgetFields.tsx,
  frontend/src/components/builder/AgentSettings.tsx, frontend/src/components/RunViewer.tsx and frontend/src/lib/builder.ts,
  tests in frontend/src/lib/builder.test.ts.
  - `BudgetFields`: add, change or remove a budget, with defaults and limits from `GET /budget-limits`, read-only for
    templates.
  - `Draft` gains `budget`. `draftFrom` copies a saved agent's, including none, and leaves a template's unset so the save omits
    it. `draftFromAgent` keeps it. `draftFields` omits it when unset.
  - `RunViewer`: a Stop button while live, for runs with no `village_tick`.

**Checkpoint**: US1 and US2 work together, and evaluations can no longer overspend per attempt.

---

## Phase 5: User Story 3 — Retries on passing failures (Priority: P3)

**Goal**: a passing provider failure does not end the run.

**Independent Test**: a fake provider answers "rate limited" twice, then normally. The run completes, and its trace shows the
two failed attempts with their reasons and waits.

- [X] T025 [P] [US3] `PassingLLMError` in backend/src/agent_lab/llm/base.py, backend/src/agent_lab/llm/openai_compat.py and
  backend/src/agent_lab/llm/anthropic.py, tests in backend/tests/test_retries.py (research §7).
  - Raised for any `httpx.TransportError`, and HTTP 408, 429, 500, 502, 503, 504 and 529, except a 429 whose body says
    `insufficient_quota`. Everything else stays a plain `LLMError`, and the text does not change.
  - `wait_hint` from `retry-after-ms`, else `retry-after` in seconds; a date is ignored.
  - Tests with `MockTransport` for both clients: each status, a timeout, a dropped connection, hints, a wrong key (401), a refused
    request (400) and an unknown model.

- [X] T026 [US3] The retry loop in backend/src/agent_lab/agents/steps.py and `retry_wait` in
  backend/src/agent_lab/harness/guard.py, tests in backend/tests/test_retries.py (FR-013, FR-014).
  - With a guard, `chat` tries up to 3 times, with one LLM span per attempt, each counted by `before_model_call`. A retried
    attempt's span carries `lab.retry.attempt`, `lab.retry.reason` and `lab.retry.wait_s`.
  - Waits of 2 s, then 8 s; a hint replaces them, up to 30 s. `retry_wait` raises `OverBudget` when the wait passes the time left.
  - Tests: all four scenarios of User Story 3; a retry at the model call limit ends over budget; `decide` retries too; no guard
    means no retry; a run's totals count every attempt.

- [X] T027 [P] [US3] Showing attempts in frontend/src/lib/run-state.ts and frontend/src/components/SpanDetail.tsx, tests in
  frontend/src/lib/run-state.test.ts.
  - `spanFacts(span)`: today's facts, plus "Attempt" and "Waited before the next try" when `lab.retry.*` is set. `SpanDetail` shows
    no attributes today, so without this the wait stays invisible (FR-014).

- [X] T028 [US3] The village stays as it was, in backend/tests/test_village_runner.py (FR-023).
  - A village turn with a provider failing with `PassingLLMError` once: no retry, no guard, and the failure counts as it does today.
    `test_pauses_after_three_failed_steps` still passes.

**Checkpoint**: an evaluation no longer loses attempts to a passing rate limit.

---

## Phase 6: User Story 4 — Approvals before tool calls (Priority: P4)

**Goal**: a tool marked ask first is never called without an approval.

**Independent Test**: mark `notes/write_note` as ask first and run an agent whose scripted fake model calls it. The run waits; denying
it gives the model the denial as the tool's result; a second run that is approved writes the note.

- [X] T029 [P] [US4] Pending requests in backend/src/agent_lab/harness/approvals.py, tests in backend/tests/test_approvals.py
  (data-model.md, "Approval request"; research §8).
  - `Approvals`: `ask(...)` awaits a future, with `asked_at` and `expires_at` 10 minutes apart, and removes it in a `finally`;
    `open()`, oldest first; `answer(id, approve, reason) -> bool`.
  - Deciders: `OwnerDecider(approvals, run)` and `CaseDecider(setting)`, which answers at once. Each returns a decision with `by`
    (`owner`, `timeout`, `case`).
  - No answer in time: denied, reason "no answer from the owner", `by` `timeout`.

- [X] T030 [US4] Asking first in backend/src/agent_lab/agents/steps.py and backend/src/agent_lab/harness/guard.py, tests in
  backend/tests/test_approvals.py (FR-016, FR-017, FR-019, FR-021).
  - In `call_tool`, after the arguments parse and for a known tool in `ask_first`, before the tool span: an `approval <tool>` step span
    on the tool's node, with `lab.came_from`, redacted arguments as input, and the `lab.approval.*` attributes from the contract.
  - Denied: the text is the result, with no tool span: "denied by the owner", with ": <reason>" if given; "denied by the owner: no answer
    from the owner" on a timeout; "denied by the test case" in an evaluation.
  - The guard sets the run to `waiting_approval` while any request is open, publishes `run_status`, and pauses the clock across the wait.
    Afterwards it checks the budget again, so a run over budget ends and the call stays unsent.
  - Tests: all six scenarios of User Story 4 but the page's; a block agent's tool block; two calls decided in order; a wait longer than the
    time budget (FR-019); a Stop during a wait; a denied call counted by no tool span; `assert_trace_valid`.

- [X] T031 [US4] Marking tools and answering in backend/src/agent_lab/api.py and backend/src/agent_lab/api_harness.py, tests in
  backend/tests/test_approvals.py and backend/tests/test_agents_api.py (FR-015; contracts "Approvals").
  - `ask_first` on `POST` and `PUT /agents`: absent on `PUT` means unchanged; pruned on save to `config_tools`.
  - `start_run`'s guard gets `OwnerDecider`.
  - `GET /approvals`. `POST /approvals/{id}` with `decision` `approve` or `deny` and optional `reason`, at most 500 characters: 204; 404 if no
    longer open; **403 for a foreign `Origin`**, as `/mcp` does.
  - Tests: arguments are redacted, including a servers-file secret; a restart leaves no tool call to go out (FR-022).

- [X] T032 [US4] Cases decide in backend/src/agent_lab/evaluation/runner.py, tests in backend/tests/test_evaluation_runner.py (FR-020).
  - Each attempt's guard gets `CaseDecider(case.approvals)`.
  - Tests: deny, the default, leaves the tool uncalled and marks the span `by` `case`; approve calls it; a saved agent's ask-first tools come from
    the copy.

- [X] T033 [P] [US4] Approvals on the page in frontend/src/lib/use-approvals.ts, frontend/src/components/ApprovalsBanner.tsx,
  frontend/src/components/ApprovalCard.tsx, frontend/src/components/RunViewer.tsx, frontend/src/app/page.tsx and
  frontend/src/lib/run-state.ts, tests in frontend/src/lib/run-state.test.ts.
  - `useApprovals` polls `GET /approvals` every 2 s. `ApprovalsBanner` shows on all three views (FR-018), and opens the waiting run, switching to
    Agents; page.tsx has three separate returns, so add it to each.
  - `ApprovalCard`, in `RunViewer` for that run's requests: the tool, arguments, a reason box, Approve and Deny.
  - `spanFacts` adds "Decision" and "Decided by" from `lab.approval.*` (FR-021).

- [X] T034 [P] [US4] Ask-first choices in frontend/src/components/builder/AgentSettings.tsx and frontend/src/lib/builder.ts, tests in
  frontend/src/lib/builder.test.ts.
  - `Draft` gains `askFirst`, copied like `budget`. `draftTools(draft)` lists the tools of a ReAct, routing or block config, in any block depth.
  - One checkbox per tool, read-only for templates.

**Checkpoint**: all four stories work together.

---

## Phase 7: Polish & cross-cutting

- [X] T035 [P] Documentation in docs/evaluations.md (new), docs/agents.md, docs/api.md, docs/development.md, README.md and AGENTS.md.
  - docs/evaluations.md: cases, checks, examples, reading results and comparisons, budgets, retries, approvals, and what an evaluation can cost.
  - docs/api.md: the new routes, and the `run_status` event. docs/agents.md: the new run states and spans.
  - README.md: the milestone, and what comes after it.
  - AGENTS.md: the `harness/` and `evaluation/` packages, the new routes modules, and "Current feature: `specs/017-evaluation-harness/`", plus
    contract 5's budget and approval rules.

- [X] T036 [P] Timing in specs/017-evaluation-harness/quickstart.md under "Results", measured once with a short script in the scratchpad: reading a
  500-attempt evaluation's results (under 1 s), and stopping a run (under 2 s).

- [X] T037 Review against the requirements in specs/017-evaluation-harness/tasks.md: every row of "Requirement → test" names a test that exists and
  passes; `git diff` shows no change to `backend/tests/golden/templates.json`; `make check` passes, and its exit code is 0.

- [ ] T038 Manual checks 1–7 of specs/017-evaluation-harness/quickstart.md on `anthropic/claude-haiku-5-5` (SC-002, SC-006, SC-007); record results in
  quickstart.md. Commit "M17 manual check results".
  - **Spends the owner's money**, and needs `ANTHROPIC_API_KEY`. Ask the owner before running it. Use a scratch database and backend, as in M16's checks,
    so the owner's village stays untouched. Any check not run is recorded as not run, with why.

---

## Dependencies

- **Phase 1 → Phase 2 → stories.**
- **US1** needs Phase 2. T009 needs T008; T010, T011 and T012 need T008; T013 needs T008; T014 needs T009–T013; T015 needs T014; T016 needs T015's
  contract; T017 needs T016; T018 needs T017.
- **US2** needs Phase 2. T019 → T020 → T021 → T022. T023 needs T014 and T021. T024 needs T022.
- **US3** needs Phase 2 and T019. T025 → T026. T027 needs only T007. T028 needs T026.
- **US4** needs Phase 2, T020, T021 and T022. T029 → T030 → T031. T032 needs T014 and T030. T033 needs T031. T034 needs T024.
- **Polish** after the stories it covers. T038 last.

## Parallel examples

- **Phase 2**: T003 and T007 alongside T002 (different files).
- **US1**: after T008, T010, T011 and T012 together; T016 while T014 and T015 are built, from the contract.
- **US3**: T025 and T027 together.
- **US4**: T029 and T033 together, from the contract; T034 alongside them once T024 is done.
- **Across stories**: US3 and US4 can run in parallel after T022, except for edits to `steps.py` (T026, T030), which go one at a time.

## Implementation strategy

- **MVP**: Phases 1–3. The owner can measure any agent and compare two evaluations. Stop and check the independent test, SC-006 with the fake model and
  SC-001. Until US2, an attempt's budget is recorded and not enforced, so run it only on a scripted or local model.
- **Then** US2 (limits and Stop), US3 (retries), US4 (approvals), each a commit with `make check` green.
- **Last** docs, timing and the manual checks.

## Requirement → test

| Requirement | Test |
|---|---|
| FR-001 | test_evaluation_checks.py (limits), test_evaluation_api.py (create, edit, delete, 50 cases) |
| FR-002 | test_evaluation_checks.py (every kind) |
| FR-003 | test_evaluation_runner.py (repeats, chosen cases, chosen model, runs stored) |
| FR-003a | test_evaluation_runner.py (edits during an evaluation; the default budget) |
| FR-004, FR-004a | test_evaluation_results.py (the order; rates; pooled) |
| FR-005 | test_evaluation_judge.py (traced, its own model, outside the budget) |
| FR-006 | test_evaluation_results.py, test_evaluation_api.py (kept until the agent is deleted), evaluation.test.ts |
| FR-007 | test_evaluation_results.py (every `change`), test_evaluation_api.py |
| FR-008 | test_evaluation_runner.py (stop, one at a time), test_evaluation_api.py (notice) |
| FR-009 | test_evaluation_examples.py, test_evaluation_api.py (read-only, copied), builder.test.ts |
| FR-010 | test_budget.py (limits), test_agents_api.py (how each agent starts) |
| FR-011 | test_budget.py (each limit, parallel, time) |
| FR-012 | test_stop.py |
| FR-013 | test_retries.py (the failure table, waits, hints, the cap) |
| FR-014 | test_retries.py (one span per attempt, counted), run-state.test.ts |
| FR-015 | test_agents_api.py (`ask_first`, pruned), builder.test.ts |
| FR-016, FR-017 | test_approvals.py (waits, approve, deny, tool blocks) |
| FR-018 | test_approvals.py (`GET /approvals`), manual check 4 |
| FR-019 | test_approvals.py (a wait longer than the budget) |
| FR-020 | test_evaluation_runner.py (the case decides, marked) |
| FR-021 | test_approvals.py (spans of each decider), run-state.test.ts |
| FR-022 | test_interrupted.py, test_evaluation_runner.py, test_approvals.py |
| FR-023 | test_village_runner.py, test_interrupted.py, test_agents_api.py |
| SC-001 | the existing suite, test_templates.py unchanged |
| SC-002, SC-006, SC-007 | manual checks 1, 2 and 5; test_evaluation_results.py for comparison |
| SC-003 | test_budget.py, test_stop.py |
| SC-004 | test_retries.py |
| SC-005 | test_approvals.py, test_evaluation_runner.py |
