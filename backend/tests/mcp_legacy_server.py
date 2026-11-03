"""A stdio MCP server that speaks only 2025-11-25 (no `server/discover`), for tests.

Tools: `echo` (its text), `env` (the names of its environment), `notify` (adds a tool and
announces the change), `exit` (ends the program).
"""

import json
import os
import sys
from typing import Any, cast

TOOLS = [
    {"name": n, "description": n, "inputSchema": {"type": "object", "properties": p}}
    for n, p in [("echo", {"text": {"type": "string"}}), ("env", {}), ("notify", {}), ("exit", {})]
]


def send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def answer(method: str, params: dict[str, Any]) -> object:
    if method == "initialize":
        return {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "legacy", "version": "0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    name, args = params.get("name"), cast(dict[str, Any], params.get("arguments") or {})
    if name == "echo":
        text = str(args.get("text"))
    elif name == "env":
        text = " ".join(sorted(os.environ))
    elif name == "notify":
        TOOLS.append({"name": "added", "inputSchema": {"type": "object"}})
        send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        text = "ok"
    else:
        sys.exit(3)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def main() -> None:
    print("legacy server starting", flush=True)  # not a message: the host ignores it
    print("a line on stderr", file=sys.stderr, flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        method = message["method"]
        if method not in ("initialize", "tools/list", "tools/call"):
            error = {"code": -32601, "message": f"unknown method {method}"}
            send({"jsonrpc": "2.0", "id": message["id"], "error": error})
            continue
        result = answer(method, message.get("params") or {})
        send({"jsonrpc": "2.0", "id": message["id"], "result": result})


if __name__ == "__main__":
    main()
