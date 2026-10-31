---
description: "Task list for M4 — Model Providers and Per-Agent Model Choice"
---

# Tasks: M4 — Model Providers and Per-Agent Model Choice

**Input**: `specs/004-model-providers/` (plan.md, spec.md, research.md, data-model.md,
contracts/http-api.md, quickstart.md)

**Tests**: requested by the spec (FR-015, SC-003–SC-005); every FR maps to a test or manual
check (see Traceability). Tests use `FakeLLM` or `httpx.MockTransport` only, never a real
provider.

**Gate**: a phase is done only when `make check` passes; commit after each phase. Read
`frontend/AGENTS.md` before any frontend task (Next.js 16). Visual work on the model select uses
the frontend-design skill, keeping the M3 identity.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 / US2 / US3 from spec.md

## Conventions used by every task

- Local requests, template graphs and template `config_version`s stay exactly as in M3:
  backend/tests/golden/templates.json is never regenerated in M4 (FR-009).
- A config's `provider` is left out of its JSON when it is `"local"` (research §1); "no
  `provider` key" always means Local, in stored agents, run configs and the UI.
- A model reference is the pair `{provider, model}`; provider names are `local` and `openai`,
  labels `Local` and `OpenAI`.
- API keys and provider base URLs never appear in an API response, span, run or stream event.
- Every rejection is `422 {"detail": [{"loc", "msg", "type"}]}` with `loc` into the request
  body (contracts/http-api.md).

---

## Phase 1: Setup — settings

- [X] T001 Settings in backend/src/agent_lab/config.py: add `llm_models: tuple[str, ...]` (`LLM_MODELS`, comma-separated, blanks dropped), `openai_api_key: str` (`OPENAI_API_KEY`, default empty), `openai_models: tuple[str, ...]` (`OPENAI_MODELS`), `openai_base_url: str` (`OPENAI_BASE_URL`, default `https://api.openai.com/v1`), `openai_reasoning_off: str` (`OPENAI_REASONING_OFF`, default `none`; an empty value is kept as empty), `default_model: str` (`DEFAULT_MODEL`, default `f"local/{llm_model}"`); the four M3 variables unchanged; add the new variables, commented out, to .env.example with one line each on their meaning

---

## Phase 2: Foundational — provider field, catalog, resolution (blocks all stories)

**Purpose**: every run gets its client from a catalog of configured models, while the M3
behavior stays identical on the default local model.

