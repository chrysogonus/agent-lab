# Implementation Plan: M16 — Tools over MCP

**Branch**: `main` (feature directory `016-mcp-tools`) | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-mcp-tools/spec.md`

## Summary

A new package `agent_lab/mcp/` holds a hand-written MCP layer for both ends.

1. **The protocol**:
   - `jsonrpc.py`: messages and errors;
   - `server.py`: one server core answering both protocol eras;
   - `client.py`: one connection, which finds the era and lists and calls tools.
2. **The transports**: in-process (the lab's own server), stdio (local programs) and streamable
   HTTP (addresses), all in `transports.py`.
3. **The host** (`host.py`):
   - reads the servers file (`servers_file.py`);
   - connects every server in a FastAPI lifespan;
   - resolves config tool names to callable tools;
   - keeps each connection's state and last connect messages for the Tools page.
4. **The lab's server** (`lab_server.py`): serves `calculator` and `get_weather` in-process to
   the host, and over `POST /mcp` to outside clients.
5. **The notes server** (`notes.py`): a separate stdio program over the same server core.

`steps.call_tool` sends every call through the host, with the JSON-RPC messages on the tool
span. The frontend gains a Tools view, and the tool pickers group tools by server.

The MCP revision is 2026-07-28 with a fallback to 2025-11-25 ([research.md](research.md) §1).

## Technical Context

- **Language/Version**: Python 3.12, TypeScript / Next.js 16
- **Dependencies**: unchanged. JSON-RPC, SSE parsing and the subprocess transport use
  `json`, `asyncio` and the existing `httpx`.
- **Storage**: none new. The servers file is JSON, and connections live in memory.
- **Testing**:
  - pytest with `FakeLLM`;
  - `httpx.MockTransport` for HTTP servers;
  - the in-process transport;
  - the notes server and a small legacy server script as real subprocesses;
  - vitest.
- **Target Platform**: local (127.0.0.1)
- **Project Type**: web application
- **Performance Goals**: a built-in tool call through the in-process path adds under 5 ms. A
  stdio call to the notes server takes under 100 ms. Connecting all servers never delays the
  lab's start.
- **Constraints**:
  - no MCP library;
  - existing configs, config versions, graphs and golden files unchanged (research §4);
  - secrets from the servers file redacted everywhere;
  - `make dev` keeps reloading cleanly, so local programs stop with the old process.
- **Scale/Scope**: up to 20 servers; tool results up to 20,000 characters; 10 s to connect,
  30 s per call.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Hand-built, readable | Pass | JSON-RPC and both MCP eras are written by hand in small modules (each well under 300 lines). There is no SDK and no framework. |
| II. Observable by default | Pass | Every tool call stays a tool span and now carries the request and response messages. Connecting happens outside runs, and its messages are kept and shown on the Tools page. |
| III. Secure local defaults | Pass | The lab binds 127.0.0.1. `/mcp` checks `Origin` and `Host`. Addresses are loopback unless the entry allows a host. Local programs get only named variables. The notes server stays in its folder. Tool output stays a tool message. The servers file is the declared and granted scope, replacing the unused per-tool scopes. |
| IV. Smallest change | Pass | One server core serves the lab and the notes server. Built-ins keep their names. The fallback is the spec-prescribed minimum. Legacy HTTP tool-change streams are left out (research §3). |
| V. Gates + traceability | Pass | Every FR maps to tests with the fake model and fake transports. SC-003, SC-005 and SC-006 are manual checks. |

Post-design re-check: all pass. The servers file adds a way to run local commands. It is the
owner's own file, read only from the lab's folder or `MCP_SERVERS_FILE`, and no API writes it.

## Design

### Backend

- `mcp/jsonrpc.py`:
  - `request`, `notification`, `result` and `error` builders;
  - `is_response` and `is_notification`;
  - the error codes (`-32600`, `-32601`, `-32602`, `-32603`, `-32020`, `-32022`);
  - `RpcError(code, message, data)`.
- `mcp/server.py`: `Server(name, version, tools: list[Tool])`.
  - `handle(message) -> response | None` answers both eras (contracts: "MCP messages the lab
    answers"). It checks arguments the way `_parse_arguments` does today, which moves here from
    `steps.py`.
  - `run_stdio(server)`: a loop reading stdin lines and writing stdout lines.
- `mcp/transports.py`: one shape, `send(message) -> response` and `notify(message)`, with
  `on_notice(callback)` and `close()`.
  - `InProcess(server)`;
  - `Stdio(command, args, env, cwd)`: the reader task, the futures by id and the stderr tail;
  - `Http(url, headers, client)`: JSON or SSE responses, the legacy session id and the
    long-lived listen stream.
- `mcp/client.py`: `Connection(name, transport)`.
  - `open()`: discover, falling back to initialize, then list the tools (paginated), then
    subscribe if the server declares `listChanged`.
  - `call(tool, arguments) -> CallResult(text, error, request, response)`, with the 30 s
    timeout, `x-mcp-header` mirroring and result conversion.
  - The state, the reason, the log and the 10 s connect timeout.
- `mcp/servers_file.py`: pydantic models of the file (data-model.md).
  - `load(path) -> Entries | error`;
  - `${VAR}` resolution;
  - the address host check;
  - `secrets(entry)`.
- `mcp/host.py`: `Host(file_path, http_client)`.
  - `start()` and `close()`; `reload()` and `reconnect(name)`;
  - `servers()` for the API, and `secrets()`;
  - `resolve(config_names) -> dict[str, HostTool]`, raising `ToolsUnavailable(reason)`;
  - `HostTool`: the config name, server, description, parameters, `schema(model_name)` and
    `call(arguments)`;
  - `model_names(tools)`, as in research §4.
- `mcp/lab_server.py`: `LAB = Server("glasshouse", …, [CALCULATOR, WEATHER])`.
- `mcp/notes.py`: the notes tools and `main()` with `--folder`.
- `tools/base.py`: `Tool` keeps `name`, `description`, `parameters` and `fn` as a server-side
  definition. `scopes` goes.
- `tools/catalog.py`: removed. `known_tool` becomes a form check:
  `^(calculator|get_weather|[a-z][a-z0-9-]{0,29}/[A-Za-z0-9_.-]{1,64})$`.
- `agents/steps.py`:
  - `chat(tools=…)` takes `HostTool`s and offers each under its model name;
  - `call_tool(ctx, tools: dict[model name → HostTool], call, …)` awaits `tool.call` and sets
    the MCP attributes;
  - the span node stays `tool:<config name>`.
- `agents/react.py`, `workflows/routing.py`, `blocks/run.py`, `blocks/model.py` and
  `agents/registry.py`:
  - tools come from a `tools` argument the run passes in, resolved by the host, instead of
    `TOOLS`;
  - `granted_scopes` goes;
  - `ModelBlock.tools` allows up to 6;
  - `came_from` maps model names back to config names.
- `runs.py`:
  - `new_run` collects the config's tool names (`tool_names` for blocks, `tools` for ReAct,
    route tools for routing) and resolves them;
  - `execute_run` passes the resolved tools and the host's secrets to the agent and the tracer.
- `api.py`:
  - `create_app(…, host: Host | None = None)`: the default is a host with only the lab's
    server, so existing tests are unchanged;
  - a lifespan for `start()` and `close()`;
  - `POST /mcp`, and `GET`/`DELETE /mcp` returning 405;
  - `GET /mcp/servers`, `POST /mcp/servers/{name}/reconnect` and `POST /mcp/reload`;
  - `GET /tools` from the host;
  - `POST /runs` answers 409 on `ToolsUnavailable`.
- `main.py`: builds the host from `Settings` (`MCP_SERVERS_FILE` or the lookup order).
- `config.py`: `mcp_servers_file`.
- `village/`: block agents are built with no tools. Unchanged otherwise.
- `backend/mcp.json`: the default file with the notes server.

### Frontend

- `lib/api.ts`:
  - `ToolInfo.server`;
  - `McpServer` and `McpServers` types;
  - `listServers()`, `reconnectServer(name)` and `reloadServers()`.
- `lib/tools.ts` (+ test):
  - `groupTools(tools)` by server, the lab first;
  - `toolLabel(tool)`;
  - `unavailableTools(configNames, tools)`;
  - `stateLabel(server)`.
- `components/ToolsView.tsx`: the server list with state, tools and the last connect's
  messages, plus the Reconnect and Reload buttons.
- `app/page.tsx`: a Tools view beside Agents and Village.
- Builder pickers (`builder/AgentSettings.tsx`, `BlockSettings.tsx`, `NodeSettings.tsx`, as they
  pick tools): an `<optgroup>` per server, unavailable tools marked, and up to 6 tools on a
  model-call block.

### Tests

- **Backend**:
  - `test_mcp_jsonrpc.py`;
  - `test_mcp_server.py`: both eras, errors, arguments;
  - `test_mcp_client.py`: discovery and fallback, pagination, result conversion, timeouts,
    `x-mcp-header`, list_changed, all over `InProcess` and `MockTransport`;
  - `test_mcp_stdio.py`: the notes server and a legacy script as subprocesses;
  - `test_mcp_servers_file.py`;
  - `test_mcp_host.py`: resolve, model names, reload, failures;
  - `test_mcp_http.py`: `/mcp`, Origin, headers, 405;
  - `test_mcp_notes.py`.
- **Existing tests**: they keep their scripted tool calls (`calculator`). Tests of `TOOLS` and
  scopes are rewritten against the lab's server.
- **Frontend**: `tools.test.ts`.

## Project Structure

```text
backend/src/agent_lab/mcp/__init__.py, jsonrpc.py, server.py, transports.py, client.py,
    servers_file.py, host.py, lab_server.py, notes.py (new)
