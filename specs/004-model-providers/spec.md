# Feature Specification: M4 — Model Providers and Per-Agent Model Choice

**Feature Branch**: `main` (feature directory `004-model-providers`)

**Created**: 2026-10-31

**Status**: Draft

**Input**: Agent Lab milestone M4: switch, in the UI, between the local model (vLLM serving
`qwen3.5-9b`) and OpenAI API models the owner configures; the model is chosen per agent, stored
with it and recorded on every run so runs on different models can be compared.

## Context

M1–M3 run every agent on one model taken from the environment: the local vLLM server. M3 let
the owner build custom agents from six templates. To learn how much an agent's behavior depends
on the model, the owner now wants to run the same agent on different models, including hosted
OpenAI models (for example a GPT model such as "gpt 6 luna", whatever the owner configures).

A **provider** is a model server: the local OpenAI-compatible server (no key) and OpenAI (an API
key from `.env`). Each provider offers a configured list of model ids. One model is the
**default**. A custom agent picks one of the configured models; templates run on the default.

All M1–M3 core contracts apply unchanged: every model and tool call is a span on a node of the
run's graph; graphs and `config_version` come from the server; secrets are redacted; servers bind
to 127.0.0.1; tests never call a real model.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, a senior engineer studying agent behavior on a local machine.

### User Story 1 - Run a custom agent on a hosted model (Priority: P1)

The owner opens a custom agent, picks an OpenAI model from the model list in its agent settings,
saves and runs it. The run behaves like any other: live graph, waterfall, totals, replay. The
run header, span details and past-runs list show which model answered.

**Why this priority**: running an agent on another model is the whole point of the milestone.

**Independent Test**: with the OpenAI provider configured and its HTTP calls answered by a mock
transport, a custom routing agent set to an OpenAI model sends its requests to the OpenAI
endpoint with that model id and the key, the run completes, and the run records the model.

**Acceptance Scenarios**:

1. **Given** the OpenAI provider is configured with a key, **When** the owner opens a custom
   agent's settings, **Then** the model list shows the local models and the OpenAI models, the
   current one selected, and OpenAI models marked as external.
2. **Given** a custom agent set to an OpenAI model, **When** the owner runs it, **Then** every
   model call of the run goes to OpenAI with that model, and the run header and each model span
   show the model.
3. **Given** two runs of the same agent on two different models, **When** the owner looks at
   the past-runs list, **Then** each entry shows its model next to its totals, and the two runs
   have different `config_version`s.
4. **Given** a template, **When** the owner runs it, **Then** it uses the default model, as
   before M4.

---

### User Story 2 - Workflows behave the same on every provider (Priority: P2)

Thinking off, JSON-schema structured output and native tool calling work on both providers, so
every template shape (routing decisions, plans, verdicts, tool calls) runs on an OpenAI model as
it does locally.

**Why this priority**: a model switch is only useful if the workflows keep working; provider
quirks must not leak into the agents.

**Independent Test**: for each provider, recorded requests (mock transport) show the provider's
own way of turning thinking off, the JSON schema for decisions and the tool declarations, and no
parameter the provider does not accept.

**Acceptance Scenarios**:

1. **Given** an agent with reasoning off on the local provider, **When** it calls the model,
   **Then** the request turns thinking off the way the local server expects, as in M3.
2. **Given** the same agent on OpenAI, **When** it calls the model, **Then** the request turns
   thinking off the OpenAI way and contains no parameter only the local server understands.
3. **Given** a routing or orchestrator agent on OpenAI, **When** it decides, **Then** the
   decision is requested as JSON-schema structured output and validated as in M2.
4. **Given** a ReAct agent on OpenAI, **When** the model calls tools, **Then** the tool calls
   run and are traced exactly as locally.

---

### User Story 3 - Failures and unavailable models are clear (Priority: P3)

A provider without its key cannot be chosen; a provider that fails during a run ends the run
with a readable error; secrets never show up anywhere.

**Why this priority**: hosted providers add new failure modes (missing key, rate limits, outages)
and a secret that must stay out of traces.

**Independent Test**: scripted transports return 401, 429 and 500 and time out; each run ends
`error` with the provider's message on the span; no stored or streamed span contains the key.

**Acceptance Scenarios**:

1. **Given** no OpenAI key is configured, **When** the owner opens the model list, **Then** the
   OpenAI models are shown as unavailable ("no API key") and cannot be selected or saved.
2. **Given** a custom agent whose model became unavailable (key removed, model removed from the
   configuration), **When** the owner opens or runs it, **Then** the builder shows the model as
   unavailable and starting a run is rejected with a message naming the model.
3. **Given** OpenAI answers a model call with a rate-limit or server error, **When** the run
   continues, **Then** the model span records the provider's error, the run ends `error`, and
   the next run can start immediately.
4. **Given** any run on OpenAI, **When** its spans are stored and streamed, **Then** neither the
   API key nor the authorization header appears in them, and the key never reaches the browser.

### Edge Cases

- The same model id is configured on two providers → the model list shows both, each with its
  provider; an agent stores provider and model together, so the choice is unambiguous.
- The default model is changed in the configuration → template runs use the new default and get
  a new `config_version`; earlier runs keep theirs.
- The local server is down → a run on a local model fails with a connection error on the span,
  as today; the model list does not probe servers.
