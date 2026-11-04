# Feature Specification: M17 — The Evaluation Harness

**Feature Branch**: `main` (feature directory `017-evaluation-harness`)

**Created**: 2026-11-04

**Status**: Draft

**Input**: The roadmap item after M16: "the evaluation harness for the lab's other agents
(budgets, retries, approvals)". The owner ran `/speckit-specify` with no further text after
this recommendation: measure saved agents against test cases, and give runs budgets,
retries and approval steps before tool calls.

## Context

The lab has six agent templates and a builder, and since M16 its agents can use tools from any
MCP server the owner lists. What the lab cannot do yet is say whether an agent is any good, or
keep a run from going wrong:

- **No measurement.** Whether an agent answers well is judged by running it by hand and reading
  the trace. After a change to a prompt, a block or the model, there is no way to tell whether
  it got better or worse. The village has had turn checks and scenarios with pass rates since
  M13; the lab's other agents have nothing like them.
- **No limits.** A run ends only when the agent finishes or hits its own loop limit (for
  example a ReAct agent's iteration limit). There is no cap on tokens, tool calls or time, and
  the owner cannot stop a run that has gone wrong.
- **No retries.** A model call that fails for a passing reason (a rate limit, a busy server, a
  dropped connection) ends the run with an error. On the hosted model this happens often enough
  to spoil a run of many cases.
- **No approvals.** Since M16 an agent can call tools with lasting effects, such as writing a
  note. Whatever the servers file grants is called without asking. The M16 spec deferred
  approvals to this milestone.

The roadmap has called the parts of this milestone "the harness" since M1: the code around an
agent that limits it, retries for it, asks the owner before it acts, and measures it.

All earlier contracts apply:
- every model call and every tool call is a traced step of a run;
- the automated tests use the scripted fake model and fake transports only; evaluations on the
  real model are run by the owner and are never part of the quality gates;
- no new dependency;
- the lab binds to 127.0.0.1 only, and secrets never reach a stored or shown trace;
- existing agents, builder configs and their runs keep working unchanged.

The village does not change in this milestone. Its turns keep running without budgets or
approvals, and its turn checks and scenarios stay as they are.

The roadmap after M17:
- M18 agent memory for the lab's other agents;
- M19 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who builds agents in the lab, changes their prompts, blocks,
tools and models, and wants to know whether a change helps.

### User Story 1 - Test cases and pass rates (Priority: P1)

For any agent (a template or a saved agent), the owner writes test cases. A case is a prompt and
one or more checks on what the run did. Checks can look at:
- **the answer's text**: it contains a phrase, does not contain one, or matches a pattern;
- **the tools**: a tool was called, or was not called;
- **the end**: the run ended in a given state, for example completed;
- **the cost**: the run used at most a number of model calls or tokens;
- **a judge**: a model is asked a yes-or-no question about the answer, for example "Does the
  answer give a temperature for Berlin?".

The owner runs an agent's cases, each a chosen number of times (1 to 10), on a chosen model. Each
attempt is an ordinary traced run. The results page shows:
- each case's pass rate, and for a failed attempt which check failed and why, with a link to its
  run;
- the overall pass rate;
- the average model calls, tokens and time per attempt;
- the agent's config version and the model used.

Results are kept. The owner can compare an evaluation with an earlier one of the same agent and
sees, per case, whether its pass rate went up, down or stayed the same.

**Why this priority**: measurement is what the lab is missing most. Without it, budgets,
retries and approvals cannot be judged either. It also mirrors what M13 gave the village, so the
owner already knows the idea.

**Independent Test**: give a saved agent two cases and run them three times with a scripted fake
model whose answers pass one case and fail the other. The results show 100% and 0%, the failed
check and its reason, and a link to each run.

**Acceptance Scenarios**:

1. **Given** an agent with cases, **When** the owner runs them 3 times each, **Then** every
   attempt is a stored, traced run, and the results show each case's pass rate and the overall
   one.
2. **Given** a failed attempt, **When** the owner opens the results, **Then** they see which
   check failed, what it expected and what the run did, and can open the attempt's run.
3. **Given** a case with a judge check, **When** it runs, **Then** the judge's call is traced, and
   its yes or no decides the check. An answer that is neither counts as an error, not a pass.
4. **Given** two evaluations of the same agent, one before and one after a prompt change,
   **When** the owner compares them, **Then** each case shows both pass rates and the change,
   along with both config versions.
5. **Given** an evaluation in progress, **When** the owner stops it, **Then** no further attempts
   start, the running attempt is stopped, and the finished attempts' results are kept and
   marked as a stopped evaluation.
6. **Given** a template, **When** the owner opens its cases, **Then** it comes with at least two
   example cases that pass with the scripted fake model's sample behaviour.

---

### User Story 2 - Budgets and stopping a run (Priority: P2)

An agent can have a budget: the most model calls, tokens, tool calls and time a run may use.
The owner sets it in the agent's settings. A new agent starts with the default budget filled
in; agents saved before this milestone, and the templates, have none and run as before, until
the owner gives them one. (A builder agent may have up to 30 blocks, loops and parallel
branches, so no fixed default is safe for every existing agent.) When a run uses up any part
of its budget, it stops before its next step, with the state "over budget" and a reason saying
which limit it reached. Its trace up to that point is kept.

The owner can stop any running run of a lab agent from its trace view. It ends with the state
"stopped", and its trace up to that point is kept.

**Why this priority**: an evaluation runs an agent many times on a hosted model that costs
money. A runaway agent must not be able to use more than the owner allows, and a run that has
gone wrong must be stoppable.

**Independent Test**: give an agent a budget of 3 model calls and a scripted fake model that keeps
calling tools. The run stops after 3 model calls as over budget, and the trace shows 3 model
calls and the reason.

**Acceptance Scenarios**:

1. **Given** an agent with a budget of 3 model calls, **When** its run would make a 4th call,
   **Then** the run ends as over budget before that call, saying "model calls: 3 of 3".
2. **Given** an agent with a token budget, **When** a model call takes the run past it, **Then**
   no further step starts, and the run ends as over budget with the tokens used.
3. **Given** a run that is waiting for a slow model answer, **When** its time budget runs out,
   **Then** the call is abandoned and the run ends as over budget.
4. **Given** a running run, **When** the owner presses Stop, **Then** the run ends as stopped
   within 2 seconds, and its trace shows every step taken until then.
5. **Given** an agent saved before this milestone, **When** it runs its sample prompt, **Then** it
   behaves as before: it has no budget, and nothing stops it early.

---

### User Story 3 - Retries on passing failures (Priority: P3)

When a model call fails for a passing reason (the provider says it is rate limited or busy, the
call times out, or the connection drops), the lab waits and tries again, up to 2 more times.
Each wait is longer than the last. When the provider says how long to wait, the lab waits that
long, up to a limit. Each attempt is visible in the trace. A failure that will not pass by
waiting (a refused request, a wrong key, an unknown model) is not retried.

**Why this priority**: on the hosted model, a single rate limit can end one run in an
evaluation of thirty. Retries make pass rates measure the agent instead of the provider's mood.

**Independent Test**: a fake provider answers "rate limited" twice, then normally. The run
completes, and its trace shows the two failed attempts with their reasons and waits.

**Acceptance Scenarios**:

1. **Given** a provider that is busy twice and then answers, **When** an agent runs, **Then** the
   run completes, and the model step shows 3 attempts.
2. **Given** a provider that refuses a request as invalid, **When** an agent runs, **Then** the
   run ends with the error at once, without retrying.
3. **Given** a provider that is busy on every attempt, **When** an agent runs, **Then** the run
   ends with an error after 3 attempts, saying the provider was busy.
4. **Given** a retry wait that would go past the run's time budget, **When** it comes, **Then**
   the run ends as over budget instead of waiting.

---

### User Story 4 - Approvals before tool calls (Priority: P4)

In an agent's settings, the owner marks tools as "ask first". Before such a tool is called,
whoever calls it (the model, or a builder agent's tool block), the run pauses in the state
"waiting for approval". The trace view shows the tool and the arguments, and the owner either:
- **approves**, and the call goes out as usual; or
- **denies**, optionally with a reason. The denial (and the reason) becomes the tool's result,
  just as a tool error does today: the model receives it, or a tool block passes it on as its
  output. The run goes on.

A request that gets no answer within 10 minutes is denied, with the reason "no answer from the
owner". The time spent waiting does not count against the run's time budget.

In an evaluation nobody is watching, so each case says what to do with approval requests:
approve them or deny them. The default is deny. The trace marks each such decision as made by
the case, not by the owner.

**Why this priority**: tools with lasting effects arrived in M16. Asking first lets the owner try
an agent with such tools without trusting it fully. It is last because it is the only part that
needs the owner at the screen during a run.

**Independent Test**: mark `notes/write_note` as ask first and run an agent whose scripted fake
model calls it. The run waits; denying it gives the model the denial as the tool's result; a
second run that is approved writes the note.

**Acceptance Scenarios**:

1. **Given** a tool marked ask first, **When** the model calls it, **Then** the run waits, and the
   tool is not called until the owner approves.
2. **Given** a waiting run, **When** the owner denies with the reason "not now", **Then** the
   model's next call contains the tool result "denied by the owner: not now", and the run goes
   on.
3. **Given** a waiting run whose trace view is not open, **When** the owner opens the lab,
   **Then** they can see that a run is waiting for approval and go to it.
4. **Given** an evaluation case that says deny, **When** its agent calls a tool marked ask first,
   **Then** the tool is not called, and the trace marks the denial as the case's.
5. **Given** a model answer with two calls to tools marked ask first, **When** the run reaches
   them, **Then** the owner decides each call separately, in order.
6. **Given** a builder agent with a tool block for a tool marked ask first, **When** the run
   reaches the block, **Then** it waits for the owner. If denied, the tool is not called, and the
   block's output is the denial text, which the next block receives.

### Edge Cases

- **The agent or a case is edited during an evaluation**: the evaluation goes on with the copy
  it took at its start (FR-003a); the edit applies from the next evaluation.
- **The agent changes between evaluations**: every result records the config version it ran
  with. A comparison shows both versions, and still compares cases that exist in both.
- **A case is added, changed or removed between evaluations**: a comparison shows the case as
  new, changed or removed instead of comparing pass rates of different cases.
- **A case's tool is unavailable**: when the run is refused because a server is not connected,
  the attempt counts as an error, not a fail, and the results say so. Errors are counted
  separately from fails and are left out of the pass rate.
- **The judge fails**: when the judge's model call fails or answers neither yes nor no, the check
  counts as an error for that attempt.
- **An attempt goes over budget**: it fails unless one of its checks expects that end (FR-004).
  Checks on the answer see whatever the run produced until then.
- **Every attempt of a case is an error**: the case shows no pass rate, only its errors, and adds
  nothing to the overall pass rate.
- **The model for an evaluation is unavailable**: the evaluation does not start, and says why.
- **The lab stops during an evaluation**: when the lab starts again, the evaluation shows as
  interrupted with the results it had; it does not resume.
- **The lab stops while a run waits for approval**: when the lab starts again, the run shows as
  interrupted. No tool call goes out.
- **Two evaluations at once**: only one evaluation runs at a time. Starting another while one
  runs is refused with a reason.
- **A run is already over budget when an approval comes**: the approval is ignored, and the run
  ends as over budget.
- **Stop during a tool call**: the run ends as stopped. An answer that arrives later is ignored.
  The tool may still have done its work, and the trace says the answer was not awaited.
- **Retries and budgets**: every attempt counts as a model call, and its tokens count, if the
  provider reports them.
- **An agent is deleted**: its cases and evaluation results are deleted with it.
- **A pattern check with an invalid pattern**: refused when the case is saved, with the reason.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The owner MUST be able to create, edit and delete test cases for any agent: a name,
  a prompt, one or more checks, and what to do with approval requests (approve or deny; default
  deny). An agent MAY have at most 50 cases, and a case at most 10 checks.
- **FR-002**: Checks MUST include: the answer contains a text, does not contain a text, or
  matches a pattern; a tool was called or was not called; the run ended in a given state; the
  run used at most a number of model calls or tokens; a judge model answers yes to a question
  about the answer.
- **FR-003**: The owner MUST be able to run an agent's cases (all or a chosen set), each 1 to 10
  times, on a chosen model. Each attempt MUST be an ordinary traced run of the agent, stored like
  any other run and marked as part of the evaluation.
- **FR-003a**: When an evaluation starts, it MUST take a copy of the agent's config (with its
  budget and ask-first tools), the chosen cases and the model. Every attempt MUST use that copy,
  so that editing the agent or a case while the evaluation runs changes only later
  evaluations.
- **FR-004**: Every check of every attempt MUST end as pass, fail or error, with a reason for a
  fail or an error. An attempt's outcome MUST be decided in this order:
  1. **error**, when the run was refused before its first step (for example a tool server not
     connected), ended with a provider error, or was stopped by the owner;
  2. **fail**, when the run ended in any other state than completed (over budget, out of
     iterations or rounds), unless one of the case's checks expects that end state;
  3. **fail**, when any check fails;
  4. **error**, when any check is an error;
  5. **pass** otherwise.
- **FR-004a**: A case's pass rate MUST be its passed attempts divided by its attempts that are not
  errors. A case whose attempts are all errors MUST show no pass rate, only its error count. The
  overall pass rate MUST pool the attempts of all cases the same way (passed attempts divided by
  attempts that are not errors), not average the cases' rates.
- **FR-005**: A judge check's model call MUST be traced, on the evaluation's model unless the case
  names another, and MUST NOT count against the agent's budget.
- **FR-006**: An evaluation's results MUST show per case its pass rate, errors and failed checks
  with reasons and run links, and overall the pass rate, the average model calls, tokens and
  time per attempt, the config version and the model. Results MUST be kept until the agent is
  deleted.
- **FR-007**: The owner MUST be able to compare two evaluations of the same agent, case by case,
  with cases that exist in only one of them, or changed between them, shown as such.
- **FR-008**: The owner MUST be able to stop an evaluation. Finished attempts MUST be kept. Only
  one evaluation MAY run at a time.
- **FR-009**: Each template MUST come with at least two example cases that pass with the scripted
  fake model's sample behaviour.
- **FR-010**: The owner MUST be able to give any saved lab agent a budget of model calls,
  tokens, tool calls and time per run, in its settings, and to change or remove it. A new agent
  MUST start with the default budget: 30 model calls, 200,000 tokens, 30 tool calls and 10
  minutes. An agent without a budget MUST run as before. Each limit MAY be raised to 200 model
  calls, 2,000,000 tokens, 200 tool calls and 60 minutes.
- **FR-011**: A run that has used up any part of its budget MUST start no further step and MUST
  end in the state "over budget", with the limit reached and the amount used. A step in progress
  when the time budget runs out MUST be abandoned.
- **FR-012**: The owner MUST be able to stop a running run of a lab agent. It MUST end in the
  state "stopped" within 2 seconds, with its trace kept.
- **FR-013**: A model call that fails because the provider is rate limited or busy, times out, or
  loses the connection MUST be retried up to 2 more times, waiting longer before each retry and
  honouring the provider's own wait hint up to 30 seconds. Other failures MUST NOT be retried.
- **FR-014**: Every attempt of a model call, failed or not, MUST be visible in the run's trace
  with its reason and wait, and MUST count against the budget.
- **FR-015**: The owner MUST be able to mark any of an agent's tools as "ask first" in the agent's
  settings.
- **FR-016**: Before any call of a tool marked ask first goes out, whether the model or a tool
  block makes it, the run MUST pause in the state "waiting for approval", and MUST show the
  tool and its arguments (with secrets redacted) to the owner.
- **FR-017**: An approval MUST send the call as usual. A denial MUST NOT call the tool; the
  tool's result MUST be "denied by the owner", with the owner's reason if given, and it MUST go
  where the tool's result would go (to the model, or as a tool block's output). The run MUST go
  on. A request with
  no answer within 10 minutes MUST be denied with the reason "no answer from the owner".
