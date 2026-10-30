---
description: "Task list for M1 — ReAct walking skeleton"
---

# Tasks: M1 — ReAct Walking Skeleton

**Input**: `specs/001-react-walking-skeleton/` (plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md)

**Tests**: requested by the spec (FR-009, SC-005); every FR maps to a test or manual check
(see Traceability).

**Gate**: a phase is done only when `make check` passes; commit after each phase.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create `backend/` uv package `agent_lab` (Python 3.12; deps fastapi, uvicorn[standard], httpx, pydantic; dev ruff, pyright, pytest) with ruff/pyright/pytest config in backend/pyproject.toml
- [X] T002 [P] Scaffold `frontend/` with create-next-app (TypeScript, App Router, Tailwind, ESLint, pnpm, src dir), add @xyflow/react, bind dev server to 127.0.0.1 in frontend/package.json
- [X] T003 Add Makefile (`install`, `check`, `check-backend`, `check-frontend`, `dev-backend`, `dev-frontend`) and .env.example (`LLM_PROVIDER`, `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen3:8b`, `LLM_API_KEY`, `AGENT_LAB_DB`)

## Phase 2: Foundational (blocks all stories)

- [X] T004 [P] Span model and SpanKind (`llm | tool | route | retrieve | rerank | memory | step`; `ended_at` null while running) in backend/src/agent_lab/tracing/span.py
- [X] T005 [P] Redaction (sensitive keys, `Bearer …`, `sk-…`, known secret values) in backend/src/agent_lab/tracing/redact.py
- [X] T006 Tracer async context manager with contextvar parenting, redaction before sink, error capture in backend/src/agent_lab/tracing/tracer.py
- [X] T007 [P] Graph/Node/Edge models in backend/src/agent_lab/graph.py
- [X] T008 [P] SQLite store (`runs`, `spans`, upsert span, `prompt` 1..4000 chars, status `running | completed | max_iterations | error`) in backend/src/agent_lab/store.py
- [X] T009 [P] Per-run pub/sub in backend/src/agent_lab/bus.py
- [X] T010 [P] LLMClient protocol, ChatResponse, ToolCall, LLMError in backend/src/agent_lab/llm/base.py; FakeLLM in backend/src/agent_lab/llm/fake.py
- [X] T011 [P] Settings from env in backend/src/agent_lab/config.py
- [X] T012 Tests: tracer nesting/error capture and redaction units in backend/tests/test_tracing.py

## Phase 3: User Story 1 — Run the agent and watch it live (P1) 🎯 MVP

**Independent test**: scripted FakeLLM run over the WebSocket delivers every span with valid node ids.

- [X] T013 [P] [US1] Tool base (`Tool`, `ToolError`, scopes) and calculator parser in backend/src/agent_lab/tools/base.py, backend/src/agent_lab/tools/calculator.py
- [X] T014 [P] [US1] Deterministic get_weather in backend/src/agent_lab/tools/weather.py
- [X] T015 [P] [US1] Tests for calculator and weather in backend/tests/test_tools.py
- [X] T016 [P] [US1] OpenAI-compatible client in backend/src/agent_lab/llm/openai_compat.py; tests with httpx.MockTransport in backend/tests/test_llm_client.py
- [X] T017 [US1] ReActAgent (config, config_version, graph, start/step, run_to_completion) in backend/src/agent_lab/agents/react.py
- [X] T018 [US1] Test multi-step tool run (span tree, node ids, tokens, config_version) in backend/tests/test_react.py
- [X] T019 [US1] execute_run (tracer → store + bus, run_ended) in backend/src/agent_lab/runs.py
- [X] T020 [US1] API: POST /runs, WS /runs/{id}/stream, CORS, trusted hosts, WS origin check in backend/src/agent_lab/api.py, backend/src/agent_lab/main.py
- [X] T021 [US1] API tests: POST + live WS stream, origin/host rejection in backend/tests/test_api.py
- [X] T022 [P] [US1] Frontend types and fetch/ws helpers in frontend/src/lib/api.ts; span upsert/route/active node in frontend/src/lib/run-state.ts
- [X] T023 [US1] Page with PromptForm, GraphView, Waterfall, SpanDetail in frontend/src/app/page.tsx and frontend/src/components/

## Phase 4: User Story 2 — Replay a past run (P2)

**Independent test**: after a completed run and a store reopen, GET and WS return identical spans.