- [X] T002 [P] Provider field: in backend/src/agent_lab/agents/config_fields.py add `LOCAL = "local"` and `Provider = Annotated[Literal["local", "openai"], Field(exclude_if=lambda v: v == LOCAL)]`; in each of the six configs (backend/src/agent_lab/agents/react.py `ReActConfig`, backend/src/agent_lab/workflows/chain.py, routing.py, parallel.py, orchestrator.py, evaluator.py `Config`) add `provider: Provider = LOCAL` directly after `model`; in backend/tests/test_templates.py extend `test_config_versions`: every template's version is unchanged with `provider="local"` and differs with `provider="openai"` (same `model`)
- [X] T003 [P] Client settings in backend/src/agent_lab/llm/openai_compat.py: constructor gains `provider: str = "local"` (exposed as `self.provider`, used by spans as `gen_ai.provider.name`), `reasoning_off: dict[str, Any] | None = None` (fields merged into the body when `reasoning is False`; `None` means the M3 local fields `{"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}`); remove the hard-coded fields from `chat`; tests in backend/tests/test_llm_client.py: `test_local_body_unchanged` (reasoning False, True and None give exactly the M3 bodies), `test_reasoning_off_fields_are_configurable` (`{}` adds nothing; `{"reasoning_effort": "low"}` adds only that)
- [X] T004 Catalog in new backend/src/agent_lab/llm/models.py: `ModelRef` as a frozen pydantic model (`provider: Literal["local", "openai"]`, `model: str` "1–200 characters"), the one definition used by the catalog, the registry and the API; frozen dataclass `ModelEntry(ref, provider_label, external, unavailable: str | None, client: LLMClient)`; `class UnavailableModel(Exception)` carrying a message such as `"model openai/gpt-6-luna is not available: no API key"` or `"... is not configured"`; `class Models(entries: list[ModelEntry], default: ModelRef)` with `get(ref) -> ModelEntry | None`, `client(ref) -> LLMClient` (raises `UnavailableModel`), `default`, and `__init__` raising `ValueError` naming `DEFAULT_MODEL` when the default is missing or unavailable; `parse_ref(text) -> ModelRef` splitting at the first `/` (`ValueError` for a missing `/` or an unknown provider); `models_from_settings(settings) -> Models`: Local entries for `llm_model` then `llm_models` (duplicates dropped, external false, never unavailable), OpenAI entries for `openai_models` (external true, unavailable `"no API key"` when `openai_api_key` is empty; none at all when `openai_models` is empty); one `httpx.AsyncClient(timeout=120.0)` per provider shared by its clients; OpenAI clients get `provider="openai"` and `reasoning_off={"reasoning_effort": v}` or `{}` when `v` is empty; tests in new backend/tests/test_models.py: M3 environment only → one Local entry, default `local/qwen3.5-9b`; `LLM_MODELS` with a duplicate; OpenAI models with and without key; empty `OPENAI_MODELS` hides OpenAI; `DEFAULT_MODEL` not configured, unavailable, missing `/`, unknown provider → `ValueError` naming `DEFAULT_MODEL`; a model id containing `/` (`local/Qwen/Qwen3-8B`); the same id in `LLM_MODELS` and `OPENAI_MODELS` → two entries, one per provider (spec edge case)
- [X] T005 Registry in backend/src/agent_lab/agents/registry.py: `make_config(default: ModelRef)` for all six specs (`Config(model=ref.model, provider=ref.provider)`); `validate_config(template_id, stored, default: ModelRef)` = `config_model.model_validate({"model": default.model, "provider": default.provider, **stored})`; `editable(config)` also drops `provider`; new `pinned(stored: dict) -> ModelRef | None` (both keys present → ref, else `None`); update the call in backend/tests/test_templates.py, golden file unchanged. Done as: `make_config` removed, templates use `validate_config(id, {}, default)`; `model_of(config)` gives a config's `ModelRef`
- [X] T006 Resolution and wiring: backend/src/agent_lab/runs.py `resolve(agent_id, store, models) -> (spec, config, name, client)` (client = `models.client(ModelRef(provider=config.provider, model=config.model))`, raising `UnavailableModel`); `new_run(prompt, agent_id, models, store, secrets)` and `execute_run(..., llm=client)`; backend/src/agent_lab/api.py `create_app(*, store, models: Models, secrets)` using `models.default` wherever it used `llm.model`; backend/src/agent_lab/main.py builds `models_from_settings(settings)` (a `ValueError` → `SystemExit` with its message) and passes `secrets=(llm_api_key, openai_api_key)`; in backend/src/agent_lab/llm/fake.py `FakeLLM.__init__` gains `provider: str = "fake"` (stored as `self.provider`, replacing the class attribute); in backend/tests/helpers.py add `fake_models(local: FakeLLM, openai: FakeLLM | None = None, *, openai_key: bool = True, default: ModelRef | None = None) -> Models` (sets `provider` to `"local"` / `"openai"` on the given `FakeLLM`s, so spans report the provider as in production); switch the 20 `create_app(...)` calls in backend/tests/test_api.py, test_agents_api.py, test_agents_validation.py and test_redaction.py to `models=fake_models(llm)`

**Checkpoint**: `make check` passes with the golden file unchanged; the app behaves as in M3.

---

## Phase 3: User Story 1 — Run a custom agent on a hosted model (P1) 🎯 MVP

**Goal**: pick an OpenAI model in a custom agent's settings, save, run; the run shows its model.

**Independent test**: with an OpenAI client on a mock transport, a custom routing agent pinned to
an OpenAI model sends its requests to the OpenAI URL with that model id and the key; the run
completes and records the model.

### Backend

