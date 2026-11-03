"""The hand-written MCP layer, for both ends (specs/016-mcp-tools).

`jsonrpc` messages and codes; `server` one server core answering both protocol eras;
`transports` in-process, stdio and streamable HTTP; `client` one connection to one server;
`servers_file` the owner's servers file; `host` every connection and the tools agents use;
`lab_server` the lab's own server (calculator, get_weather); `notes` the example notes server.
"""
