---
description: "Task list for M16 — Tools over MCP"
---

# Tasks: M16 — Tools over MCP

**Input**: `specs/016-mcp-tools/` (plan.md, spec.md, research.md, data-model.md,
contracts/interfaces.md, quickstart.md)

**Tests**: requested by the spec (every story has an independent test, SC-001, SC-004).
`FakeLLM`, `httpx.MockTransport`, the in-process transport and the repo's own stdio scripts
only. The failing test is written first.

**Gate**: a phase is done only when `make check` passes (check its exit code); commit after each
phase. Read `frontend/AGENTS.md` before frontend work.

## Format: `[ID] [P?] [Story] Description`

## Conventions used by every task

- **No MCP library, no new dependency.** JSON-RPC, SSE parsing and the subprocess transport use
  `json`, `asyncio` and the installed `httpx` (constitution, FR-018).
- **Configs stay as they are.** `calculator` and `get_weather` keep their bare names. No stored
  config, config version, graph node id (`tool:<name>`) or golden file changes (research §4).
- **The village is untouched.** Its block agents get no tools and never touch the host. The
  village is paused and `make dev` reloads on edits; nothing here changes the village store.
- **Secrets.** Every value from a servers-file `env` or `headers` entry joins the redaction
  secrets of runs, spans, the Tools page and the connect log.
- **Manual checks** use `openai/gpt-6-luna` while the local model is off.

---

## Phase 1: Setup

- [X] T001 Create the package backend/src/agent_lab/mcp/__init__.py with a module docstring
  naming its modules (jsonrpc, server, transports, client, servers_file, host, lab_server,
  notes) and that it is the hand-written MCP layer for both ends.
  - No behaviour change; `make check` passes unchanged.

## Phase 2: Foundational — the protocol core

Every story needs these. Nothing is wired into agents yet.

- [X] T002 [P] JSON-RPC in backend/src/agent_lab/mcp/jsonrpc.py, tests in
  backend/tests/test_mcp_jsonrpc.py.
  - Builders `request(id, method, params)`, `notification(method, params)`,
    `result(id, value)` and `error(id, code, message, data=None)`.
  - `is_response(msg)`, `is_notification(msg)` and `is_request(msg)`; a message without
    `"jsonrpc": "2.0"` is none of them.
  - Codes `PARSE_ERROR = -32700`, `INVALID_REQUEST = -32600`, `METHOD_NOT_FOUND = -32601`,
    `INVALID_PARAMS = -32602`, `INTERNAL_ERROR = -32603`, `HEADER_MISMATCH = -32020`,
    `UNSUPPORTED_VERSION = -32022`.
  - `RpcError(Exception)` with `code`, `message`, `data`.
  - Constants `MODERN = "2026-07-28"` and `LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26",
    "2024-11-05")` and the `_meta` keys `io.modelcontextprotocol/protocolVersion`,
    `…/clientCapabilities`, `…/clientInfo`, `…/serverInfo`.

- [X] T003 The server core in backend/src/agent_lab/mcp/server.py, tests in
  backend/tests/test_mcp_server.py (contracts "MCP messages the lab answers").
  - `Server(name, version, tools: list[Tool])` and `async handle(message) -> dict | None`
    (None for notifications).
  - `server/discover` → `{resultType: "complete", supportedVersions: ["2026-07-28",
    "2025-11-25"], capabilities: {tools: {}}, _meta: {"io.modelcontextprotocol/serverInfo":
    {name, version}}}`.
  - `initialize` → `{protocolVersion, capabilities: {tools: {}}, serverInfo}`: the client's
    version if it is one of the four legacy revisions, else `2025-11-25`.
    `notifications/initialized` → None.
  - `tools/list` → `{resultType: "complete", tools: [{name, description, inputSchema}],
    ttlMs: 3600000, cacheScope: "public"}`, no pagination.
  - `tools/call` → `{resultType: "complete", content: [{type: "text", text}], isError}`. A tool
    that raises `ToolError` gives `isError: true` with its message.
  - Move `_parse_arguments`' missing/unexpected check from backend/src/agent_lab/agents/steps.py
    here: arguments that are not an object, or that miss or add parameters, give `isError: true`
    naming them, with today's `ToolError` text.
  - A request with `_meta` protocolVersion other than `2026-07-28` → `-32022` with
    `data: {supported: ["2026-07-28"], requested}`. An unknown tool → `-32602`. Any other method →
    `-32601`.
  - `async run_stdio(server)`: reads stdin lines, answers on stdout, one JSON message per line;
    a line that is not JSON gets `-32700`; logs go to stderr only.
  - Tests: both eras, each error, the argument errors with the calculator, a tool that raises.

