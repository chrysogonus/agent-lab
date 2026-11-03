# API

[← README](../README.md)

The backend serves on **http://127.0.0.1:8000** (local only). The frontend uses nothing else,
so everything the UI does can be scripted.

## Agents and runs

| Endpoint | What it does |
|---|---|
| `GET /agents` | templates, then custom agents, with config, sample prompt and graph |
| `POST /agents`, `PUT /agents/{id}`, `DELETE /agents/{id}` | create, update, delete a custom agent (`model`: `{"provider", "model"}` or `null` for Default) |
| `GET /blocks/new`, `GET /agents/{id}/blocks` | an unsaved block agent: new, or converted from a template or custom agent |
| `POST /graph` `{"template_id", "config"}` | the graph for an unsaved config (validation errors as `422`) |
| `GET /tools` | tools of every connected MCP server, by config name (`calculator`, `server/tool`), with `server` and their parameter schema |
| `GET /models` | configured models: provider, id, external, available, default (never keys) |
| `POST /runs` `{"prompt", "agent_id"}` | start a run (`202`); `409` when a tool's server is not connected or does not list it |
| `GET /runs` | past runs with totals, newest first (village turns are left out) |
| `GET /runs/{id}` | a run and its spans |
| `WS /runs/{id}/stream` | stored spans, then live span events, then `run_ended` |

```bash
# start a run of the ReAct template, keep its id, then fetch the run with its spans
RUN_ID=$(curl -s -X POST http://127.0.0.1:8000/runs -H 'content-type: application/json' \
  -d '{"prompt": "What is 17*23 plus the current temperature in Berlin?", "agent_id": "react"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["run_id"])')
curl -s "http://127.0.0.1:8000/runs/$RUN_ID"
```

## MCP

See [tools.md](tools.md).

| Endpoint | What it does |
|---|---|
| `GET /mcp/servers` | the servers file (`file`, `file_error`) and every server: kind, target, state, reason, revision, tools, last connect's messages (secrets redacted) |
| `POST /mcp/servers/{name}/reconnect` | re-read one entry and connect it again (`202`, `404` for an unknown name) |
| `POST /mcp/reload` | re-read the servers file (`202`) |
| `POST /mcp` | the lab's own MCP server for outside clients (both revisions; `GET` and `DELETE` are `405`) |

## Village

| Endpoint | What it does |
|---|---|
| `GET /village` | the whole village state: clock, calendar, weather, villagers (with plans, what they carry and what they are set on: `intention` with `kind`, `place`, `villager`, `until`, `purpose`, `since`, and their `keepsakes`), today's `happenings` (kind, label, cell, state, by, concerns, start, end and the `figure` to draw), the `boat` (null until built; state, rowers, cell), festival stalls, the trader, the latest town hall meeting, the project being built and what stands, log, chronicle, map (with the building catalogue) |
| `POST /village/start`, `/pause`, `/step`, `/reset` | the controls |
| `PUT /village/interval` | seconds per step, 1–30 (the UI sends 15, 5 or 2) |
| `GET /village/villagers/{name}/turns` | a villager's turns (decisions, plans, reflections, meeting runs), newest first |
| `GET /village/health?days=14` | village health of the recent days (at most 28), newest first; the day in progress has `final: false`, numbers without a source are `null` |
| `POST /village/villagers/{name}/whisper` | `{"text"}` (1–200 characters, 3 a day per villager): heard now (`{"heard": true}`) or on waking (`false`); 404 unknown villager, 422 bad length, 409 the day's limit. Heard as a claim from "a voice"; the decision answering it has `"after_whisper": true` (M15) |
| `GET /village/health/{day}/turns?reason=` | the decisions of that day that waited for one kind of reason (names and goods taken out: `<villager> is not next to you`) |
| `WS /village/stream` | the state after every move, step and decision |

Details per milestone: `specs/*/contracts/`.
