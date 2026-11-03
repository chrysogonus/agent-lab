# Data Model: M16 — Tools over MCP

Nothing in this milestone goes into the database. Runs and spans keep their tables. The servers
file is the owner's, and connections live in memory.

## Servers file (`mcp.json`)

```text
{"mcpServers": {<name>: <entry>, ...}}
```

| Field | Kind | Rules |
|---|---|---|
| name (key) | string | `^[a-z][a-z0-9-]{0,29}$`; not `lab`; at most 20 entries |
| `type` | `"stdio"` \| `"http"` | optional: `http` when `url` is set, else `stdio` |
| `command` | string | stdio: required, 1–500 characters |
| `args` | list of strings | stdio: optional, at most 50, each at most 500 characters |
| `env` | map of name → value | stdio: optional; `${VAR}` takes VAR from the lab's environment |
| `url` | string | http: required; `http` or `https` |
| `headers` | map of name → value | http: optional; `${VAR}` as for `env` |
| `allowHosts` | list of host names | http: optional; hosts allowed beyond this computer |

Unknown fields are refused, so a typo is reported rather than ignored.

The file is looked up in this order:
1. `MCP_SERVERS_FILE`;
2. `backend/data/mcp.json`;
3. `backend/mcp.json`, the committed default.

## Server connection (in memory)

| Field | Meaning |
|---|---|
| `name` | the entry's name; `lab` for the lab's own server |
| `kind` | `stdio`, `http` or `internal` |
| `target` | the command line or the URL, with secrets redacted |
| `state` | `connecting` → `connected` \| `failed` |
| `reason` | why it failed (`null` unless failed) |
| `era` | `modern` (2026-07-28) or `legacy` (initialize) |
| `protocol_version` | the revision agreed |
| `server_info` | the server's self-reported `name` and `version`, for display only |
| `watching` | whether tool changes are followed (FR-016) |
| `tools` | the listed tools, as below |
| `log` | the messages of the last connect: at most 20, each cut at 4,000 characters, redacted |
| `secrets` | the resolved `env` and `headers` values, for redaction; never shown |

### State changes

```text
connecting --(discover or initialize, then tools/list)--> connected
connecting --(error, 10 s timeout, version refused, bad entry)--> failed
connected  --(process exited, stream closed, call finds it dead)--> failed
any        --(reconnect or reload)--> connecting
connected  --(tools changed notice)--> connected (tools listed again)
```

## Tool (as listed)

| Field | Meaning |
|---|---|
| `server` | the connection's name |
| `name` | the server's tool name |
| `config_name` | the name configs use: `calculator`/`get_weather` for the lab's built-ins, `server/tool` otherwise |
| `description` | from the server; empty if none |
| `input_schema` | the tool's JSON Schema; an object schema is required, and a tool without one is dropped |
| `header_params` | arguments mirrored as `Mcp-Param-*` headers (modern HTTP only) |

The name the model sees is not stored. It is worked out per model call from the tools offered
(research §4).

## Tool span (extended)

These are the existing tool-span fields plus the new attributes:

| Attribute | Value |
|---|---|
| `mcp.method.name` | `tools/call` |
| `mcp.protocol.version` | the connection's revision |
| `jsonrpc.request.id` | the request id |
| `lab.mcp.server` | the server name |
| `lab.mcp.request` | the JSON-RPC request as sent |
| `lab.mcp.response` | the JSON-RPC response as received, or `null` on timeout or a dead connection |

`gen_ai.tool.name` stays the config name.

## Agent configs

The shapes are unchanged:
- ReAct `tools`, the routing template's route `tool`, a model-call block's `tools` and a
  tool-call block's `tool` all accept `calculator`, `get_weather`, `lab/<tool>` or
  `server/tool`;
- the form is checked when a config is saved, and whether the tool exists is checked when a run
  starts;
- a model-call block may list up to 6 tools, up from 2.

## Note (notes server)

| Field | Rules |
|---|---|
| name | `^[A-Za-z0-9][A-Za-z0-9 _-]{0,59}$`; the file is `<name>.md` in the folder |
| text | at most 20,000 characters |
| count | at most 200 notes in the folder |