- **FR-018**: The lab MUST show the owner every run waiting for approval, from any page.
- **FR-019**: Time spent waiting for approval MUST NOT count against the run's time budget.
- **FR-020**: In an evaluation, approval requests MUST be decided by the case's setting, and the
  trace MUST record the decision as the case's.
- **FR-021**: Each approval decision (by the owner, by timeout or by a case) MUST be part of the
  run's trace.
- **FR-022**: Runs and evaluations that were in progress when the lab stopped MUST show as
  interrupted when it starts again. No waiting tool call MAY go out after a restart.
- **FR-023**: The village's turns MUST behave as before: no budgets, retries or approvals apply
  to them in this milestone.

### Key Entities

- **Test case**: belongs to one agent. A name, a prompt, its checks, and what to do with approval
  requests.
- **Check**: one condition on an attempt: its kind (answer text, tools, end state, cost, judge)
  and what it expects.
- **Evaluation**: one run of an agent's cases: the agent and its config version, a copy of the
  config and the cases as they were at its start, the model, the repeat count, when it started
  and ended, and its state (running, finished, stopped, interrupted).
- **Attempt**: one run of one case in an evaluation: the run, and each check's result (pass, fail
  or error) with its reason.
- **Budget**: an agent's limits per run: model calls, tokens, tool calls and time.
- **Approval request**: a paused tool call in a run: the tool, the arguments, and the decision
  (approved, denied, timed out) with who made it and the reason.
