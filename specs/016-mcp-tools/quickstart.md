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
   - confirm the token appears nowhere on the Tools page, in the span detail, or in the stored
     spans, where this gives 0:

     ```bash
     python3 -c "import sqlite3; print(sqlite3.connect('backend/data/agent_lab.db').execute(
       \"select count(*) from spans where coalesce(input,'') || coalesce(output,'') ||
       coalesce(attributes,'') like '%<token>%'\").fetchone()[0])"
     ```

## Results (2026-11-03)

**Timing** (plan performance goals), measured once with a script:

| Path | Goal | Measured |
|---|---|---|
| `calculator` through the in-process lab server | adds under 5 ms | adds 0.014 ms (0.016 ms against 0.002 ms called directly) |
| `notes/read_note` over stdio | under 100 ms | median 0.19 ms, p95 0.26 ms, max 0.36 ms |

**Manual checks** on `openai/gpt-6-luna`. They ran against a second backend on port 8010, with a
scratch database and a scratch servers file, so the owner's database was not touched. That
file listed `notes`, `journal` (a second notes server) and `web` (the lab's own `/mcp` over
HTTP, with `Authorization: Bearer ${M16_CHECK_TOKEN}`).

| Check | Result |
|---|---|
| 1. The Tools page | API: `lab`, `notes` and `journal` connected at start. `web` failed with "All connection attempts failed" because it was its own address before uvicorn accepted connections; Reconnect connected it (modern, 2026-07-28). Browser (2026-11-05, see below): passed. |
| 2. Built-ins unchanged | Passed with reasoning off: "17 × 23 + 11°C = **402**". Both tool spans show `lab.mcp.server: lab`, 2026-07-28, the request id and the response. With reasoning on (the template's default), OpenAI refuses function tools for gpt-6-luna on `/v1/chat/completions` (HTTP 400). That limit predates M16. |
| 3. The owner's own server | Passed: a `todo` entry was added to the file, then Reload, then a new block agent using `todo/write_note` and `web/calculator`. It completed 3.3 s after the file edit (through the API, not the builder UI). |
| 4. Notes between runs (SC-006) | **3/5** with a plain system prompt: in both misses the model did not look in its notes. **4/5** with a system prompt saying "before answering any question, look in your notes": the one miss read the note and then refused to repeat a "password". Every tool call the model made worked. |
| 5. Claude Code | Not run on 2026-11-03: `claude mcp add` changes the owner's Claude Code settings. Run on 2026-11-05 without changing them: passed (see below). |
| 6. Secrets (SC-004) | Passed: the token appeared 0 times in 35 tool spans, in the runs, on the Tools page and in the server log. |

## Results (2026-11-05): the two open checks

Both ran against a scratch backend on port 8010 with a scratch database and servers file, and no
model keys, so the owner's database and settings were not touched.

| Check | Result |
|---|---|
| 1. The Tools page | Passed in headless Chromium: `lab` and `notes` connected with their tools. With the notes command set to `nonexistent`, **Reload** showed notes as "failed: cannot start: No such file or directory", and `lab` stayed connected with its tools. Restoring the file and pressing **Reload** connected notes again. The page came from a scratch frontend on port 3001, which is not an allowed origin, so the browser ran with web security off; origin checks were not part of this check. |
| 5. Claude Code (SC-005) | Passed on Claude Code 2.1.318 with `claude -p --mcp-config <file> --strict-mcp-config`, the same `/mcp` endpoint as `claude mcp add`: `get_weather` for Berlin gave 11 °C and rain, and `calculator` for `2**10 - 24` gave 1000. |

**Limits of these results:**
- SC-003 was met through the API. Picking the tool in the builder UI was not run on a real model.
- SC-006 reached its 4 of 5 only with a system prompt telling the agent to look in its notes. A
  plain system prompt gave 3 of 5.