- A model does not support a feature a workflow needs (e.g. no tool calling) → the provider's
  error is recorded on the span and the run ends `error`; M4 does not keep a capability table.
- An agent with reasoning on runs on OpenAI → the provider's default reasoning behavior is used;
  reasoning text appears in spans only when the provider returns it.
- Very slow hosted responses → the existing per-request timeout applies and ends the run `error`.
- An M1–M3 database → existing runs list and replay; their stored config already names their
  model.

## Requirements *(mandatory)*

### Functional Requirements

**Providers and models**

- **FR-001**: The system MUST support several providers configured in the environment: the local
  OpenAI-compatible server and OpenAI, each with a base URL, an optional API key and a list of
  model ids; exactly one configured model MUST be the default. The M3 environment settings MUST
  keep working unchanged as the configuration of the local provider and its default model.
- **FR-002**: The API MUST list the configured models with provider, model id, whether the
  provider is external (not on this machine), whether it is available (key present when the
  provider needs one), and which one is the default; it MUST never return API keys.
- **FR-003**: Model calls MUST go to the agent's provider with the agent's model id; one server
  process MUST serve runs on different providers at the same time.

**Per-agent model choice**

- **FR-004**: Each custom agent MUST have a model setting (provider and model id) chosen from the
  configured models; new custom agents start with the default model; templates MUST run with the
  default model.
- **FR-005**: The server MUST reject saving an agent with a model that is not configured or not
  available, naming the field; it MUST reject starting a run of an agent whose model is no longer
  configured or available, naming the model.
- **FR-006**: The model MUST be part of every run's stored configuration and of its
  `config_version`.

**Provider differences**

- **FR-007**: Turning thinking off MUST use each provider's own request setting; a request MUST
  NOT contain parameters the target provider does not accept.
- **FR-008**: JSON-schema structured output for decisions and native tool calling MUST work on
  both providers with unchanged validation and tracing (M2 decision rules, M1 tool spans).
- **FR-009**: Requests of the six templates on the default (local) model MUST stay exactly as in
  M3 (golden test unchanged).

**UI**

- **FR-010**: The builder's agent settings MUST offer the model as a list grouped by provider,
  external models marked, unavailable models shown but not selectable, with the reason.
- **FR-011**: The run header, the model spans' details and the past-runs list MUST show each
  run's model.

**Failures and secrets**

- **FR-012**: A provider error during a run (missing or rejected key, rate limit, server error,
  timeout, connection failure) MUST be recorded on the model span with the provider's message
  and end the run `error`; it MUST NOT hang the run or affect other runs.
- **FR-013**: Every configured API key MUST be redacted from stored and streamed spans and run
  data; keys and authorization headers MUST NOT be sent to the browser.
- **FR-014**: Runs stored by M1–M3 MUST still list and replay.

**Quality**

- **FR-015**: Tests MUST use the scripted fake model or mock HTTP transports only; they MUST cover
  per-provider request shapes (thinking off, structured output, tools, no foreign parameters),
  model selection and validation, unavailable providers, provider errors and redaction.
- **FR-016**: All quality gates (`make check`) MUST pass; every requirement maps to a test or an
  explicit manual check in `tasks.md`.

### Key Entities

- **Provider**: name, base URL, API key (environment only, never exposed), whether it is
  external, whether it is available, and its model ids.
- **Model choice**: provider name and model id; the default is one of the configured choices.
- **Custom agent**: as in M3, plus its model choice.
- **Run**: as in M3; its configuration snapshot includes the model choice.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can switch a custom agent from the local model to an OpenAI model and
  start a run in under 30 seconds.
- **SC-002**: Each of the six template shapes completes its sample prompt on a configured OpenAI
  model (manual check with a real key).
- **SC-003**: For every provider, 100% of recorded test requests contain only parameters that
  provider accepts.
- **SC-004**: In 100% of tested failure cases (401, 429, 500, timeout, connection refused), the
  run ends `error` within the request timeout and the error names the cause.
- **SC-005**: No stored or streamed span, run or API response in the test suite contains a
  configured API key.
- **SC-006**: Any two runs can be compared by model, calls, tokens and wall time from the
  past-runs list without opening either.

## Future Scope (not planned in M4)

- **M5 Composable block builder**: agents built from nested blocks (LLM call, tool call, code
  check, router, parallel group, loop); templates become starting layouts.
- **M6 MCP**, **M7 Harness** (budgets, retries, approvals), **M8 Agent memory**, **M9 RAG**,
  **Phase 2 Village**.
- Per-node model choice, a per-run model override, cost tracking, an Anthropic adapter (the
  provider seam stays ready for it), streaming responses, discovering models from the provider.

## Assumptions

- The model list is configured, not fetched from the providers; the owner adds model ids such as
  an OpenAI GPT model to the configuration.
- Availability means "key present when needed"; servers are not probed. A wrong key or an
  unknown model id shows up as a run error.
- Templates stay read-only and run on the default model; to run a template's shape on another
  model, the owner customizes a copy (one click) and picks the model.
- Choosing an external model sends that agent's prompts and tool results to the provider; the
  marking in the model list is the owner's reminder, there is no extra confirmation.
- No retries or fallbacks on provider errors; budgets and retries arrive with the harness (M7).
- One API key per provider, from `.env`; `.env` stays out of git.
