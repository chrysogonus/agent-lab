# Implementation Plan: M17 — The Evaluation Harness

**Branch**: `main` (feature directory `017-evaluation-harness`) | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-evaluation-harness/spec.md`

## Summary

Two new packages, and a small change at the one place every call already passes through.

1. **The harness** (`harness/`): a `RunGuard` holds one run's budget, ask-first tools and counts.
   `execute_run` sets it for lab runs, and `steps.chat` and `steps.call_tool` consult it:
   - budgets count calls as they start, and tokens as they return;
   - `steps.chat` retries passing failures, with each attempt its own span;
   - `steps.call_tool` asks for approval first, with each decision its own span;
   - `asyncio.timeout` is the time budget, and `task.cancel` is Stop.
2. **Evaluations** (`evaluation/`): cases, checks, a judge, and a task that runs attempts one by one as
   ordinary runs, then computes outcomes, rates and comparisons.
3. **The village is untouched**: with no guard, `steps` behaves exactly as today.

Budgets and ask-first tools sit beside the agent's config, not in it, so no existing config version
changes ([research.md](research.md) §1).

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged. `re`, `hashlib`, `asyncio` and the existing `httpx` and `pydantic`
  cover everything.
- **Storage**: SQLite, in place: new tables `eval_cases`, `evaluations` and `eval_attempts`; new
  columns `agents.harness`, `runs.harness` and `runs.stop_reason` ([data-model.md](data-model.md)).
  Pending approvals and live runs stay in memory.
- **Testing**:
  - pytest with `FakeLLM`, and an injected sleep for retry waits;
  - `httpx.MockTransport` for each provider's failures and wait hints;
  - the in-process lab server and the notes server for ask-first tools;
  - vitest for the pure view logic.
- **Target Platform**: local (127.0.0.1)
- **Project Type**: web application
- **Performance Goals**: a run ends as stopped within 2 seconds (FR-012). The guard adds no await on
  the normal path. An evaluation's results read in under 1 s at its largest (500 attempts).
- **Constraints**:
  - existing configs, config versions, graphs and golden files unchanged (SC-001);
  - no change to village behaviour (FR-023);
  - tests never reach a real model;
  - existing error texts unchanged, since `PassingLLMError` keeps them;
  - the owner's database gains columns on first start, so back it up first (AGENTS.md).
- **Scale/Scope**: 50 cases per agent × 10 attempts, one evaluation at a time; up to 200 model calls in
  a run.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | No library and no framework. Each new module has one job and stays under 300 lines, and the new routes get their own modules instead of growing `api.py`. |
| II. Observable by default | Pass | Each model call attempt is an LLM span, each approval decision a step span, and each judge call a traced run. Spans stay on declared nodes. A run's reason is stored and streamed. |
| III. Secure local defaults | Pass | Still 127.0.0.1. `POST /approvals/{id}` checks `Origin`, since it lets a tool run. Shown arguments, stored reasons and the evaluation's config copy are redacted. Patterns compile on save and run only on the owner's own text. |
| IV. Smallest change | Pass | One guard at the existing choke point; no agent or workflow signature changes. No resume, no socket for progress, and no rule language. The orchestrator's one-line `gather` fix is needed by FR-011. |
| V. Gates + traceability | Pass | Every FR maps to tests with the fake model and fake transports. SC-002, SC-006 and SC-007 have manual checks. View logic goes in `lib/evaluation.ts` and `lib/run-state.ts`, with tests. |

Post-design re-check: all pass. Approvals add a way for a page to let a tool call through. It is
limited to the lab's own origins, needs a random id, and only ever lets through a call the agent's
tools already allow.

## Design

The rules behind each choice are in [research.md](research.md), and the shapes are in
[data-model.md](data-model.md) and [contracts/interfaces.md](contracts/interfaces.md).

### Backend: the harness

- `harness/budget.py`:
  - `Budget`, `DEFAULT_BUDGET` and `MAX_BUDGET`;
  - `Harness` (`budget`, `ask_first`): what an agent stores;
  - `OverBudget(reason)`.
- `harness/guard.py`: `RunGuard` and the `ContextVar` `current_guard`.
  - `before_model_call()`, `after_model_call(response)`, `before_tool_call()`: counting; the first
    limit reached stays reached;
  - `retry_wait(error, attempt) -> float | None`: how long to wait, `None` to give up; raises
    `OverBudget` past the time budget;
  - `pause_clock()` and `resume_clock()`, on a bound `asyncio.timeout`;
  - `last_text`, `over`, `stop_requested`;
  - an injected `sleep`.
- `harness/approvals.py`:
  - `Approvals`: `ask(...)`, `open()`, `answer(id, approve, reason)`, with the 10-minute timeout;
  - the deciders: the owner's (through `Approvals`) and a case's (immediately).
- `harness/live.py`: `LiveRuns`: `add`, `remove` and `stop(run_id)` for lab runs.
- `agents/steps.py`:
  - `chat`: asks the guard before each attempt, retries `PassingLLMError` with one span per attempt;
  - `call_tool`: after the arguments parse, an `approval <tool>` span for ask-first tools; a denied call
    returns the denial text with no tool span; a stopped call records that the answer was not awaited.
- `runs.py`:
  - `execute_run(guard=…)`: sets `current_guard`, wraps the agent in `asyncio.timeout`, and maps
    `OverBudget`, `TimeoutError` and a requested stop to their states, the guard's state first;
  - `new_run` splits so an evaluation can start from its copy, and takes a model override.
- `workflows/orchestrator.py`: `gather(return_exceptions=True)`, re-raising the first, as `blocks/run.py`.
- `llm/base.py`, `llm/openai_compat.py`, `llm/anthropic.py`: `PassingLLMError` with `wait_hint`.
- `store.py`:
  - `RunStatus`, the new columns, `set_run_status` and `mark_interrupted`;
  - `agents.harness` on read and write;
  - `delete_agent` also removes cases, evaluations and their runs.
- `store_evaluations.py`: `EvaluationTables`, a mixin of `Store` for the three new tables, so `store.py`
  stays readable.

### Backend: evaluations

- `evaluation/model.py`: `Check` (a union on `kind`), `Case`, `CaseFields`, `Evaluation` and `Attempt`.
- `evaluation/checks.py`: `run_check(check, run, spans) -> CheckResult`, pure, for all but the judge.
- `evaluation/judge.py`: the judge's run, graph and `yes`/`no` schema.
- `evaluation/results.py`, pure:
  - `attempt_outcome(run, check_results)`, in FR-004's order;
  - `summarize(attempts)`, following FR-004a;
  - `fingerprint(case)` and `compare(earlier, later)`.
- `evaluation/examples.py`: at least two cases for each of the six templates, as data.
- `evaluation/runner.py`: `Evaluations`:
  - `start(agent_id, repeats, case_ids, model)` takes the copy, refuses a second evaluation, and starts
    the task;
  - `stop(eval_id)` ends the running attempt and starts no more;
  - each attempt: a guard with the copy's budget and the case's approval setting, then `new_run`,
    `execute_run`, the checks, then the stored attempt.

### Backend: the API

- `api_harness.py`: `POST /runs/{id}/stop`, `GET /approvals`, `POST /approvals/{id}` and
  `GET /budget-limits`.
- `api_evaluations.py`: cases, evaluations, compare and notice.
- `api.py`:
  - lifespan marks interrupted runs and evaluations;
  - `AgentInfo`, `NewAgent` and `AgentFields` gain `budget`, `ask_first` and `cases_from`;
  - `start_run` builds the guard from the agent's harness and registers the run;
  - the run stream treats both live states as live, and sends `run_status`;
  - `delete_agent` answers 409 during that agent's evaluation.
- `village/runner.py`: `providers()`, for the notice. No behaviour changes.

### Frontend

- `lib/api.ts`: the new types and calls. `RunStatus` grows, so `tsc` finds every status table.
- `lib/run-state.ts` (+ test): `applyEvent` handles `run_status`; `RunView` gains `status`.
- `lib/builder.ts` (+ test): `Draft` gains `budget`, `askFirst` and `casesFrom`; `draftFrom` sets them;
  `draftTools(draft)` lists the tools the agent can mark.
- `lib/evaluation.ts` (+ test):
  - check labels, a blank check per kind, and the case form's rules;
  - rate and change text, and which check to show for a failed attempt.
- `lib/use-approvals.ts`: polls `GET /approvals` every 2 s.
- `components/ApprovalsBanner.tsx`: on all three views (FR-018); opens the waiting run.
- `components/ApprovalCard.tsx`: the tool, arguments, reason box, Approve and Deny.
- `components/RunViewer.tsx`: new states, a Stop button while live, `stop_reason`, and the approval
  card.
- `components/RunList.tsx`: new states, by `STATUS_DOT`.
- `components/builder/BudgetFields.tsx`: add, change or remove a budget, from `GET /budget-limits`.
- `components/builder/AgentSettings.tsx`: budget fields and ask-first choices.
- `components/evaluation/`:
  - `EvaluationPanel.tsx`: the agent's cases, evaluations and start form, beside the builder;
  - `CaseForm.tsx`, with one row per check;
  - `EvaluationResults.tsx`: rates, failed checks with reasons and run links, polled while running;
  - `EvaluationCompare.tsx`.
- `app/page.tsx`: a Build / Evaluate switch for a listed agent, the banner, and opening an attempt's run.

### Tests

- **Backend**:
  - `test_budget.py`: each limit, tokens over on one call, parallel branches, the time budget, retries
    against the budget, no budget;
  - `test_stop.py`: Stop within 2 s, during a tool call, across parallel branches, on village runs;
  - `test_retries.py`: the failure table with `MockTransport` for both clients, hints, the 30 s cap, one
    span per attempt, totals;
  - `test_approvals.py`: approve, deny, reason, timeout, several in order, a tool block, over budget during
    a wait, the clock, `Origin`;
  - `test_evaluation_checks.py`, `test_evaluation_results.py`: every kind and FR-004's order;
    pooled rates; compare;
  - `test_evaluation_runner.py`: the copy, stopping, one at a time, refused attempts, interrupted, default
    budget, case approvals;
  - `test_evaluation_judge.py`: traced, its own run, outside the budget, neither yes nor no;
  - `test_evaluation_examples.py`: every template's examples pass with a scripted model;
  - `test_evaluation_api.py`: routes, limits, read-only examples, copying cases, deleting an agent, notice;
  - `test_interrupted.py`: runs and evaluations at start; village runs left alone.
- **Existing tests**: unchanged, including `test_templates.py`, with the golden file and pinned config
  versions untouched.
- **FR-023**: a test runs a village turn with a provider failing once, and sees no retry and no guard.
- **Frontend**: `evaluation.test.ts`, and additions to `run-state.test.ts` and `builder.test.ts`.

## Requirement Map

| Requirements | Where |
|---|---|
| FR-001, FR-002 | `evaluation/model.py`, `checks.py`, `store_evaluations.py`, `CaseForm.tsx` |
| FR-003, FR-003a, FR-008 | `evaluation/runner.py`, `api_evaluations.py`, `EvaluationPanel.tsx` |
| FR-004, FR-004a, FR-006, FR-007 | `evaluation/results.py`, `EvaluationResults.tsx`, `EvaluationCompare.tsx` |
| FR-005 | `evaluation/judge.py` |
| FR-009 | `evaluation/examples.py`, `cases_from` on `POST /agents` |
| FR-010, FR-011 | `harness/budget.py`, `harness/guard.py`, `steps.py`, `runs.py`, `orchestrator.py`, `BudgetFields.tsx` |
| FR-012 | `harness/live.py`, `runs.py`, `api_harness.py`, `RunViewer.tsx` |
| FR-013, FR-014 | `llm/`, `steps.chat`, `guard.retry_wait` |
| FR-015 | `agents.harness`, `AgentSettings.tsx` |
| FR-016, FR-017, FR-019, FR-021 | `steps.call_tool`, `harness/approvals.py`, `guard.pause_clock`, `ApprovalCard.tsx` |
| FR-018 | `GET /approvals`, `use-approvals.ts`, `ApprovalsBanner.tsx` |
| FR-020 | the case's decider in `harness/approvals.py`, set by `evaluation/runner.py` |
| FR-022 | `store.mark_interrupted`, the lifespan in `api.py` |
| FR-023 | no guard for village runs; `test_interrupted.py` and the FR-023 test |

## Project Structure

```text
backend/src/agent_lab/harness/__init__.py, budget.py, guard.py, approvals.py, live.py (new)
backend/src/agent_lab/evaluation/__init__.py, model.py, checks.py, judge.py, results.py,
    examples.py, runner.py (new)
