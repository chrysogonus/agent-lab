# Quickstart: M16 — Tools over MCP

## Automated

```bash
make check
```

This covers every functional requirement with the scripted fake model:
- `httpx.MockTransport` serves fake modern and legacy HTTP servers;
- the in-process transport serves the lab's server;
- the notes server runs as a real subprocess (`sys.executable -m agent_lab.mcp.notes`);
- a small legacy stdio server script under `backend/tests/` tests the fallback.

No test reaches a real model or an outside service.

## Manual checks

The local model is off for now, so manual runs use `openai/gpt-6-luna`. Set `OPENAI_API_KEY` in
`.env` and pick the model in the agent's settings.

1. **The Tools page** (FR-001, FR-005, SC-007):
   - start `make dev`, open http://127.0.0.1:3000, then go to **Tools**;
   - `lab` and `notes` show as connected with their tools;
   - change the notes entry's command to `nonexistent` in `backend/data/mcp.json` and press
     **Reload**: notes fails with the reason, and lab still works.
2. **Built-ins unchanged** (SC-001, SC-002): run the ReAct template's sample prompt. The tool
   spans show `lab.mcp.server: lab` with the request and the response.
3. **The owner's own server** (SC-003):
   - add any MCP server to `backend/data/mcp.json` (for example a second notes server with
     another folder), press **Reload**, and pick one of its tools in a new builder agent;
   - time it: within 5 minutes.
4. **Notes between runs** (SC-006):
   - build a model-call block with `notes/write_note`, `notes/read_note` and `notes/list_notes`;
   - prompt it to note a fact, then in a second run to read it back;
   - record 5 tries.
5. **Claude Code** (SC-005): `claude mcp add --transport http glasshouse
   http://127.0.0.1:8000/mcp`, then ask Claude Code for the weather in Berlin and for
   `2**10 - 24`. Both calls succeed.
6. **Secrets** (SC-004):
   - give an HTTP entry a header `Authorization: Bearer ${SOME_TOKEN}`;
   - run a tool of it;
   - confirm the token appears nowhere on the Tools page, in the span detail, or in
     `sqlite3 backend/data/agent_lab.db "select count(*) from spans where input || output || attributes like '%<token>%'"`, which gives 0.
