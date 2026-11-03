# Feature Specification: M16 — Tools over MCP

**Feature Branch**: `main` (feature directory `016-mcp-tools`)

**Created**: 2026-11-03

**Status**: Draft

**Input**: "M16 MCP: the lab's agents get their tools over a hand-written Model Context Protocol
layer, so tools are no longer only the two built into the code." The input lists four parts:
- a hand-written MCP host that connects to the servers the owner lists;
- the lab's own MCP server, serving the built-in tools;
- a small example server shipped in the repo;
- tracing of every call.

It also sets security rules, limits the milestone to tools, and asks that earlier contracts are
kept.

## Context

The lab has six agent templates and a builder. Agents can use exactly two tools, a calculator
and a fake weather report, which are written into the lab's code. Adding a tool means changing
the lab.

The Model Context Protocol (MCP) is the common way for an agent host to get tools from separate
programs, called servers. A server may be a local program the host starts, or a service the host
reaches over HTTP. Many such servers exist, and other agent tools (for example Claude Code) can
use any of them.

This milestone makes the lab an MCP host and an MCP server, written by hand:
- **A host**: the lab connects to the servers the owner lists and offers their tools to its
  agents.
- **Its own server**: the calculator and the weather report move behind the lab's own MCP
  server. The lab's agents reach them through the host like any other tool, so every tool call
  takes the same path. Other MCP clients can use them too.
- **An example server**: a small notes server ships with the lab, so a second, separate server
  works without installing anything.

All earlier contracts apply:
- every model call and every tool call is a traced step of a run;
- tests use the scripted fake model and fake transports only, never a real model or a real
  outside service;
- no new dependency, and no MCP software library: the protocol is written by hand;
- the lab binds to 127.0.0.1 only, and secrets never reach a stored or shown trace;
- existing agents and builder configs keep working unchanged.

The village does not change in this milestone.

The roadmap after M16:
- M17 the evaluation harness for the lab's other agents (budgets, retries, approvals);
- M18 agent memory for the lab's other agents;
- M19 RAG.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who builds agents in the lab, runs them and reads their traces.

### User Story 1 - The built-in tools over MCP (Priority: P1)

The calculator and the weather report are served by the lab's own MCP server. When an agent
calls a tool, the lab's host sends the call to that server and hands the answer back to the
model. The owner sees no difference in what the agents can do, but the trace now shows each
call as an MCP call: which server, which tool, the message that went out and the one that came
back.

Agents and builder configs saved before this milestone name the tools `calculator` and
`get_weather`. They keep running and mean the same two tools.

**Why this priority**: it builds the whole path (host, server, protocol, tracing) on tools whose
behaviour is already known and tested, so any difference is a bug in the new path.

**Independent Test**: run the ReAct template's sample prompt with the scripted fake model. The
answer and the tool results are the same as before the milestone, and each tool span shows the
lab's server, the tool and the exchanged messages.

**Acceptance Scenarios**:

1. **Given** the ReAct template, **When** the owner runs its sample prompt, **Then** the model's
   tool calls go to the lab's server and the run ends with the same answer as before.
2. **Given** a builder agent saved before this milestone with a tool-call block for
   `calculator`, **When** it runs, **Then** it calls the lab's calculator and its result is
   unchanged.
3. **Given** a run that called a tool, **When** the owner opens the tool span, **Then** it shows
   the server's name, the tool's name, the outgoing request and the response, with any secret
   replaced by a redaction mark.
4. **Given** a tool call with invalid arguments (for example a division by zero), **When** the
   server answers with a tool error, **Then** the model receives the error text, the run goes
   on, and the span is marked as an error.

---

### User Story 2 - The owner's own servers (Priority: P2)

The owner lists MCP servers in a servers file. Each entry is either:
- a local program the lab starts, with its arguments and the environment variables it may see;
- an address the lab reaches over HTTP.

When the lab starts, it connects to each listed server, introduces itself and asks for its
tools. A Tools page shows every server:
- its name and kind (local program or address);
- its state: connected, connecting, or failed with the reason;
- its tools, each with its description and the arguments it takes.

The owner can reconnect a server from the page, for example after fixing its entry. In the
builder and the ReAct template's settings, the owner picks tools from any connected server. The
picker groups them by server and names them `server/tool`.

**Why this priority**: this is what makes the lab open. Any MCP server the owner has, or writes,
becomes a tool for the lab's agents without changing the lab.

**Independent Test**: list a fake server in the servers file (served by a test transport).
The Tools page lists it as connected with its tools. A builder agent that picks one of its
tools calls it in a run, and the result reaches the model.

**Acceptance Scenarios**:

1. **Given** a servers file with a local program and an address, **When** the lab starts,
   **Then** both appear on the Tools page with their state and tools.
