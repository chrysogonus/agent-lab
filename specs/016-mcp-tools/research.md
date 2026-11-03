# Research: M16 — Tools over MCP

The starting point:
- **Tools**: two tools are Python objects in `tools/catalog.py` (`TOOLS`). `steps.call_tool`
  calls `tool.fn(**args)` and records a tool span.
- **Where tools are named**: the ReAct template (`tools: ["calculator", "get_weather"]`), the
  routing template (one tool per route), the builder's model-call block (at most 2) and its
  tool-call block. `known_tool` checks names against `TOOLS` when a config is saved.
- **Scopes**: `Tool.scopes` and `granted_scopes` exist, but nothing grants a scope and both tools
  have none.
- **The app**: no FastAPI lifespan. `TrustedHostMiddleware` allows only `127.0.0.1` and
  `localhost`, and CORS allows the frontend's origins.

## 1. Which MCP revision

- **Decision**: the lab speaks **2026-07-28**, the current revision, and falls back to
  **2025-11-25** (and older revisions back to 2024-11-05 on stdio) for servers that do not
  speak it. The lab's own server and the notes server answer both eras.
- **What changed in 2026-07-28** (from the official changelog and the transport, versioning,
  discover, tools and subscriptions pages):
  - no `initialize` handshake and no sessions;
  - every request carries `_meta["io.modelcontextprotocol/protocolVersion"]` and
    `…/clientCapabilities` (and SHOULD carry `…/clientInfo`);
  - `server/discover` returns `supportedVersions`, `capabilities` and `serverInfo`, and every
    server MUST implement it;
  - results carry `resultType` (`"complete"`, and a missing field means complete);
  - `tools/list` results carry `ttlMs` and `cacheScope`;
  - `notifications/tools/list_changed` reaches only a client with an open `subscriptions/listen`.
- **Telling the eras apart** (as the spec prescribes): send `server/discover` first.
  - A discover result means a modern server.
  - A recognised modern error (`-32022` unsupported version) means modern with no common
    version. The server fails with that reason and there is no fallback.
  - Any other error, or no answer within 3 seconds, means a legacy server. The lab sends
    `initialize` (2025-11-25), accepts the version the server answers with if it is one the lab
    knows, then sends `notifications/initialized`.
  - Over HTTP, a 400/404/405 with an unrecognised body means legacy as well.

  The era is kept for the connection's lifetime.
- **Why**: Claude Code and other clients may still speak 2025-11-25 in November 2026, and so may
  most third-party servers. Answering both eras on the server side costs one extra method
  (`initialize`, plus accepting `notifications/initialized`), because legacy session ids are
  optional and the lab mints none.
- **Alternatives**:
  - 2025-11-25 only: rejected, because new servers may be modern-only, and modern-only servers
    reject legacy clients.
  - 2026-07-28 only: rejected, because most servers the owner can install today may be legacy.

## 2. Transports

- **stdio** (local programs): the lab starts the program with `asyncio.create_subprocess_exec`.
  - It writes one JSON message per line to stdin and reads one per line from stdout.
  - stderr is kept as the last 20 lines, shown when the server fails.
  - A stdout line that is not a JSON-RPC message is ignored and logged.
  - One reader task routes responses to waiting calls by id, and passes notifications on.
  - Ids are unique per connection, so concurrent runs share one process safely.
  - Shutdown: close stdin, wait 2 seconds, terminate, then kill after 2 more seconds.
- **Streamable HTTP** (addresses): one `httpx.AsyncClient`, injected so tests use
  `httpx.MockTransport`. Each request is a POST.
  - Headers: `Accept: application/json, text/event-stream` and
    `Content-Type: application/json`.
  - Modern servers also get `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` (for
    `tools/call`). Non-ASCII values are encoded as `=?base64?…?=`.
  - Legacy servers get `MCP-Protocol-Version` after `initialize`, and the `Mcp-Session-Id` when
    the server set one.
  - A JSON response is read directly. An SSE response is read event by event until the message
    with the request's id; notifications on the way are passed on.
