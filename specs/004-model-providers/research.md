# Research: M4 — Model Providers and Per-Agent Model Choice

Sources were checked on 2026-10-31. Facts about OpenAI below come from third-party pages, not
OpenAI's own reference, and are confirmed or corrected by the manual real-key check (SC-002).

## 1. Where the model lives in a config, without changing M3 `config_version`s

- **Decision**: every template `Config` keeps `model: str` (the model id) and gains, right after
  it, `provider: str = Field(default="local", exclude_if=lambda v: v == "local")`.
  `config_version` stays `sha256(config.model_dump_json())[:12]`.
- **Rationale**: the golden file pins each template case's `config_version` (FR-009, golden test
  unchanged). With `exclude_if`, a local config serializes exactly as in M3, so template and
  "Default" agent versions are unchanged, while an OpenAI config gets a different version
  (FR-006). Stored run configs read the same way: no `provider` key means local, which is also
  true of every M1–M3 run. Checked with the installed pydantic 2.14.2:
  `{"model":"q"}` vs `{"model":"g","provider":"openai"}`.
- **Alternatives**: a `provider` field always serialized (changes all six golden versions);
  one combined string like `openai/gpt-…` in `model` (the run header, span names and request
  body would need to split it everywhere); a custom serializer on a shared base class (more
  code, and field order would move `model` and change hashes).

## 2. Where a custom agent's model setting is stored

- **Decision**: in the agent's stored `config` JSON as the flat keys `model` and `provider`, only
  when pinned. "Default" = the keys are absent. Resolution is
  `config_model.model_validate({**default_fields, **stored})`. The API exposes it as a separate
  top-level `model` field (`{provider, model}` or `null`); `config` in the API stays the editable
  fields only.
- **Rationale**: no schema migration; M3 agents (stored without `model`) are on "Default" with no
  change (clarification Q1). The stored keys are the `Config`'s own fields, so validation stays
  in one place.
- **Alternatives**: new `model_provider`/`model_id` columns (a migration for no gain); pinning
  every agent at first start (rejected in clarify, option B).

## 3. One client per configured model

- **Decision**: at startup, build one `OpenAICompatClient` per configured (provider, model). The
  clients of one provider share one `httpx.AsyncClient`. A `Models` catalog
  (`llm/models.py`) holds, per model: the reference, provider label, external flag, the reason
  it is unavailable (or none) and its client; plus the default reference. A run gets the client
  of its config's (provider, model); workflows are unchanged (they already use `ctx.llm` and
  `ctx.llm.model`).
- **Rationale**: the model list is fixed at startup (clarification Q3), so the clients can be too;
  no factory or cache is needed. Concurrent runs on different providers use different clients
  (FR-003). Tests build a catalog from `FakeLLM`s directly.
- **Alternatives**: passing the model per `chat()` call (changes the `LLMClient` protocol and every
  call site); a client factory with a cache (more code for the same behavior).

## 4. Environment variables

- **Decision**:

  | Variable | Meaning | Default |
  |---|---|---|
  | `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | local provider, as in M3 | as in M3 |
  | `LLM_MODELS` | further local model ids, comma-separated | empty |
  | `OPENAI_API_KEY` | OpenAI key; without it OpenAI models are listed as unavailable | empty |
  | `OPENAI_MODELS` | OpenAI model ids, comma-separated; empty hides OpenAI | empty |
  | `OPENAI_BASE_URL` | OpenAI endpoint | `https://api.openai.com/v1` |
  | `OPENAI_REASONING_OFF` | `reasoning_effort` value sent when reasoning is off; empty sends nothing | `none` |
  | `DEFAULT_MODEL` | `provider/model`, split at the first `/` (model ids may contain `/`) | `local/$LLM_MODEL` |

  Startup fails with a message naming `DEFAULT_MODEL` when it is not a configured model or not
  available (spec edge case). Both keys go into the redaction secrets.
- **Rationale**: the M3 `.env` keeps working unchanged (FR-001); every M4 variable is optional.
- **Alternatives**: a JSON or YAML provider file (more to parse, rejected with the generic provider
  list in clarify, option B).

## 5. Thinking off per provider (FR-007)

- **Decision**: the client gets `reasoning_off: dict` (the fields added when `reasoning` is
  False). Local: `{"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking":
  false}}`, exactly the M3 body. OpenAI: `{"reasoning_effort": OPENAI_REASONING_OFF}`, or `{}`
  when that variable is empty. When `reasoning` is True or None nothing is added (the provider's
  default, spec edge case).