2. **Given** an entry whose program does not exist, **When** the lab starts, **Then** that
   server shows as failed with the reason, the other servers work, and the lab starts normally.
3. **Given** an agent that uses a tool of a server that is not connected, **When** the owner
   runs it, **Then** the run stops before the first model call and says which server is
   missing.
4. **Given** a connected server that stops during a run, **When** the model calls one of its
   tools, **Then** the model receives an error saying the server is unavailable, and the Tools
   page shows the server as failed.
5. **Given** an address entry pointing to a host other than this computer, **When** the lab
   starts, **Then** the server is refused with the reason, unless the entry explicitly allows
   that host.

---

### User Story 3 - The example notes server (Priority: P3)

The repo ships a small MCP server, written by hand like the rest of the lab, that keeps notes:
it lists, reads and writes short text notes inside one folder. The folder is set in the servers
file; the server never reads or writes outside it. The default servers file lists it, so the
owner can build an agent that keeps notes between runs without installing anything.

**Why this priority**: it proves the host works with a separate program, started and spoken to
like any third-party server, and it gives the lab its first tool with a lasting effect.

**Independent Test**: start the notes server as a local program in a test, connect through the
host, write a note, list the notes and read it back. Then try a note name that reaches outside
the folder, which is refused.

**Acceptance Scenarios**:

1. **Given** the notes server is connected, **When** an agent writes a note and a later run
   reads it, **Then** the later run gets the same text.
2. **Given** a note name such as `../secret` or an absolute path, **When** a tool is called with
   it, **Then** the call fails with a tool error, and nothing outside the folder is read or
   written.
3. **Given** a note longer than the limit, **When** it is written, **Then** the call fails with
   a tool error saying the limit.

---

### User Story 4 - Other MCP clients use the lab's server (Priority: P4)

The lab's own server is reachable at an address on this computer. The owner can add it to
another MCP client, for example Claude Code, and use the calculator and the weather report
there. The docs say how.

**Why this priority**: it shows the server is a real MCP server, not just an internal detail,
and it is a cheap check that the hand-written protocol matches the standard.

**Independent Test**: a test client speaks to the lab's server address the way an outside
client does (introduce itself, list tools, call one) and gets correct answers. A manual check
connects Claude Code.

**Acceptance Scenarios**:

1. **Given** the lab is running, **When** an outside MCP client connects to the lab's server
   address, **Then** it can list and call the calculator and the weather report.