- **In-process** (the lab's own server): the host hands the same JSON-RPC message objects to the
  server's `handle(message)` function. There is no socket, so the host never calls its own HTTP
  port and the lab's start never waits on itself. It is still the same protocol path: the same
  messages, the same client, the same spans.
- **Alternatives**: the lab reaching its own server over loopback HTTP. Rejected: at start the
  host would connect before uvicorn accepts connections, and a run would hold two requests for
  every tool call.

## 3. The tools-changed notice (FR-016)

- **Decision**: when a server declares `tools.listChanged`:
  - **Modern servers**: the lab opens `subscriptions/listen` with `toolsListChanged: true`. On
    stdio its notices arrive on stdout. Over HTTP it is a long-lived POST whose SSE stream
    carries them.
  - **Legacy stdio servers**: send `notifications/tools/list_changed` on stdout unasked.
  - On each notice the lab lists the tools again.
  - **Legacy HTTP servers** would need a separate GET stream, so they are not watched. The
    Tools page says so, and Reconnect lists their tools again.
- **Why**: covers every transport except a deprecated-era corner, without a second stream
  type.

## 4. Naming tools

- **The names the owner and configs use**:
  - The lab's built-ins keep their bare names, `calculator` and `get_weather`. `lab/calculator`
    is accepted as the same tool.
  - Every other tool is `server/tool`.
  - Stored configs, config versions, graph node ids (`tool:<name>`) and the golden template file
    stay unchanged.
- **The name the model sees**:
  - the tool's own name, when it is unique among the tools offered in that call and matches
    `^[A-Za-z0-9_-]{1,64}$`;
  - otherwise `server__tool`, with other characters replaced by `_`, cut to 64 characters and
    made unique with a numeric suffix.

  The host keeps the map back to the config name, so spans and graph edges use config names.
- **Server names**: `^[a-z][a-z0-9-]{0,29}$`, with `lab` reserved.
- **Why**: existing agents and the scripted fake-model tests keep calling `calculator`.
  Function-calling APIs reject `/` in tool names.
- **Alternatives**: rewriting stored configs to `lab/calculator`. Rejected: it changes every
  config version and the graphs of stored runs.

## 5. The servers file

- **Decision**: JSON in the shape other MCP clients use, so an entry can be pasted:

  ```json
  {"mcpServers": {
    "notes": {"command": "uv", "args": ["run", "--no-sync", "python", "-m", "agent_lab.mcp.notes",
              "--folder", "data/notes"]},
    "docs": {"type": "http", "url": "http://127.0.0.1:9000/mcp",
             "headers": {"Authorization": "Bearer ${DOCS_TOKEN}"}}
  }}
  ```

  - **Where it is**:
    - `MCP_SERVERS_FILE` if set;
    - else `backend/data/mcp.json` (the owner's file; `backend/data/` is git-ignored);
    - else the committed default `backend/mcp.json`, which lists only the notes server.
  - **Values**: `${NAME}` in `env` and `headers` values is taken from the lab's environment
    (`.env` is already loaded by `make dev`). A missing variable fails that server with the
    reason. Every value from `env` and `headers` joins the run's redaction secrets.
  - **Local programs** get `PATH`, `HOME` and the entry's `env`, nothing else. Their working
    folder is the backend folder.
  - **Addresses** must have host `127.0.0.1`, `localhost` or `::1`, unless the entry lists the
    host in `"allowHosts"`. Only `http` and `https` are accepted.
  - **Limits**: at most 20 servers. An invalid file is one error shown on the Tools page; the lab
    server still works.
- **Alternatives**: TOML (`tomllib`). Rejected because no other MCP client uses it, so entries
  could not be pasted.

## 6. Calling a tool and its result

- **Arguments**: the model's argument text must parse to a JSON object, as today. The server
  checks the arguments themselves; the lab's server keeps today's missing/unexpected check.
- **The call**: `tools/call` with `name` and `arguments`, plus `_meta` for modern servers. Over
  modern HTTP, arguments that the tool's schema marks `x-mcp-header` are mirrored into
  `Mcp-Param-{name}` headers, and tools with an invalid `x-mcp-header` declaration are dropped
  from the list (the spec's MUST).
- **The result text for the model**:
  - text items joined by blank lines;
  - `image` → `[image: image/png]`;
  - `audio` → `[audio: …]`;
  - `resource_link` → `[resource link: uri]`;
  - embedded `resource` → its text, or `[resource: uri]`;
  - with no content but `structuredContent`, its JSON.

  The text is cut at 20,000 characters with `[cut: N more characters]`.
- **Failures**: each of these becomes the tool result `error: …`, and the span's error is set.
  - `isError: true`;
  - a JSON-RPC error;
  - no answer within 30 seconds (`timed out after 30 s`);
  - a dead connection (`server notes is unavailable`). This also marks the server failed.
- **`input_required` results**: answered with the error "the tool asked for input, which the lab
  does not support".

## 7. Tracing (FR-010, FR-011)

- **Decision**: `steps.call_tool` keeps the tool span: input the arguments, output the result
  text, and the node `tool:<config name>` or the tool-call block's own node. New attributes:
  - `mcp.method.name: "tools/call"`;
  - `mcp.protocol.version`;
  - `jsonrpc.request.id`;
  - `lab.mcp.server`;
  - `lab.mcp.request` and `lab.mcp.response`: the JSON-RPC messages, as sent and received.

  Redaction runs over all of it with the run's secrets plus the host's.
- **The handshake and tool listing** (discover or initialize, the listings) happen outside any
  run. Each connection keeps the messages of its last connect: at most 20, each cut at 4,000
  characters, redacted. The Tools page shows them.
- **Why**: a span needs a run. Connecting is not part of a run, but its messages are the lesson.

## 8. Checking tools before a run (FR-008)

- **Decision**: `POST /runs` resolves every tool the config names (ReAct tools, routing tools,
  and block tools at any depth). If one's server is not connected, or the server does not list
  it, the endpoint answers 409 with `server "notes" is not connected` or
  `tool "notes/x" is not listed by "notes"`, and no run is created.
- **Saving a config** only checks the name's form: a built-in bare name, or `server/tool`.
  Saving an agent while its server is down still works.
- **The per-tool `scopes` and `granted_scopes` are removed.** Nothing granted them, and the
  servers file is now the grant (Constitution III: access is declared in the entry and granted
  by the owner writing it).

## 9. The lab's own server over HTTP (FR-012)

- **Decision**: `POST /mcp` on the backend (127.0.0.1:8000).
  - `Origin` present and not the lab's frontend origin → 403. The existing
    `TrustedHostMiddleware` already refuses foreign `Host` headers.
  - Modern requests are checked: `MCP-Protocol-Version` must match `_meta`, and `Mcp-Method`
    must match the method (and `Mcp-Name` the tool for `tools/call`). Otherwise 400 with
    `-32020`.
  - Answers are `application/json`; a notification gets 202.
  - `GET` and `DELETE` get 405.
  - An unknown method gets 404 with `-32601`.
  - No session ids are minted, and `Mcp-Session-Id` is ignored.
- **Claude Code**: `claude mcp add --transport http glasshouse http://127.0.0.1:8000/mcp`.
  Claude Code sends no `Origin`.

## 10. The notes server (FR-013)

- **Decision**: `python -m agent_lab.mcp.notes --folder PATH`, using the same server module as
  the lab's server over a stdio loop.
- **Tools**:
  - `list_notes()`: names, with sizes;
  - `read_note(name)`;
  - `write_note(name, text)`: creates or replaces a note.
- **Names**: `^[A-Za-z0-9][A-Za-z0-9 _-]{0,59}$`, stored as `<name>.md`. A resolved path whose
  parent is not the folder is refused, so symlinks cannot lead out.
- **Limits**: notes up to 20,000 characters, and at most 200 notes. Writes go to a temporary file
  and replace the note.
- **Folder**: created if missing. The default is `data/notes` (git-ignored).

## 11. Lifecycle

- **Decision**: a FastAPI lifespan.
  - **At start** the host connects the lab's server at once, then every listed server in the
    background, each within 10 seconds. The page shows `connecting` until then.
  - **At shutdown** it closes every connection and stops local programs.
  - **Reconnect and reload**:
    - `POST /mcp/servers/{name}/reconnect` re-reads that entry from the file and connects it
      again;
    - `POST /mcp/reload` re-reads the file, connects new and changed entries, drops removed
      ones and leaves unchanged connected ones alone.
- **The village** builds its block agents without tools. Its runs never touch the host.

## 12. Frontend

- **Decision**:
  - **Navigation**: a third view, **Tools**, beside Agents and Village. It shows each server's
    name, kind, target, state, reason, revision, server name and version, tools (name,
    description, arguments), and the last connect's messages, with Reconnect and Reload.
  - **Pickers**: the builder's and templates' tool pickers group tools by server in `<optgroup>`s
    and mark a tool from a server that is not connected as "(unavailable)".
  - **Limits**: a model-call block may have up to 6 tools.
  - **Pure logic** goes in `lib/tools.ts` (grouping, labels, unavailable marks) with vitest
    tests.