- **Model call attempt**: one try of a model call: its result or the failure's reason, and the
  wait before the next try.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every existing agent template and saved builder agent runs its sample prompt
  unchanged. The existing test suite passes.
- **SC-002**: The owner can write three cases for a saved agent and see their pass rates on the
  real model within 10 minutes, without leaving the lab's pages.
- **SC-003**: No run makes a model call or a tool call after its budget is used up (100% of runs
  in the tests). A run stopped by the owner shows as stopped within 2 seconds.
- **SC-004**: With a provider that fails for a passing reason twice before answering, 100% of
  runs complete, and every failed attempt appears in the trace.
- **SC-005**: No tool marked ask first is ever called without an approval by the owner or by an
  evaluation case (100% in the tests).
- **SC-006**: After changing an agent, the owner can see which cases got better or worse by
  comparing two evaluations, without opening any single run.
- **SC-007**: On the real model, an evaluation of the ReAct template's example cases with 5
  attempts each finishes without a run ending in a provider error (manual check).

## Assumptions

- **Scope**: the milestone covers all four parts named on the roadmap: test cases with pass
  rates, budgets, retries and approvals. Context compaction, which an early roadmap listed under
  the harness, belongs with agent memory (M18).
- **Lab agents only**: the six templates and the owner's saved agents. The village keeps its own
  checks and scenarios from M13 and gets no budgets or approvals yet.