- **Findings**: `chat_template_kwargs` is a vLLM/SGLang extension, not an OpenAI parameter
  ([Agenta](https://agenta.ai/docs/prompt-engineering/playground/chat-template-kwargs)); OpenAI
  answers unknown fields with 400 "Unrecognized request argument supplied"
  ([OpenAI forum](https://community.openai.com/t/unrecognized-request-argument-supplied-functions/605984)).
  `reasoning_effort: "none"` is accepted by GPT-5.1 and later general models, not by GPT-5, Codex,
  pro or o-series models, which take `minimal` or `low`
  ([Vercel AI Gateway](https://vercel.com/docs/ai-gateway/capabilities/reasoning/openai)).
  Non-reasoning models reject `reasoning_effort` entirely. Third-party pages list `gpt-6-luna`,
  `gpt-6-sol` and `gpt-6-astra` as API ids
  ([Let's Data Science](https://letsdatascience.com/news/openai-expands-gpt-56-options-in-chatgpt-360ebb75));
  which effort values they accept is not documented in what I found.
- **Rationale**: one setting covers the models the owner is likely to configure; a model that
  rejects the value fails the run with OpenAI's message on the span (FR-012), and the owner
  changes or empties `OPENAI_REASONING_OFF`.
- **Known limit**: the value is per provider, not per model. Configuring a GPT-5.1+ model and a
  non-reasoning model together needs a per-model value later. Code comment:
  `shortcut: one thinking-off value per provider; per-model values when mixed models need it`.
- **Alternatives**: a per-model table (a capability table, out of scope per the spec); sending
  nothing (reasoning models would think at their default effort, slower and costlier).

## 6. Structured output on OpenAI (FR-008)

- **Decision**: the OpenAI client rewrites a `json_schema` request's schema before sending:
  every object gets `additionalProperties: false` and `required` = all its properties, and the
  string keywords `minLength`/`maxLength` are dropped. The server still validates the answer with
  the full pydantic model (M2 decision rules), so dropped bounds are still enforced. The local
  client sends the schema unchanged (golden requests).
- **Findings**: OpenAI strict mode requires `additionalProperties: false` and every property in
  `required` ([merge.dev](https://docs.merge.dev/merge-gateway/capabilities/structured-outputs),
  [DEV](https://dev.to/modelflare_dev/structured-outputs-with-openai-compatible-apis-a-json-schema-guide-46bb));
  pydantic's schemas omit `additionalProperties`, so all three decisions (`Route`, `Plan`,
  `Verdict`) would be rejected as sent today. Support for `minLength`/`maxLength` in strict mode
  is not confirmed by the sources; `Plan` uses them on its items. `minItems`/`maxItems` are kept.
- **Alternatives**: `extra="forbid"` on the decision models (changes the golden local requests);
  `strict: false` for OpenAI (no schema guarantee, more decision errors).

## 7. Tool calling and other parameters

- **Decision**: no change. The client sends only `model`, `messages`, `stream`, `tools`,
  `response_format` and the thinking-off fields; no `max_tokens` or `temperature`, which OpenAI
  reasoning models restrict. Tool declarations are already OpenAI's own format.

## 8. Failures and secrets (FR-012, FR-013)

- **Decision**: no new error path. Every transport error, non-200 status and bad body already
  raises `LLMError`, which the span records before the run ends `error`; the 120 s timeout stays.
  The provider name goes on the span as `gen_ai.provider.name` (`local` or `openai`, from the
  client) next to `gen_ai.request.model`.
- **Secrets**: both keys are passed to the tracer's known-secret redaction; the `sk-…` pattern and
  the `authorization` key rule already exist. OpenAI's 401 text is expected to show only a masked
  key (not verified); if it echoed the full key, the known-secret rule would still replace it. `GET /models` returns no key or base URL. Tests assert no stored span, run,
  stream event or API response contains either key (SC-005).

## 9. UI

- **Decision**: a native `<select>` with `<optgroup>` per provider in agent settings, first option
  "Default (Local · qwen3.5-9b)". External models get "(external)" in the label; unavailable ones
  are `disabled` with the reason in the label, e.g. "gpt-6-luna (no API key)". A pinned model that
  is no longer configured shows as a disabled option "gpt-x (not configured)" so the current value
  stays visible. The run header and past-runs list show `provider · model` from the run's stored
  config (no `provider` = Local); the span detail adds the provider from
  `gen_ai.provider.name`.
- **Rationale**: a native select is keyboard and screen-reader accessible with no new component;
  the label rules are pure functions in `lib/models.ts` with vitest tests.
