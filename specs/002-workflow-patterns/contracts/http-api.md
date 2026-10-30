# HTTP API changes in M2

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/agents` | – | `200` `[AgentInfo]`, ReAct first, then chain, routing, parallel, orchestrator, evaluator |
| POST | `/runs` | `{"prompt": str (1..4000), "agent_id": str = "react"}` | `202` `Run`; `422` if `agent_id` is not in `/agents` |
| GET | `/runs` | – | `200` `[Run]` (now with `totals`) |
| GET | `/runs/{run_id}` | – | `200` `{"run": Run, "spans": [Span]}` (`run.totals` included) |
| WS | `/runs/{run_id}/stream` | – | unchanged (M1 `stream-events.md`) |

`AgentInfo`, `RunTotals`: see `../data-model.md`. Origin/Host rules unchanged.