- **Cases live in the lab**: cases are written and edited on the agent's pages and stored with
  the lab's data, not in files in the repo. The templates' example cases ship with the lab.
- **Evaluations run in the lab**: started and watched from the lab's pages. Unlike the village's
  checks, no command line is needed.
- **One at a time**: an evaluation runs its attempts one after another, and only one evaluation
  runs at a time. This keeps the hosted model within its rate limits and keeps the results easy
  to read.
- **Budgets are opt-in for existing agents**: existing agents are already bounded by their own
  loop limits (iterations, rounds, items), but a large builder agent can need more than any
  fixed default allows. So only new agents start with a budget; the owner adds one to an older
  agent when wanted.
- **Budgets are checked between steps**: a single model call can take a run past its token
  budget, since the tokens are known only after the call. The run then stops before the next
  step. Time is the only limit that ends a step in progress.
- **Retries cover model calls only**: tool errors already reach the model as the tool's result,
  and the model decides what to do. A tool server that went away is reconnected from the Tools
  page, as in M16.
- **Approval is per tool, per agent**: there is no rule language (for example by argument
  value). The servers file still decides which tools exist at all.
- **Judge**: a judge check asks a plain yes-or-no question. Scores, rubrics and comparing two
  answers are out of scope.
- **Model for manual checks**: the hosted model the owner named (`openai/gpt-6-luna`) until the
  local model is back. Its tool calls need reasoning off.
