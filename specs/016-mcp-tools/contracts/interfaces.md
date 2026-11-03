# Interfaces: M16 — Tools over MCP

## MCP messages the lab sends (host)

### Modern servers (2026-07-28)

Every request's `params._meta` holds:

```json
{"io.modelcontextprotocol/protocolVersion": "2026-07-28",
 "io.modelcontextprotocol/clientCapabilities": {},
 "io.modelcontextprotocol/clientInfo": {"name": "glasshouse", "version": "0.1.0"}}
```

| When | Method | Params besides `_meta` |
|---|---|---|
| connect | `server/discover` | none |
| connect, and after a tools-changed notice | `tools/list` | `cursor` on pages after the first |
| the server declares `tools.listChanged` | `subscriptions/listen` | `{"notifications": {"toolsListChanged": true}}` |
| a tool call | `tools/call` | `name`, `arguments` |

### Legacy servers (2025-11-25 and older)

| When | Message |
|---|---|
| connect | `initialize` `{protocolVersion: "2025-11-25", capabilities: {}, clientInfo}` |
| after its result | notification `notifications/initialized` |
| then | `tools/list` and `tools/call`, without `_meta` |

The lab accepts these revisions in the server's answer: `2025-11-25`, `2025-06-18`,
`2025-03-26` and `2024-11-05`. It refuses any other.

### HTTP request headers

| Header | Modern | Legacy |
|---|---|---|
| `Accept` | `application/json, text/event-stream` | same |
| `Content-Type` | `application/json` | same |
| `MCP-Protocol-Version` | `2026-07-28` | the agreed revision, after `initialize` |
| `Mcp-Method` | the method | none |
| `Mcp-Name` | the tool name, on `tools/call` | none |
| `Mcp-Param-{name}` | mirrored `x-mcp-header` arguments | none |
| `Mcp-Session-Id` | none | the value the server returned, if any |
| entry `headers` | yes | yes |

## MCP messages the lab answers (its own server and the notes server)

| Method | Answer |
|---|---|
| `server/discover` | `{resultType: "complete", supportedVersions: ["2026-07-28", "2025-11-25"], capabilities: {tools: {}}, _meta: {"io.modelcontextprotocol/serverInfo": {name, version}}}` |
| `initialize` | `{protocolVersion, capabilities: {tools: {}}, serverInfo}`: the client's version if it is one of the four legacy revisions above, else `2025-11-25` |
| `notifications/initialized` | nothing (HTTP 202) |
| `tools/list` | `{resultType: "complete", tools: [{name, description, inputSchema}], ttlMs: 3600000, cacheScope: "public"}`, with no pagination |
| `tools/call` | `{resultType: "complete", content: [{type: "text", text}], isError}`; a tool's error is `isError: true` with its message |
| anything else | JSON-RPC error `-32601` |

- **Modern requests** (those with `_meta` protocolVersion) with a version other than
  `2026-07-28` get `-32022` with `data: {supported: ["2026-07-28"], requested}`.
- **An unknown tool** gets `-32602`.
- **Arguments that are not an object, or that miss or add parameters** get `isError: true`
  naming them, as today's `ToolError` text does.

The lab's server is named `glasshouse` and lists `calculator` and `get_weather`. The notes
server is named `glasshouse-notes` and lists `list_notes`, `read_note` and `write_note`.

## HTTP API

### `POST /mcp`: the lab's own MCP server

- **Request**: a JSON-RPC message. Modern requests carry the headers above.
- **Answers**:
  - `200 application/json` with the response;
  - `202` for a notification;
  - `400` with `-32020` on a header that does not match the body;
  - `403` when `Origin` is present and not `http://127.0.0.1:3000` or `http://localhost:3000`;
  - `404` with `-32601` for an unknown method.
- `GET /mcp` and `DELETE /mcp` → `405`.

### `GET /mcp/servers`

```json
{"file": "backend/mcp.json", "file_error": null,
 "servers": [{"name": "lab", "kind": "internal", "target": "built in", "state": "connected",
   "reason": null, "era": "modern", "protocol_version": "2026-07-28",
   "server_info": {"name": "glasshouse", "version": "0.1.0"}, "watching": false,
   "tools": [{"name": "calculator", "config_name": "calculator", "description": "…",
              "parameters": {…}}],
   "log": [{"direction": "out", "message": {…}}, {"direction": "in", "message": {…}}]}]}
```

`file_error` explains an unreadable or invalid servers file. The `lab` server is listed even
then.

### `POST /mcp/servers/{name}/reconnect`

Re-reads that entry from the file and connects it again. Answers `202` with that server's entry from the
`servers` list above (state `connecting`), or `404` for an unknown name.

### `POST /mcp/reload`

Re-reads the file: new and changed entries connect, and removed ones close. Answers `202` with
the body of `GET /mcp/servers`.

### `GET /tools` (changed)

Every tool of every connected server:

```json
[{"name": "calculator", "server": "lab", "description": "…", "parameters": {…}},
 {"name": "notes/write_note", "server": "notes", "description": "…", "parameters": {…}}]
```

`name` is the config name. The shape gains only `server`, so the builder's existing use keeps
working.

### `POST /runs` (changed)

`409 {"detail": "server \"notes\" is not connected"}` or
`409 {"detail": "tool \"notes/x\" is not listed by \"notes\""}` before a run is created, when a
tool of the config cannot be called.

## Tool result text for the model

| Server answer | Text |
|---|---|
| text items | joined by blank lines |
| image / audio | `[image: <mimeType>]` / `[audio: <mimeType>]` |
| resource link | `[resource link: <uri>]` |
| embedded resource | its text, or `[resource: <uri>]` |
| only `structuredContent` | its JSON |
| `isError: true` | `error: <text>` |
| JSON-RPC error | `error: <message>` |
| no answer in 30 s | `error: timed out after 30 s` |
| dead connection | `error: server "<name>" is unavailable` |
| `resultType: "input_required"` | `error: the tool asked for input, which the lab does not support` |

Text longer than 20,000 characters is cut, followed by `[cut: N more characters]`.