backend/src/agent_lab/api_harness.py, api_evaluations.py, store_evaluations.py (new)
backend/src/agent_lab/runs.py, store.py, api.py, agents/steps.py
backend/src/agent_lab/llm/base.py, openai_compat.py, anthropic.py
backend/src/agent_lab/workflows/orchestrator.py, village/runner.py
backend/tests/test_budget.py, test_stop.py, test_retries.py, test_approvals.py,
    test_evaluation_*.py, test_interrupted.py (new)
frontend/src/lib/api.ts, run-state.ts, builder.ts, evaluation.ts (+ test, new), use-approvals.ts (new)
frontend/src/components/ApprovalsBanner.tsx, ApprovalCard.tsx (new), RunViewer.tsx, RunList.tsx
frontend/src/components/builder/BudgetFields.tsx (new), AgentSettings.tsx
frontend/src/components/evaluation/ (new), frontend/src/app/page.tsx
README.md, docs/evaluations.md (new), docs/agents.md, docs/api.md, docs/development.md, AGENTS.md
```

**Structure Decision**:
- The harness knows nothing of evaluations, so a plain run with a budget and an evaluation's attempt
  take the same path.
- Agents and workflows see none of this: they keep calling `steps`.

## Complexity Tracking

| Addition | Why it is needed | Simpler option rejected because |
|---|---|---|
| A `ContextVar` for the guard | One run's limits must reach every `steps` call, across parallel branches | A field on `StepContext` changes seven constructors and every `create` lambda (research §2) |
| Budget and ask-first beside the config | They must not change config versions | Fields on the config models change every existing version and the pinned hashes (research §1) |
| Four more run states | Spec requires each to show and be checked; the village ignores them | Reusing `error` could not tell a limit from a failure, and FR-004 treats them differently |