backend/src/agent_lab/tools/base.py, calculator.py, weather.py (catalog.py removed)
backend/src/agent_lab/agents/steps.py, react.py, registry.py, config_fields.py
backend/src/agent_lab/workflows/routing.py, blocks/model.py, blocks/run.py
backend/src/agent_lab/runs.py, api.py, main.py, config.py
backend/mcp.json (new), backend/tests/test_mcp_*.py (new), backend/tests/mcp_legacy_server.py (new)
frontend/src/lib/api.ts, lib/tools.ts (+ test, new), components/ToolsView.tsx (new),
    app/page.tsx, components/builder/*Settings.tsx
README.md, docs/tools.md (new), docs/agents.md, docs/api.md, docs/development.md, AGENTS.md
```

**Structure Decision**:
- The protocol and both ends live in one new package.
- Agents see only `HostTool`s, so where a tool runs (in-process, a subprocess, an address) is
  invisible to them.

## Complexity Tracking

| Addition | Why it is needed | Simpler option rejected because |
|---|---|---|
| Two protocol eras | Servers and clients in the wild speak 2025-11-25, while new ones may be 2026-07-28 only | Either era alone leaves the owner's servers or Claude Code out (research §1) |
| An in-process transport | The host reaches the lab's own server without calling its own port | Loopback HTTP would race the server's start and double each call |
