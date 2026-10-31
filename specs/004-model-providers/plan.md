# Implementation Plan: M4 — Model Providers and Per-Agent Model Choice

**Branch**: `main` (feature directory `004-model-providers`) | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-model-providers/spec.md`

## Summary

Two providers, Local (the M3 server) and OpenAI, are read from the environment; every M4
variable is optional, so the M3 `.env` keeps working. At startup the server builds one
`OpenAICompatClient` per configured model into a `Models` catalog with the default model. Each
template `Config` gains a `provider` field that is left out of the JSON when it is `local`, so
local configs and their `config_version`s stay exactly as in M3. A custom agent stores
`model`/`provider` in its config only when pinned; without them it follows the default. A run
picks the client for its config's (provider, model); the workflows do not change. Provider
differences live in the client: its own thinking-off fields, and for OpenAI a strict-mode
rewrite of decision schemas. The API adds `GET /models` and a `model` field on agents; the UI
adds a model select in agent settings and shows the model on runs.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / Next.js 16 (frontend)

**Primary Dependencies**: unchanged; no new dependencies. Uses pydantic's `Field(exclude_if=...)`
(installed 2.14.2).

**Storage**: SQLite, no schema change. A pinned model is two keys in the agent's config JSON;
runs already store their config.

**Testing**: pytest with `FakeLLM` and `httpx.MockTransport` (per-provider request bodies,
failures); golden template file unchanged; vitest for model labels and options.

**Target Platform**: local Linux/WSL, loopback only; OpenAI reached over HTTPS when configured

**Project Type**: web app (backend + frontend)

**Performance Goals**: switching an agent's model and starting a run in under 30 s (SC-001);
hosted calls bounded by the existing 120 s request timeout.

**Constraints**: local requests and template `config_version`s exactly as in M3 (FR-009);
keys never stored, streamed or sent to the browser; no agent frameworks or provider SDKs.

**Scale/Scope**: single owner; two providers; a handful of model ids each.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | Same hand-written client, two constructor settings (`reasoning_off`, `strict_schema`); no OpenAI SDK; one small `llm/models.py` |
| II. Observable by default | Pass | No new model path; every call still goes through `steps.chat`; spans add the real provider name (`gen_ai.provider.name`) next to the model |
| III. Secure local defaults | Pass | Servers still bind to 127.0.0.1; both keys are known secrets for redaction; `GET /models` exposes no key or URL; choosing an external model is marked in the UI (spec assumption: no extra confirmation) |
| IV. Smallest change | Pass | This is the sanctioned provider seam. Exactly two providers (clarify Q2), fixed model list (Q3), no capability table, no migration |
| V. Gates + traceability | Pass | `make check` unchanged; label logic in `lib/models.ts` with vitest; FR → test map in `tasks.md` |

The constitution says "Provider, base URL and model come from the environment"; M4 keeps that
and adds a second provider from the environment. Post-design re-check: passes; no Complexity
Tracking entries.

## Design

Details: [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md).

### Configuration (`config.py`, `llm/models.py`, `main.py`)

- `Settings` gains `llm_models`, `openai_api_key`, `openai_models`, `openai_base_url`,
  `openai_reasoning_off`, `default_model` (research §4).
- `llm/models.py`: `ModelRef`, `ModelEntry`, `Models` (entries in order, `default`, `get(ref)`,
  `client(ref)`, `info()`), and `models_from_settings(settings)` that builds the clients, one
  shared `httpx.AsyncClient` per provider. Startup exits with a message naming `DEFAULT_MODEL`
  when the default is missing or unavailable.
- `main.py`: `create_app(store=..., models=models_from_settings(settings), secrets=(llm key,
  openai key))`. The `LLM_PROVIDER` check stays.

### Client (`llm/openai_compat.py`)

- Constructor gains `provider` (span name: `local` / `openai`), `reasoning_off: dict` and
  `strict_schema: bool`. The M3 hard-coded thinking-off fields move into Local's
  `reasoning_off`, so the local body is byte-for-byte the same.
- `strict_schema`: before sending a `json_schema` response format, copy the schema, give every
  object `additionalProperties: false` and `required` = all properties, drop
  `minLength`/`maxLength` (research §6). Pydantic validation of the answer is unchanged.
- Error handling unchanged (`LLMError` → span error → run `error`).

### Configs and resolution (`workflows/*.py`, `agents/react.py`, `agents/registry.py`, `runs.py`)

- Each of the six `Config`s: `provider: str = Field(default="local", exclude_if=...)` right after
  `model` (a shared annotated type in `agents/config_fields.py`).
- Registry: `make_config(default: ModelRef)` instead of `make_config(llm)`;
  `validate_config(template_id, stored, default)` merges
  `{"model": default.model, "provider": default.provider, **stored}`; `editable()` also drops
  `provider`; new `pinned(stored) -> ModelRef | None`.
- `runs.resolve(agent_id, store, models)`: build the config as above, then
  `models.client(ModelRef(config.provider, config.model))`; a pinned ref that is missing or
  unavailable raises `UnavailableModel(message)`. `new_run`/`execute_run` take the resolved
  client instead of the app-wide `llm`.

### API (`api.py`)

- `GET /models` → `[ModelInfo]`.
- `AgentInfo.model`, `AgentFields.model: ModelRef | None = None`. On save: reject
  `model`/`provider` inside `config`; check a pinned ref with `models.get` (422 at
  `body.model`); store `{**editable(config), **pinned_keys}`.
- `POST /runs`: `UnavailableModel` → 422 at `body.agent_id` naming the model.

### UI

- `lib/api.ts`: `ModelRef`, `ModelInfo`, `listModels()`, `AgentInfo.model`, `AgentFields.model`.
- `lib/models.ts` (pure, vitest): `modelLabel(ref, models)` ("OpenAI · gpt-6-luna"),
  `modelOptions(models, current)` (Default first, groups by provider, disabled + reason, a
  "not configured" entry for a missing pinned ref), `runModel(run)` from the stored config.
- `lib/builder.ts`: `Draft.model` carried through `draftFrom*`, `draftFields`, dirty state.
- `builder/AgentSettings.tsx`: model `<select>` with `<optgroup>`s; read-only for templates
  (shows "Default (…)").
- `RunViewer` header and `RunList` entries show `runModel(run)`; `SpanDetail` adds the provider.
- Visual work follows the frontend-design skill (owner's global rule), keeping the M3 identity.

### Docs

`.env.example`, README and AGENTS.md: the new variables, that `OPENAI_API_KEY` stays in `.env`
only, and that `.env` changes need a backend restart.

## Project Structure

### Documentation (this feature)

```text
specs/004-model-providers/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
backend/src/agent_lab/
├── config.py, main.py                    # new settings, catalog at startup
├── llm/models.py                         # new: ModelRef, ModelEntry, Models, models_from_settings
├── llm/openai_compat.py                  # provider, reasoning_off, strict_schema
├── agents/config_fields.py               # Provider field type
├── workflows/*.py, agents/react.py       # provider field in each Config
├── agents/registry.py, runs.py, api.py   # default-aware resolution, /models, agent model
backend/tests/
├── helpers.py                            # catalog from FakeLLMs
├── test_models.py                        # new: settings → catalog, default rules
├── test_llm_client.py                    # per-provider bodies, strict rewrite, failures
├── test_templates.py                     # make_config(default ref); golden file unchanged
├── test_agents_api.py, test_agents_validation.py, test_api.py, test_redaction.py  # extended
frontend/src/
├── lib/api.ts, lib/models.ts (+ test), lib/builder.ts (+ test)
└── components/builder/AgentSettings.tsx, RunViewer.tsx, RunList.tsx, SpanDetail.tsx, app/page.tsx
.env.example, README.md, AGENTS.md
```

**Structure Decision**: extend the M3 layout; one new backend module and one new frontend
module.

## Complexity Tracking

None.
