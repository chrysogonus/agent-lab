# HTTP API changes in M3

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/agents` | – | `200` `[AgentInfo]`: the six templates in M2 order, then custom agents by name (case-insensitive) |
| GET | `/tools` | – | `200` `[ToolInfo]` |
| POST | `/agents` | `{"template_id", "name", "description", "sample_prompt", "config"}` | `201` `AgentInfo`; `422` on any invalid field or a name in use |
| PUT | `/agents/{agent_id}` | `{"name", "description", "sample_prompt", "config"}` | `200` `AgentInfo`; `404` unknown or template id; `422` as above |
| DELETE | `/agents/{agent_id}` | – | `204`; `404` unknown or template id. Runs of the agent stay |
| POST | `/graph` | `{"template_id", "config"}` | `200` `Graph` derived by the server; `422` with field errors |
| POST | `/runs` | `{"prompt": str (1..4000), "agent_id": str = "react"}` | `202` `Run`; `422` if `agent_id` is neither a template nor a stored custom agent |
| GET | `/runs`, `/runs/{run_id}` | – | as M2; `Run` gains `agent_name`, `template_id` (null on M1/M2 runs) |
| WS | `/runs/{run_id}/stream` | – | unchanged |

Rules:

- `config` contains the template's editable fields ([data-model](../data-model.md)); `model` is
  rejected if sent (the server injects its configured model). Graphs and `config_version` are
  never accepted from the client.
- Every rejection is `422 {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` with `loc`
  pointing into the body, e.g. `["body", "name"]` for a name in use,
  `["body", "config", "routes", 1, "tool"]` for an unknown tool,
  `["body", "template_id"]` for an unknown template.
- CORS: allowed methods become `GET, POST, PUT, DELETE`; origins and the Host allowlist are
  unchanged.

`AgentInfo`, `ToolInfo`, `Run`: see [data-model](../data-model.md).