- [X] T024 [US2] GET /runs and GET /runs/{id} in backend/src/agent_lab/api.py
- [X] T025 [US2] Tests: persistence across store reopen in backend/tests/test_store.py; replay via GET and WS equals live in backend/tests/test_api.py
- [X] T026 [US2] RunList component and replay wiring in frontend/src/components/RunList.tsx, frontend/src/app/page.tsx

## Phase 5: User Story 3 — Failure paths (P3)

**Independent test**: scripted runs with tool errors and endless tool calls.

- [X] T027 [US3] Tests: tool error / unknown tool / malformed args fed back, max-iterations cap, model transport error → status `error`, ungranted tool scope rejected in backend/tests/test_react.py
- [X] T028 [US3] End-to-end redaction test (secret in prompt and API key never in the SQLite file) in backend/tests/test_redaction.py

## Phase 6: Polish

- [X] T029 [P] AGENTS.md (commands, gates, layout, contracts), CLAUDE.md (pointer), README.md (run instructions)
- [X] T030 Run quickstart.md manual checks (real model if available; else FakeLLM smoke) and record results

## Phase 7: Fixes from the first real-model run

- [X] T031 [US1] Trace the model's reasoning text (`reasoning` / `reasoning_content`) on llm spans, never resend it, in backend/src/agent_lab/llm/openai_compat.py and backend/src/agent_lab/agents/react.py
- [X] T032 [US1] Mark every edge for tools called in one model turn in frontend/src/lib/run-state.ts
- [X] T033 [US1] Keep graph edges visible while a live run re-renders the graph (pass `measured` with node size) in frontend/src/components/GraphView.tsx

## Manual check results (T030, 2026-10-30)

No Ollama model was pulled, so the smoke test ran the real API and UI against a scripted slow
model (headless Chromium): quickstart steps 1–5 and 7 pass (live graph/waterfall, span detail,
replay after reload, mobile width, both servers bound to 127.0.0.1, foreign `Host` → 400).
Step 6 passed with the scripted `2**999` call (error on the tool span, run continued). A
real-model run with `qwen3:8b` followed and passed; it exposed T031 and T032.

## Dependencies

Setup → Foundational → US1 → US2 → US3 → Polish. US2 reuses US1's API and page; US3 only adds
tests (and any fixes they expose) on US1 code.

## Parallel opportunities

T002 ∥ T001; T004, T005, T007–T011 in parallel; T013–T016 and T022 in parallel.

## Traceability (FR → test)

| FR | Test / check |
|---|---|
| FR-001 | test_react.py::test_multi_step_tool_run |
| FR-002 | test_react.py::test_max_iterations_cap |
| FR-003 | test_tools.py::test_calculator_* |
| FR-004 | test_tools.py::test_weather_deterministic |
| FR-005 | test_react.py::test_tool_error_fed_back, test_unknown_tool_and_bad_args |
| FR-006 | test_react.py::test_ungranted_scope_rejected, test_tools.py::test_m1_tools_have_no_scopes |
| FR-007 | test_llm_client.py::test_request_and_tool_call_parsing |
| FR-008 | test_react.py (agent typed against `LLMClient`, driven by FakeLLM; pyright gate) |
| FR-009 | whole suite runs without network (FakeLLM / MockTransport) |
| FR-010 | test_react.py::test_multi_step_tool_run (span tree), test_tracing.py::test_nesting |
| FR-011 | test_react.py::test_multi_step_tool_run (model, tokens, messages), test_reasoning_traced_not_resent; test_llm_client.py::test_reasoning_parsed |
| FR-012 | test_react.py::test_multi_step_tool_run (node ids ⊆ graph) |
| FR-013 | test_react.py::test_config_version_stable |
| FR-014 | test_tracing.py::test_redact_*, test_redaction.py::test_secrets_never_stored |
| FR-015 | test_store.py::test_persists_across_reopen |
| FR-016 | test_api.py::test_live_stream |
| FR-017 | test_api.py::test_replay_matches_live, test_list_runs |
| FR-018 | test_api.py::test_live_stream, test_replay_matches_live, test_unknown_run_ws |
| FR-019 | test_api.py::test_rejects_foreign_origin_ws, test_rejects_foreign_host, test_cors; Makefile binds 127.0.0.1 (quickstart step 7) |
| FR-020–FR-024 | quickstart.md manual steps 1–5 (no JS test runner approved in M1) |
| FR-025 | `make check` |
| FR-026 | files present (T029) |
