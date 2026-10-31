# HTTP API changes in M4

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/models` | – | `200` `[ModelInfo]`: Local models in configured order, then OpenAI models |
| GET | `/agents` | – | as M3; each `AgentInfo` gains `model`: `ModelRef` when pinned, `null` on "Default" (templates always `null`) |
| POST | `/agents` | M3 body + `"model": ModelRef \| null` (optional, default `null`) | `201` `AgentInfo`; `422` at `["body", "model"]` when the ref is not configured or unavailable |
| PUT | `/agents/{agent_id}` | M3 body + `"model": ModelRef \| null` (optional, default `null`) | `200` `AgentInfo`; `422` as above |
| POST | `/graph` | unchanged | unchanged (the model does not affect the graph) |
| POST | `/runs` | unchanged | `202` `Run`; `422` at `["body", "agent_id"]` when the agent is pinned to a model that is no longer configured or available, e.g. `"model openai/gpt-6-luna is not available: no API key"` |
| GET | `/runs`, `/runs/{run_id}` | – | unchanged shape; `run.config` holds `model` and, unless local, `provider` |
| WS | `/runs/{run_id}/stream` | – | unchanged |

Types:

```text
ModelRef  = {"provider": "local" | "openai", "model": str}
ModelInfo = {"provider": "local" | "openai", "provider_label": "Local" | "OpenAI",
             "model": str, "external": bool, "available": bool,
             "unavailable_reason": str | null, "default": bool}
```

Rules:

- `config` in agent bodies still holds only the editable fields; `model` or `provider` inside
  `config` is rejected (`["body", "config", "model"]` / `["body", "config", "provider"]`).
- An unknown `provider` value in `model` is a 422 at `["body", "model", "provider"]`.
- No response contains an API key, an authorization header or a provider base URL.
- CORS and the Host allowlist are unchanged.