2. **Given** a request from a web page on another site (a browser origin other than the lab's),
   **When** it reaches the lab's server, **Then** it is refused.

### Edge Cases

- **Invalid servers file**: an unreadable or malformed file is reported on the Tools page and in
  the log. The lab still starts and still serves its own built-in tools.
- **Two servers with the same tool name**: both are offered, told apart by the server's name.
- **A tool name the model cannot use**: names are made safe for the model's tool format, and
  every name the model sees maps back to exactly one server and tool.
- **A server lists no tools**: it shows as connected with no tools.
- **A slow server**: a connection that does not finish its introduction within 10 seconds fails.
  A tool call that does not answer within 30 seconds fails with a "timed out" tool error.
- **A huge or odd result**: text results are passed to the model cut at 20,000 characters, with
  a note that they were cut. Non-text content (images, audio, links to resources) is replaced by
  a short placeholder saying what it was.
- **A server that sends garbage**: messages that are not valid protocol messages are ignored,
  and an answer that never arrives counts as a timeout.
- **A server that changes its tools while connected**: the lab notices the server's change
  notice and lists the tools again.
- **Tool output that tries to give the model instructions**: tool results are always passed as
  tool results, never as system or owner instructions.
- **Stopping the lab**: local servers it started are stopped with it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The lab MUST connect to every server in the owner's servers file when it starts:
  introduce itself, agree on a protocol version, and list the server's tools. A server that
  fails MUST NOT stop the lab or other servers.
- **FR-002**: The servers file MUST allow two kinds of entry:
  - a local program, with its command, arguments and named environment variables;
  - an address over HTTP, with optional request headers.
- **FR-003**: A local program MUST receive only the environment variables its entry names, plus
  what any program needs to start (its search path and home folder).
- **FR-004**: An address entry MUST be refused unless it points to this computer, or the entry
  explicitly allows its host.
- **FR-005**: A Tools page MUST show every server with its kind, its state (connected,
  connecting, failed with the reason) and its tools (name, description, arguments). The owner
  MUST be able to reconnect a server from it.
- **FR-006**: The ReAct template, the builder's model-call and ReAct blocks, the tool-call block
  and the routing template's per-route tool MUST be able to use any tool of any connected
  server, named `server/tool`. A model-call block MAY offer up to 6 tools.
- **FR-007**: The built-in calculator and weather report MUST be served by the lab's own MCP
  server, and the lab's agents MUST reach them through the same host and protocol as any other
  server. The names `calculator` and `get_weather` in existing configs MUST keep meaning these
  two tools.
- **FR-008**: A run MUST stop before its first model call when it uses a tool whose server is not
  connected or that the server does not list, saying which.
- **FR-009**: A tool call MUST go out as a protocol call to its server. A result, a tool error, a
  timeout or an unavailable server MUST each reach the model as the tool's result text, and the
  run MUST go on.
- **FR-010**: Every tool call MUST be a tool span showing the server, the tool, the outgoing
  request and the response or error. Secrets MUST be redacted: environment values and headers
  named in the servers file, and anything already redacted today.
- **FR-011**: The Tools page MUST show, for each server, the messages of its last introduction
  and tool listing, with secrets redacted.
- **FR-012**: The lab's own server MUST be reachable by outside MCP clients at an address on this
  computer only, and MUST refuse requests from browser origins other than the lab's own.
- **FR-013**: The notes server MUST list, read and write notes only inside the folder its entry
  names. It MUST refuse names that reach outside that folder, and notes over 20,000 characters.
- **FR-014**: The default servers file MUST list the notes server. Without an owner's servers
  file, the lab MUST use the default one.
- **FR-015**: Tool results MUST reach the model as tool results only, cut at 20,000 characters
  with a note, with non-text content replaced by a placeholder.
- **FR-016**: When a connected server announces that its tools changed, the lab MUST list them
  again.
- **FR-017**: Local programs the lab started MUST be stopped when the lab stops.
- **FR-018**: The protocol layer MUST be written by hand. No MCP software library and no new
  dependency may be added.

### Key Entities

- **Server entry**: what the owner wrote about one server: its name, its kind (local program or
  address), how to start or reach it, the environment variables or headers it gets, and any
  host it is allowed to reach beyond this computer.
- **Server connection**: the lab's live link to one server: its state, the failure reason, the
  protocol version agreed, the server's own name and version, its tools, and the messages of
  its last introduction.
- **Tool**: a server's tool: its name, description and the arguments it takes. To agents it is
  `server/tool`.
- **Tool call**: one call in a run: the tool, the arguments, the request and response messages,
  the result text the model got, and whether it failed. It is stored as a span.
- **Note**: a short text with a name, kept as one file in the notes server's folder.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every existing agent template and every saved builder agent runs unchanged. The
  existing test suite passes, with tool calls now going over MCP.
- **SC-002**: With the scripted fake model, the ReAct sample run gives the same answer and the
  same tool results as before the milestone.
- **SC-003**: The owner can add a new MCP server by editing only the servers file and
  reconnecting, and use its tools in a new builder agent within 5 minutes, without changing the
  lab.
- **SC-004**: 100% of tool calls in a run appear as spans naming the server and the tool, and no
  secret from the servers file appears in any stored span or on the Tools page.
- **SC-005**: An outside MCP client (Claude Code) connects to the lab's server and calls both
  built-in tools successfully (manual check).
- **SC-006**: On a real model, an agent that uses the notes server writes a note in one run and
  reads it back in a later run in at least 4 of 5 tries (manual check).
- **SC-007**: A failing or missing server never keeps the lab from starting. The owner sees the
  reason on the Tools page.

## Assumptions

- **Tools only**: MCP also defines resources, prompts, sampling and more. This milestone covers
  connecting, listing tools, calling tools and the tool-change notice. The rest comes later
  (resources with RAG), and the village is not exposed over MCP yet.
- **The servers file is the grant**: whatever the owner writes into the servers file is allowed.
  There is no further approval per call; approvals come with the harness milestone.
- **Default servers file in the repo, owner's own file kept out of git**: the repo ships a
  default with the notes server. The owner's own file may hold secrets and is not committed.
- **The notes folder**: by default a folder under the lab's data folder, which git ignores.
- **Names for the model**: some models only accept letters, digits, `_` and `-` in tool names.
  The model sees a safe form of `server/tool`; the owner always sees `server/tool`.
- **Version**: the lab speaks the current stable MCP revision, chosen in the plan, and accepts
  servers that answer with an older one it can still speak.
- **Authorization**: servers that need a sign-in (OAuth) are out of scope. An address entry can
  carry a fixed header with a key instead.
- **Model for manual checks**: the local model is off for now. Manual checks on a real model use
  the hosted model the owner names (`openai/gpt-6-luna`), until the local model is back.
- **Tool limit per block**: a model-call block may offer up to 6 tools, up from 2. Only two
  tools existed before.