- [X] T007 [US1] `GET /models` in backend/src/agent_lab/api.py → `[ModelInfo{provider, provider_label, model, external, available, unavailable_reason, default}]` in catalog order (contracts/http-api.md)
- [X] T008 [US1] Agent model setting in backend/src/agent_lab/api.py: reuse `ModelRef` from backend/src/agent_lab/llm/models.py for requests and responses (no second definition); `AgentInfo.model: ModelRef | None` (`pinned(stored config)`; always `None` for templates); `AgentFields.model: ModelRef | None = None`; `checked_config` also rejects `provider` inside `config` (loc `["body", "config", "provider"]`); a pinned ref must be a configured, available entry, else 422 loc `["body", "model"]` with the `UnavailableModel` message; store `{**editable(config), "model": ..., "provider": ...}` when pinned, `editable(config)` otherwise; GET, POST and PUT return the same `AgentInfo`
- [X] T009 [US1] Tests in backend/tests/test_agents_api.py: `test_models_list` (fields and order; no key or URL anywhere in the body); `test_pin_openai_model` (POST with `model` → `AgentInfo.model` echoed; run uses the OpenAI `FakeLLM` only; `run.config` has `"provider": "openai"`; LLM spans have `gen_ai.provider.name == "openai"` and `gen_ai.request.model` = the id); `test_m3_agent_is_default` (an agent row written without `model` → `AgentInfo.model is None`, its run's config has no `provider` key, so its `config_version` is computed exactly as in M3); `test_default_agent_follows_default` (same store, second app with another `default` → the agent runs on the new default, new `config_version`); `test_versions_differ_by_model` (two runs, Local and OpenAI pin → different versions, US1-3); `test_template_runs_on_default` (US1-4); `test_runs_on_two_providers_concurrently` (delayed `FakeLLM`s, both runs complete, FR-003); `test_openai_request_over_http` (custom routing agent pinned to OpenAI, catalog built with `OpenAICompatClient(provider="openai", base_url="https://openai.test/v1", api_key="sk-test…", http=MockTransport)`: every request goes to `https://openai.test/v1/chat/completions` with `Authorization: Bearer sk-test…` and the model id)
- [X] T010 [P] [US1] Validation cases in backend/tests/test_agents_validation.py: keep the `model key` case (`["config", "model"]`); add `provider key` (`["config", "provider"]`), `unknown provider` (`{"provider": "anthropic", ...}` → `["model", "provider"]`), `unconfigured model` (→ `["model"]`), `empty model id` (→ `["model", "model"]`); each still asserts nothing stored

### Frontend

- [X] T011 [P] [US1] frontend/src/lib/api.ts: `ModelRef`, `ModelInfo`, `listModels()`; `AgentInfo.model: ModelRef | null`; `AgentFields.model: ModelRef | null`
- [X] T012 [P] [US1] Pure model logic in new frontend/src/lib/models.ts with tests in new frontend/src/lib/models.test.ts: `sameRef(a, b)`; `modelLabel(ref)` → `"OpenAI · gpt-6-luna"` (`"Local · …"` for `local`); `defaultLabel(models)` → `"Default (Local · qwen3.5-9b)"`; `modelOptions(models, current)` → `[{value, label, disabled, group}]`: the Default entry first (value `""`), then per provider group the models with "(external)" for external ones and the reason for unavailable ones (`"gpt-6-luna (no API key)"`, disabled), plus a disabled `"<id> (not configured)"` entry when `current` is pinned but not in `models`; `runModel(run)` → `modelLabel({provider: run.config.provider ?? "local", model: run.config.model})`, or `null` when the config has no `model`; tests include the same id on both providers (listed once under each group, distinct values)
- [X] T013 [P] [US1] frontend/src/lib/builder.ts: `Draft.model: ModelRef | null` set by `draftFrom` (from the source agent; `null` for templates) and `draftFromAgent`, sent by `draftFields`, changed by `setField(draft, ["model"], ref)` (marks dirty); tests in frontend/src/lib/builder.test.ts
- [X] T014 [US1] Model select in frontend/src/components/builder/AgentSettings.tsx: a labelled native `<select>` ("Model") with `<optgroup>` per provider from `modelOptions`, first in agent settings; read-only for templates (shows the Default label); frontend/src/app/page.tsx loads `listModels()` with the agents and passes the list down through frontend/src/components/AgentBuilder.tsx; save errors at `model` show next to the select (via `fieldErrors`)
- [X] T015 [US1] Show the model: frontend/src/components/RunViewer.tsx header shows `runModel(run)`; frontend/src/components/RunList.tsx shows it next to the totals; frontend/src/components/SpanDetail.tsx adds a "Provider" row from `attributes["gen_ai.provider.name"]`

**Checkpoint**: an agent can be switched to an OpenAI model and run from the UI; runs show their
model.

---

## Phase 4: User Story 2 — Workflows behave the same on every provider (P2)

**Goal**: thinking off, structured decisions and tool calls work on OpenAI as locally.

**Independent test**: recorded OpenAI requests show only `reasoning_effort` for thinking off, a
strict-compatible schema and the tool declarations; local requests are unchanged; every template
shape completes on a mock OpenAI transport.

- [X] T016 [US2] Strict schema rewrite in backend/src/agent_lab/llm/openai_compat.py: constructor gains `strict_schema: bool = False` (set `True` for OpenAI in `models_from_settings`); when set and `response_format["type"] == "json_schema"`, send a deep copy whose schema has, in every object (including nested `items`), `additionalProperties: false` and `required` = all property names, with `minLength`/`maxLength` removed (`minItems`/`maxItems` kept); comment: `shortcut: one thinking-off value per provider; per-model values when mixed models need it` next to the OpenAI `reasoning_off` in backend/src/agent_lab/llm/models.py
- [X] T017 [US2] Request-shape tests in backend/tests/test_llm_client.py: `test_openai_thinking_off` (body has `reasoning_effort` = the configured value and no `chat_template_kwargs`; empty value → neither key); `test_openai_reasoning_on_adds_nothing`; `test_openai_strict_schema` for `route_model([...])`, `plan_model(3)` and `Verdict` (expected rewritten schemas spelled out); `test_local_schema_unchanged` (local client sends the pydantic schema as is); `test_only_known_parameters` (for both providers and all four cases, the body's keys ⊆ `{"model", "messages", "stream", "tools", "response_format"}` plus that provider's thinking-off keys, SC-003); `test_tool_call_parsing_openai` (same parse as local)
- [X] T018 [US2] Workflows on OpenAI in new backend/tests/test_providers.py: an `OpenAICompatClient(provider="openai", strict_schema=True, reasoning_off={"reasoning_effort": "none"})` on a `MockTransport` that answers from a per-test script; runs of a custom ReAct (tool call then answer), routing (decision then handler), orchestrator (plan of 2, workers, synthesis), evaluator (reject then approve), chain and parallel agent pinned to it through the API complete with `assert_trace_valid`; decisions are validated as in M2 (an off-schema routing label falls back; an over-long plan ends `error`) (US2-1–4, FR-008)

**Checkpoint**: every template shape runs on a mock OpenAI endpoint; local bodies unchanged.

---

## Phase 5: User Story 3 — Failures and unavailable models are clear (P3)

**Goal**: unavailable models cannot be chosen or run; provider errors end runs cleanly; keys stay
hidden.

**Independent test**: scripted 401, 429, 500, timeout and refused connection each end the run
`error` with the cause on the span; no stored or streamed data contains a key.

- [ ] T019 [US3] Unavailable models in backend/src/agent_lab/api.py: `POST /runs` catches `UnavailableModel` → 422 loc `["body", "agent_id"]` with its message, no run stored; tests in backend/tests/test_agents_api.py: `test_models_list_marks_missing_key` (`available: false`, `unavailable_reason: "no API key"`, US3-1), `test_save_rejects_unavailable_model`, `test_run_rejected_when_pinned_model_unavailable` (agent pinned while the key existed, second app without key → 422 naming `openai/<id>`, `GET /runs` unchanged), `test_run_rejected_when_pinned_model_removed` (not configured), `test_agent_with_removed_model_still_lists` (US3-2)
- [ ] T020 [P] [US3] Provider failures in backend/tests/test_providers.py: parametrized over 401 (`{"error": {"message": "Incorrect API key provided"}}`), 429, 500, `httpx.ReadTimeout` and `httpx.ConnectError` raised by the transport: the run ends `error`, the model span's `error` contains the status or exception and the provider message, the next run on the same app completes, and a Local run started at the same time as the failing OpenAI run completes normally (US3-3, FR-012, SC-004)
- [ ] T021 [P] [US3] Redaction in backend/tests/test_redaction.py: `test_provider_keys_never_exposed` with a Local key and an OpenAI key, where the mock OpenAI endpoint echoes the authorization header in a 401 body and the prompt contains the OpenAI key: neither key appears in stored spans, stored runs, WebSocket events, `GET /models`, `GET /agents`, `GET /runs` or `GET /runs/{id}` (US3-4, FR-013, SC-005)
- [ ] T022 [US3] Run rejections in the UI: frontend/src/lib/api.ts `startRun` throws `ValidationError` on 422 (via `send()`); frontend/src/app/page.tsx shows its message where run-start errors appear today; the model select shows a pinned unavailable or removed model as the disabled current option from `modelOptions` (T012)

**Checkpoint**: every failure case ends the run `error` with its cause; keys stay hidden.

---

## Phase 6: Polish

- [ ] T023 [P] Docs: README.md (switching models: `OPENAI_API_KEY`, `OPENAI_MODELS`, `DEFAULT_MODEL`, `OPENAI_REASONING_OFF`, restart after `.env` changes, external models send prompts and tool results to OpenAI); AGENTS.md (`.env` holds `LLM_API_KEY` and `OPENAI_API_KEY`; tests never call a real provider); `.specify/memory/constitution.md` is not changed (the second provider still comes from the environment)
- [ ] T024 `make check` passes; FR → test map below complete
- [ ] T025 Manual checks from quickstart.md steps 1–8 on vLLM and, with the owner's key, OpenAI; record results (including the `OPENAI_REASONING_OFF` value that works for the configured model and whether OpenAI accepts the rewritten schemas) in a "Manual check results" section of this file

---

## Dependencies

- Phase 1 → Phase 2 → stories. T002 ∥ T003; T004 needs T001 and T003; T005 needs T002 and T004;
  T006 needs T005.
- US1 needs Phase 2. US2 needs Phase 2 (its HTTP-level test T018 uses the API from T008).
  US3 needs T008 (pinned models) and T012 (options).
- Frontend: T011–T013 in parallel, then T014, T015; T022 after T014.

## Parallel opportunities

- Phase 2: T002 ∥ T003.
- US1: backend T007–T010 alongside frontend T011–T013.
- US3: T020 ∥ T021.

```bash
# US1 frontend example
Task: "frontend/src/lib/api.ts: ModelRef, ModelInfo, listModels()"
Task: "Pure model logic in frontend/src/lib/models.ts"
Task: "frontend/src/lib/builder.ts: Draft.model"
```

## Implementation strategy

1. Phase 2 first, with the golden file as the judge: after it the app must behave exactly as in
   M3.
2. MVP = US1: pin an OpenAI model and run it; stop and run quickstart steps 1–3 (step 3 needs the
   key).
3. US2 makes every template shape work on OpenAI (strict schemas); without it, OpenAI runs of the
   routing, orchestrator and evaluator shapes are expected to fail on their decisions.
4. US3 hardens failures, unavailable models and redaction.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_models.py (T004); quickstart step 1 |
| FR-002 | test_agents_api.py::test_models_list, test_models_list_marks_missing_key |
| FR-003 | test_agents_api.py::test_pin_openai_model, test_runs_on_two_providers_concurrently, test_openai_request_over_http |
| FR-004 | test_agents_api.py::test_m3_agent_is_default, test_default_agent_follows_default, test_template_runs_on_default; builder.test.ts (Draft.model) |
| FR-005 | test_agents_validation.py (T010); test_save_rejects_unavailable_model, test_run_rejected_when_pinned_model_unavailable, test_run_rejected_when_pinned_model_removed |
| FR-006 | test_templates.py::test_config_versions (T002); test_versions_differ_by_model, test_default_agent_follows_default |
| FR-007 | test_llm_client.py::test_local_body_unchanged, test_openai_thinking_off, test_only_known_parameters |
| FR-008 | test_llm_client.py::test_openai_strict_schema, test_tool_call_parsing_openai; test_providers.py (T018) |
| FR-009 | test_templates.py::test_templates_match_m2 (golden file unchanged); test_local_body_unchanged, test_local_schema_unchanged |
| FR-010 | models.test.ts (modelOptions); quickstart step 1 |
| FR-011 | models.test.ts (runModel); quickstart step 3 |
| FR-012 | test_providers.py (T020, including the concurrent Local run) |
| FR-013 | test_redaction.py::test_provider_keys_never_exposed; test_models_list |
| FR-014 | test_store.py (existing migration tests); test_m3_agent_is_default; models.test.ts (runModel without `provider`) |
| FR-015 | T003, T004, T009, T010, T017–T021 |
| FR-016 | `make check` (T024) |

| SC | Test / check |
|---|---|
| SC-001 | quickstart step 3 (timed) |
| SC-002 | quickstart step 4 (real key) |
| SC-003 | test_llm_client.py::test_only_known_parameters |
| SC-004 | test_providers.py (T020) |
| SC-005 | test_redaction.py::test_provider_keys_never_exposed |
| SC-006 | quickstart step 5; models.test.ts (runModel) |
