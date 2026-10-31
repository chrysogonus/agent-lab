# Data Model: M4 — Model Providers

## Provider (environment only, `llm/models.py`)

| Field | Local | OpenAI |
|---|---|---|
| name | `local` | `openai` |
| label | `Local` | `OpenAI` |
| base URL | `LLM_BASE_URL` | `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) |
| API key | `LLM_API_KEY` (optional) | `OPENAI_API_KEY` |
| model ids | `LLM_MODEL`, then `LLM_MODELS` (duplicates dropped) | `OPENAI_MODELS`; empty = provider hidden |
| external | false | true |
| needs key | false | true |
| thinking-off fields | `reasoning_effort: none` + `chat_template_kwargs.enable_thinking: false` | `reasoning_effort: $OPENAI_REASONING_OFF`, or nothing when empty |
| strict-schema rewrite | no | yes (research §6) |

Keys and base URLs never leave the server.

## Model reference

`ModelRef {provider: "local" | "openai", model: str}`. Identity is the pair, so the same model id
on both providers stays two entries.

## Model entry (one per configured model, built at startup)

| Field | Rule |
|---|---|
| ref | `ModelRef` |
| external | from the provider |
| unavailable | `null`, or `"no API key"` when the provider needs a key and has none |
| default | true for exactly one entry: `DEFAULT_MODEL` or `local/$LLM_MODEL` |
| client | the `OpenAICompatClient` for this ref (not exposed) |

Startup validation: `DEFAULT_MODEL` must name a configured, available entry; otherwise the server
exits with a message naming `DEFAULT_MODEL`.

## Template `Config` (each of the six, unchanged otherwise)

| Field | Change |
|---|---|
| `model: str` | unchanged position; the model id |
| `provider: str` | new, right after `model`; default `"local"`; left out of the JSON when `"local"` |

`config_version` = hash of the JSON, so local configs keep their M3 versions and OpenAI configs
get new ones.

## Custom agent (stored row, table unchanged)

| Field | Change |
|---|---|
| `config` (JSON) | editable fields as in M3, plus `model` and `provider` **only when pinned** |

- "Default": the keys are absent; the agent runs with the default at run start.
- Pinned: both keys present; saving requires the ref to be a configured, available entry (422 at
  `body.model`).
- M3 rows have no `model` key, so they are on "Default" without migration.
- Resolution for a run or for `GET /agents`:
  `config_model.model_validate({"model": default.model, "provider": default.provider, **stored})`.

## Run (table unchanged)

- `config` snapshot holds the `model` (and `provider` unless local) the run actually used, also
  for agents on "Default" (FR-006). M1–M3 runs have `model` and no `provider`: shown as Local.
- `config_version` follows from the config (see above).
- Spans: `model` = the model id the provider reported; attributes `gen_ai.provider.name`
  (`local` | `openai`) and `gen_ai.request.model`.

## State rules

- Starting a run of an agent pinned to an entry that is missing or unavailable → 422 at
  `body.agent_id`, message naming `provider/model` and the reason; no run is stored.
- Changing `DEFAULT_MODEL` changes the model (and version) of templates and "Default" agents for
  later runs only.