- [X] T004 The transport shape and the in-process transport in
  backend/src/agent_lab/mcp/transports.py.
  - The shape every transport has: `async send(message) -> response`, `async notify(message)`,
    `on_notice(callback)` and `async close()`. A transport that loses its peer raises
    `TransportClosed`.
  - `InProcess(server)`: hands the message dict (a deep copy) to `server.handle`.
  - Tested through T005.

- [X] T005 The client connection in backend/src/agent_lab/mcp/client.py, tests in
  backend/tests/test_mcp_client.py over `InProcess` (research §1, §6; contracts "Tool result
  text for the model").
  - `Connection(name, transport, *, connect_timeout=10, call_timeout=30, discover_timeout=3)`.
  - `open()`:
    - modern: `server/discover` with `_meta` (protocolVersion `2026-07-28`, clientCapabilities
      `{}`, clientInfo `{"name": "glasshouse", "version": "0.1.0"}`); a `-32022` fails the
      connection with that reason and no fallback;
    - legacy on any other error or no answer within 3 s: `initialize` (`2025-11-25`), accept only
      a revision in `LEGACY`, then `notifications/initialized`;
    - then `tools/list`, following `nextCursor`; a tool without an object `inputSchema` is
      dropped;
    - fields `state` (`connecting` → `connected` | `failed`), `reason`, `era`
      (`modern` | `legacy`), `protocol_version`, `server_info`, `tools`, `log`;
    - the whole open within 10 s, else failed with `timed out after 10 s`.
  - `log`: the messages of the last open as `{"direction": "out"|"in", "message"}`, "at most 20,
    each cut at 4,000 characters".
  - `call(tool, arguments) -> CallResult(text, error: bool, request, response)`:
    - `tools/call` with `_meta` for modern, without for legacy; ids unique per connection;
    - text items joined by blank lines; `[image: <mimeType>]`, `[audio: <mimeType>]`,
      `[resource link: <uri>]`, an embedded resource's text or `[resource: <uri>]`; only
      `structuredContent` → its JSON;
    - `isError: true` → `error: <text>`; a JSON-RPC error → `error: <message>`;
      `resultType: "input_required"` → `error: the tool asked for input, which the lab does not
      support`;
    - no answer in 30 s → `error: timed out after 30 s`, `response` None;
    - `TransportClosed` → `error: server "<name>" is unavailable`, `response` None, and the
      connection becomes `failed`;
    - text over 20,000 characters is cut and followed by `[cut: N more characters]`.
  - Tests: a modern open against `Server`; a legacy-only handler (a small fake in the test that
    answers `server/discover` with `-32601`) falls back; a `-32022` answer fails; a silent
    discover falls back after 3 s (pass a short timeout); pagination; every row of the result
    table; the cut; the timeout; the dead connection.

**Checkpoint**: `make check`; commit "M16: MCP protocol core".

---

## Phase 3: User Story 1 — The built-in tools over MCP (P1) 🎯 MVP

**Goal**: every tool call goes through the host to the lab's own server, with MCP spans.

**Independent test**: the ReAct sample with the scripted fake model gives the same answer and
tool results as before (SC-002); each tool span carries `lab.mcp.server: lab`, the request and
the response.

- [X] T006 [US1] The lab's server in backend/src/agent_lab/mcp/lab_server.py:
  `LAB = Server("glasshouse", "0.1.0", [CALCULATOR, WEATHER])`. Test in
  backend/tests/test_mcp_server.py: it lists `calculator` and `get_weather` with today's
  descriptions and parameters.

- [X] T007 [US1] The host, lab only, in backend/src/agent_lab/mcp/host.py, tests in
  backend/tests/test_mcp_host.py (research §4, data-model "Tool").
  - `Host(file_path=None, http_client=None)`; `start()` opens `lab` over `InProcess(LAB)`
    (kind `internal`, target `built in`) and `close()` closes every connection.
  - `HostTool`: `server`, `name`, `config_name`, `description`, `parameters` (the input
    schema), `header_params`, `schema(model_name)` (the chat tool schema under that name), and
    `async call(arguments) -> CallResult`.
  - `resolve(config_names) -> dict[str, HostTool]` keyed by config name:
    - `calculator`, `get_weather` and `lab/<tool>` → the lab's tool (config name as written);
    - `server/tool` → that server's tool;
    - raises `ToolsUnavailable("server \"notes\" is not connected")` or
      `ToolsUnavailable("tool \"notes/x\" is not listed by \"notes\"")`.
  - `model_names(tools) -> dict[model name, HostTool]`: the tool's own name when it is unique
    among the offered tools and matches `^[A-Za-z0-9_-]{1,64}$`; otherwise `server__tool` with
    other characters replaced by `_`, cut to 64 and made unique with a numeric suffix.
  - `tools()` for `GET /tools`: every tool of every connected server, lab first.
  - Tests: resolve of bare, `lab/` and unknown names; both error texts; model names for a clash
    (`a/search`, `b/search`), for `my.tool`, and for a 70-character name.

- [X] T008 [US1] Tools without the catalog.
  - backend/src/agent_lab/tools/base.py: `Tool` drops `scopes`.
  - Remove backend/src/agent_lab/tools/catalog.py.
  - backend/src/agent_lab/agents/config_fields.py: `known_tool` checks the form only:
    `^(calculator|get_weather|[a-z][a-z0-9-]{0,29}/[A-Za-z0-9_.-]{1,64})$`, error `unknown tool
    name {name!r}: use calculator, get_weather or server/tool`.
  - Tests first in backend/tests/test_config_fields.py: `notes/write_note` and
    `lab/calculator` pass; `read_file`, `Notes/x`, `a/b/c` fail.
  - Remove `test_ungranted_tool_scopes_rejected` from backend/tests/test_blocks_run.py and the
    `catalog.TOOLS` patching in backend/tests/test_blocks_api.py (rewrite that test against the
    host: a tool that the host does not list).

- [X] T009 [US1] Tool calls through the host in backend/src/agent_lab/agents/steps.py, tests in
  backend/tests/test_steps.py (data-model "Tool span").
  - `chat(…, tools=dict[model name, HostTool])` offers `tool.schema(model_name)`.
  - `call_tool(ctx, tools: dict[model name, HostTool], call, *, caller, came_from, node_id)`:
    - the argument text must parse to a JSON object, as today; otherwise the tool result is the
      same error text as today and no request is sent;
    - an unknown model name gives today's unknown-tool text;
    - awaits `tool.call(arguments)`; the span's input is the arguments, output the result text,
      error set when `CallResult.error`;
    - attributes `mcp.method.name: "tools/call"`, `mcp.protocol.version`,
      `jsonrpc.request.id`, `lab.mcp.server`, `lab.mcp.request`, `lab.mcp.response` (None on a
      timeout or a dead connection); `gen_ai.tool.name` stays the config name;
    - the node stays `tool:<config name>` (or the tool-call block's own node).
  - Tests: a calculator call has the six attributes; a division by zero is an error span and the
    model gets the text (US1 scenario 4); the model-name → config-name mapping on a clash.

- [X] T010 [US1] Agents take resolved tools.
  - backend/src/agent_lab/agents/react.py: `ReActAgent(…, tools: dict[str, HostTool])`;
    `granted_scopes` goes.
  - backend/src/agent_lab/agents/registry.py: the ReAct `build` passes the resolved tools
    instead of `[TOOLS[t] …]`; every `build` takes `tools`.
  - backend/src/agent_lab/workflows/routing.py: `RouteSpec.tool` uses the resolved tool.
  - backend/src/agent_lab/blocks/run.py: `BlockAgent(…, tools: dict[str, HostTool] = {})`;
    `granted_scopes` goes; model-call and tool-call blocks take their tools from it, and
    `came_from` maps model names back to config names.
  - backend/src/agent_lab/blocks/model.py: `ModelBlock.tools` `max_length=6`. The tool-call
    block's argument-name check at save stays for `calculator` and `get_weather` (from
    `LAB`'s definitions); for `server/tool` it is skipped and the server reports bad arguments
    at call time.
  - backend/tests/helpers.py: a `lab_tools(*names)` helper resolving through a started lab-only
    `Host`, used where tests built agents from `TOOLS`.
  - Tests first: backend/tests/test_blocks_model.py (6 tools pass, 7 fail);
    backend/tests/test_blocks_run.py (a model-call block calling a fake server's tool by its
    `server__tool` model name records `tool:<config name>`).
  - The village's block agents are built with no tools; check backend/src/agent_lab/village/
    passes nothing new.

- [X] T011 [US1] Runs and the API resolve tools (research §8, §11).
  - backend/src/agent_lab/runs.py: a `config_tools(config)` collecting ReAct `tools`, routing
    route tools, and block tools at any depth (`tool_names`); `new_run` resolves them through
    the host before creating the run; `execute_run` passes the resolved tools to the agent.
  - backend/src/agent_lab/api.py:
    - `create_app(*, store, models, secrets=(), host: Host | None = None)`; the default is a
      lab-only `Host()`, so existing tests are unchanged;
    - a lifespan: `await host.start()`, then `await host.close()` on shutdown;
    - `POST /runs` answers `409 {"detail": <ToolsUnavailable text>}` and creates no run;
    - `GET /tools` from `host.tools()`, each with `server` added (`ToolInfo.server`).
  - Tests first in backend/tests/test_api.py: `GET /tools` lists `calculator` with
    `server: "lab"`; a builder agent naming `notes/x` with no notes server gets 409 and no run
    is stored.
  - Use `with TestClient(app)` where a test needs the lifespan.

- [X] T012 [US1] Behaviour unchanged (SC-001, SC-002).
  - backend/tests/test_templates.py and backend/tests/golden/: the ReAct sample run gives the
    same answer and tool results; no golden file changes.
  - A test in backend/tests/test_react.py: the tool spans of the sample carry
    `lab.mcp.server: "lab"` and a request whose `params.name` is `calculator`.
  - A saved builder agent with a tool-call block for `calculator` (US1 scenario 2) runs and
    gives today's result, in backend/tests/test_blocks_api.py.

**Checkpoint**: `make check`; commit "M16: built-in tools over MCP".

---

## Phase 4: User Story 2 — The owner's own servers (P2)

**Goal**: servers from the owner's file, a Tools page, and pickers across servers.

**Independent test**: a fake HTTP server (`MockTransport`) listed in a servers file shows as
connected with its tools on `GET /mcp/servers`; a builder agent picking one of its tools calls
it in a run and the result reaches the model.

- [X] T013 [P] [US2] The servers file in backend/src/agent_lab/mcp/servers_file.py, tests in
  backend/tests/test_mcp_servers_file.py (data-model "Servers file", research §5).
  - Pydantic models with `extra="forbid"` ("Unknown fields are refused"):
    - the name key `^[a-z][a-z0-9-]{0,29}$`, not `lab`, "at most 20 entries";
    - `type`: `"stdio"` | `"http"`, optional: `http` when `url` is set, else `stdio`;
    - `command`: stdio, required, "1–500 characters"; `args`: "at most 50, each at most 500
      characters"; `env`: map of name → value;
    - `url`: http, required, `http` or `https`; `headers`: map; `allowHosts`: list of host
      names.
  - `find(settings_path) -> Path`: `MCP_SERVERS_FILE`, else `backend/data/mcp.json`, else
    `backend/mcp.json`.
  - `load(path) -> (entries, error)`: an unreadable or invalid file is one error text.
  - `resolve_values(entry, environ)`: `${NAME}` in `env` and `headers` from the environment;
    a missing variable fails that entry with the reason.
  - `check_host(entry)`: host `127.0.0.1`, `localhost` or `::1`, or listed in `allowHosts`;
    otherwise refused with `host "x" is not this computer; add it to allowHosts to allow it`.
  - `secrets(entry)`: the resolved `env` and `headers` values.
  - `target(entry)`: the command line or URL, redacted.
  - Tests: each rule above, a typo field, a missing variable, a remote host refused and allowed.

- [X] T014 [P] [US2] The stdio transport in backend/src/agent_lab/mcp/transports.py, the legacy
  script backend/tests/mcp_legacy_server.py and tests in backend/tests/test_mcp_stdio.py
  (research §2).
  - `Stdio(command, args, env, cwd)`: `asyncio.create_subprocess_exec` with env `PATH`, `HOME`
    and the entry's `env` only; cwd the backend folder.
  - One reader task: responses go to waiting futures by id; notifications go to `on_notice`; a
    line that is not a JSON-RPC message is ignored and logged.
  - stderr kept as the last 20 lines, given in the failure reason.
  - A process that exits raises `TransportClosed` on every waiting and later send.
  - `close()`: close stdin, wait 2 s, terminate, kill after 2 more seconds.
  - backend/tests/mcp_legacy_server.py: a 2025-11-25-only stdio server (answers `initialize`,
    `tools/list`, `tools/call`; `server/discover` gets `-32601`; tools `echo`, `env` (the sorted
    names of its environment, so FR-003 is testable) and `notify` (sends
    `notifications/tools/list_changed`)).
  - Tests: legacy fallback over stdio; the child sees only `PATH`, `HOME` and named variables
    (FR-003); a missing command fails with the reason; killing the child makes a call return
    `error: server "x" is unavailable`; `close()` leaves no process.

- [X] T015 [P] [US2] The HTTP transport in backend/src/agent_lab/mcp/transports.py, tests in
  backend/tests/test_mcp_client.py with `httpx.MockTransport` (research §2, contracts "HTTP
  request headers").
  - `Http(url, headers, client: httpx.AsyncClient)`: POST with `Accept: application/json,
    text/event-stream` and `Content-Type: application/json` plus the entry's headers.
  - Modern: `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method`, `Mcp-Name` on `tools/call`, and
    `Mcp-Param-{name}` for arguments the tool's schema marks `x-mcp-header`; non-ASCII values as
    `=?base64?…?=`. A tool with an invalid `x-mcp-header` declaration is dropped from the list.
  - Legacy: `MCP-Protocol-Version` after `initialize`, and `Mcp-Session-Id` when the server set
    one.
  - A JSON body is read directly; an SSE body is read event by event until the message with the
    request's id, passing notifications on.
  - A notification expects 202. A 400/404/405 with a body that is not a recognised modern error
    counts as "legacy" during discover.
  - A connection error raises `TransportClosed`.
  - Tests: a modern fake server (headers checked), a legacy fake with a session id, an SSE
    answer with a notification first, `x-mcp-header` mirroring, a 404 on discover falling back.

- [X] T016 [US2] The full host in backend/src/agent_lab/mcp/host.py, tests in
  backend/tests/test_mcp_host.py (data-model "State changes", research §3, §11).
  - `Host(file_path, http_client, environ=os.environ)` reads the file at `start()`: `lab` at
    once, every entry in the background (`asyncio.create_task`), each within 10 s; the lab's
    start never waits.
  - Entries build `Stdio` or `Http`; a refused host, a missing variable or a bad entry is
    `failed` with the reason.
  - `servers()` → the `GET /mcp/servers` body (contracts): `file`, `file_error`, and per server
    `name`, `kind`, `target`, `state`, `reason`, `era`, `protocol_version`, `server_info`,
    `watching`, `tools`, `log`, all redacted with `secrets()`.
  - `secrets()`: every entry's resolved values.
  - Tools changed (FR-016): modern servers declaring `tools.listChanged` get
    `subscriptions/listen` with `{"notifications": {"toolsListChanged": true}}` (stdio and HTTP);
    legacy stdio notices arrive unasked; on each `notifications/tools/list_changed` the host
    lists again. Legacy HTTP is `watching: false`.
  - `reconnect(name)`: re-read that entry and connect it again; unknown name → `KeyError`.
    `reload()`: re-read the file, connect new and changed entries, close removed ones, leave
    unchanged connected ones alone.
  - A call that finds the connection dead marks it `failed` (US2 scenario 4).
  - `close()` stops every local program (FR-017).
  - Tests: a file with a fake HTTP server and the legacy stdio script both connect (US2
    scenario 1); a nonexistent command fails while the others work (scenario 2); a remote host
    refused (scenario 5); an invalid file gives `file_error` and `lab` still works; reload
    adds, changes and removes; a list-changed notice re-lists; a header secret is absent from
    `servers()`.

- [X] T017 [US2] The servers API and secrets in runs.
  - backend/src/agent_lab/config.py: `mcp_servers_file` from `MCP_SERVERS_FILE` (default "").
  - backend/src/agent_lab/main.py: `Host(find(settings.mcp_servers_file), httpx.AsyncClient())`
    passed to `create_app`.
  - backend/src/agent_lab/api.py:
    - `GET /mcp/servers` → `host.servers()`;
    - `POST /mcp/servers/{name}/reconnect` → 202 with that server's entry (state
      `connecting`), 404 for an unknown name;
    - `POST /mcp/reload` → 202 with the `GET /mcp/servers` body;
    - runs use `secrets + host.secrets()` for `new_run`, `execute_run` and the tracer.
  - Tests first in a new backend/tests/test_mcp_api.py: the
    three endpoints; a run calling a fake HTTP tool whose entry has
    `Authorization: Bearer ${TOKEN}` stores no span containing the token (SC-004); the US2
    independent test end to end with `FakeLLM`.

- [X] T018 [P] [US2] Frontend data and logic.
  - frontend/src/lib/api.ts: `ToolInfo.server: string`; types `McpServer` (fields as in
    `GET /mcp/servers`) and `McpServers` (`file`, `file_error`, `servers`); `listServers()`,
    `reconnectServer(name)`, `reloadServers()`.
  - New frontend/src/lib/tools.ts with tests first in frontend/src/lib/tools.test.ts:
    - `groupTools(tools)`: by server, `lab` first, then by name;
    - `toolLabel(tool)`: the config name;
    - `unavailableTools(configNames, tools)`: names no connected server offers;
    - `stateLabel(server)`: `connected`, `connecting…`, `failed: <reason>`.
  - Update fixtures in frontend/src/lib/blocks.test.ts for `server`.

- [X] T019 [US2] The Tools view (FR-005, FR-011).
  - New frontend/src/components/ToolsView.tsx: one card per server with name, kind, target,
    state and reason, revision, server name and version, "not watched for changes" when
    `watching` is false, its tools (name, description, arguments), and a collapsed "Last
    connect" list of the log messages; a Reconnect button per server and a Reload button; the
    `file` and `file_error` at the top. Polls `listServers()` while any server is `connecting`.
  - frontend/src/app/page.tsx: the view state becomes `"agents" | "village" | "tools"`, with a
    Tools tab; switching away from Agents keeps the `mayLeave()` rule. Refresh `listTools()`
    after a reconnect or reload.

- [X] T020 [US2] Pickers across servers (FR-006).
  - frontend/src/components/builder/ItemList.tsx `ToolPicker` and the model-call block's list in
    frontend/src/components/builder/BlockSettings.tsx: a small heading per server from
    `groupTools`; a chosen tool that `unavailableTools` returns is still shown, marked
    "(unavailable)".
  - The tool-call block select (BlockSettings.tsx `ToolFields`) and the routing select
    (frontend/src/components/builder/NodeSettings.tsx `ToolSelect`): an `<optgroup>` per
    server, and the chosen unavailable tool as a marked option.

**Checkpoint**: `make check`; commit "M16: the owner's MCP servers and the Tools page".

---

## Phase 5: User Story 3 — The notes server (P3)

**Goal**: a second, separate server ships with the lab.

**Independent test**: the notes server started as a subprocess through the host writes, lists
and reads a note, and refuses a name reaching outside its folder.

- [X] T021 [US3] The notes server in backend/src/agent_lab/mcp/notes.py, tests in
  backend/tests/test_mcp_notes.py over `Server.handle` (data-model "Note", research §10).
  - `python -m agent_lab.mcp.notes --folder PATH`; server name `glasshouse-notes`; the folder
    is created if missing; `run_stdio`.
  - `list_notes()`: names with sizes; `read_note(name)`; `write_note(name, text)` creates or
    replaces.
  - Names `^[A-Za-z0-9][A-Za-z0-9 _-]{0,59}$`, stored as `<name>.md`; a resolved path whose
    parent is not the folder is refused (symlinks).
  - Text "at most 20,000 characters"; "at most 200 notes in the folder"; writes go to a
    temporary file in the folder and replace the note.
  - Errors are tool errors (`isError: true`) naming the rule.
  - Tests: write, list, read; `../secret`, `/etc/passwd` and a symlink pointing out are refused
    and nothing outside is touched (US3 scenario 2); 20,001 characters refused (scenario 3); the
    201st note refused.

- [X] T022 [US3] The default servers file and the notes server over stdio.
  - New backend/mcp.json: `{"mcpServers": {"notes": {"command": "uv", "args": ["run",
    "--no-sync", "python", "-m", "agent_lab.mcp.notes", "--folder", "data/notes"]}}}`.
  - Tests in backend/tests/test_mcp_stdio.py: a host whose file lists the notes server as
    `sys.executable -m agent_lab.mcp.notes --folder <tmp>` connects it (modern era); a write in
    one run is read back in a later run with `FakeLLM` (US3 scenario 1); `find` falls back to
    backend/mcp.json when neither `MCP_SERVERS_FILE` nor backend/data/mcp.json exists (FR-014).

**Checkpoint**: `make check`; commit "M16: the notes server".

---

## Phase 6: User Story 4 — Other MCP clients (P4)

**Goal**: outside clients reach the lab's server at `POST /mcp`.

**Independent test**: a `Connection` over `Http` to the app (`httpx.ASGITransport`) discovers,
lists and calls both built-ins, in both eras.

- [X] T023 [US4] `POST /mcp` in backend/src/agent_lab/api.py, tests in
  backend/tests/test_mcp_http.py (research §9, contracts "`POST /mcp`").
  - `Origin` present and not `http://127.0.0.1:3000` or `http://localhost:3000` → 403.
  - Modern requests: `MCP-Protocol-Version` must match `_meta`, `Mcp-Method` the method and
    `Mcp-Name` the tool on `tools/call`; otherwise 400 with `-32020`.
  - `LAB.handle(message)`; a response → `200 application/json`; a notification → 202; `-32601`
    → 404. `Mcp-Session-Id` is ignored and none is minted.
  - `GET /mcp` and `DELETE /mcp` → 405.
  - Tests: each answer above; a foreign `Host` header is refused by the existing middleware.

- [X] T024 [US4] The outside-client test in backend/tests/test_mcp_http.py: a `Connection` over
  `Http(url="http://127.0.0.1/mcp", client=httpx.AsyncClient(transport=httpx.ASGITransport(app)))`
  opens (modern), lists both tools and calls `calculator` (`2**10 - 24` → `1000`) and
  `get_weather`; the same with the modern discover refused so it goes legacy.

**Checkpoint**: `make check`; commit "M16: the lab's MCP server over HTTP".

---

## Phase 7: Polish & cross-cutting

- [X] T025 [P] Docs.
  - New docs/tools.md: the servers file (shape, lookup order, `${VAR}`, `allowHosts`, limits),
    the Tools page, naming (`calculator`, `server/tool`, the model's names), the notes server,
    the two protocol eras, `POST /mcp` and `claude mcp add --transport http glasshouse
    http://127.0.0.1:8000/mcp`.
  - docs/agents.md (tool names, 6 tools per model-call block), docs/api.md (`/mcp`,
    `/mcp/servers`, reconnect, reload, `GET /tools` `server`, `POST /runs` 409),
    docs/development.md (the `backend/mcp.json` default, `MCP_SERVERS_FILE`), README.md (the
    milestone, the Tools page), AGENTS.md (the `mcp/` package, no MCP library, tests use the
    in-process transport, `MockTransport` and the repo's stdio scripts).

- [X] T026 Timing (plan performance goals): measure a calculator call through the in-process
  path (< 5 ms added) and a notes stdio call (< 100 ms) once with a short script in the
  scratchpad; record the figures in specs/016-mcp-tools/quickstart.md under "Results".

- [X] T027 Manual checks 1–6 of specs/016-mcp-tools/quickstart.md with `openai/gpt-6-luna`
  (SC-003, SC-005, SC-006); record results in quickstart.md. Commit "M16 manual check results".

---

## Dependencies

- **Phase 1 → Phase 2 → US1**: US1 needs the protocol core.
- **US2** needs US1 (the host and the rewired agents). T013, T014 and T015 can run in parallel;
  T016 needs all three; T017 needs T016; T018 can start with T017's contract and runs in parallel
  with T016–T017; T019 and T020 need T018.
- **US3** needs T014 (stdio) and T016 (host with a file). T021 alone needs only Phase 2.
- **US4** needs Phase 2 and T011 (the app); T024 also needs T015 (`Http`). It is independent of
  US2's frontend and of US3.
- **Polish** after the stories it documents.

## Parallel examples

- **Phase 2**: T002 alongside T003 (different files; T003 imports T002's names, so write T002's
  constants first).
- **US2**: T013 (servers_file.py), T014 (Stdio) and T015 (Http) together; T018 (frontend) while
  T016–T017 are built.
- **US3 and US4**: T021 and T023 together once US1 is done.

## Implementation strategy

- **MVP**: Phases 1–3. Every tool call goes over MCP to the lab's own server, with traced
  messages, and nothing the owner had changes. Stop and check SC-001 and SC-002.
- **Then** US2 (the lab opens to the owner's servers), US3 (a second server ships), US4 (outside
  clients), each a commit with `make check` green.
- **Last** docs, timing and the manual checks on `openai/gpt-6-luna`.
