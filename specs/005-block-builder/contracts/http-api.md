# HTTP API changes in M5

Block agents use the M3/M4 agent endpoints with `template_id: "blocks"`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/blocks/new` | – | `200` unsaved `AgentInfo` draft: `id: ""`, `kind: "custom"`, `template_id: "blocks"`, name "New block agent", the default `BlocksConfig` (without model), `model: null`, its graph |
| GET | `/agents/{agent_id}/blocks` | – | `200` unsaved `AgentInfo` draft converting a template or template-based custom agent: same name, description, sample prompt and model, `config` = the converted blocks; `404` unknown id; `409` the agent is already a block agent |
| GET | `/agents` | – | as M4; block agents are listed with the custom agents (`template_id: "blocks"`) |
| POST | `/agents` | `{"template_id": "blocks", "name", "description", "sample_prompt", "config": {"reasoning", "blocks"}, "model"}` | `201` `AgentInfo`; `422` with locs into `config.blocks` for every invalid block field or layout rule |
| PUT | `/agents/{agent_id}` | as M4 | as M4 |
| POST | `/graph` | `{"template_id": "blocks", "config"}` | `200` derived graph; `422` as above |
| POST | `/runs` | unchanged | `202`; `422` at `["body", "agent_id"]` if the stored layout no longer validates (e.g. a tool removed) |

Rules:

- `"blocks"` is not a template: it is absent from the template list and `POST /runs` with
  `agent_id: "blocks"` is `422` (unknown agent), as for any id that is neither a template nor a
  stored agent.
- Every rejection keeps the `422 {"detail": [{"loc", "msg", "type"}]}` shape, `loc` starting
  `["body", "config", "blocks", …]` for block errors.
- Templates and M3 custom agents behave exactly as in M4.

`AgentInfo`, `ModelRef`: as M4. `BlocksConfig`, `Block`: [data-model.md](../data-model.md).
