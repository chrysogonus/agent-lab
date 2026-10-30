# Research: M1 — ReAct Walking Skeleton

## Span persistence timing
- Decision: upsert on span start and on span end.
- Rationale: a client joining mid-run sees running spans; a crashed run still shows where it stopped.
- Alternatives: insert on end only (simpler, but late joiners miss running spans).

## Live vs. replay
- Decision: the UI reads only the WebSocket; the server sends stored spans, then live events,
  then `run_ended`, then closes. The client upserts by `span_id`, so duplicates from the
  subscribe/snapshot overlap are harmless.
- Rationale: one rendering path (contract 3). Subscribing before taking the snapshot avoids a gap.
- Alternatives: REST for replay + WS for live (two code paths).

## Span nesting
- Decision: current span in a `contextvars.ContextVar`.
- Rationale: correct across `await` and `asyncio` tasks (needed for M2 parallel workflows) without
  threading a parent through every call.
- Alternatives: explicit `parent=` arguments (noisier).

## GenAI semantic conventions
- Decision: span names `invoke_agent {agent}`, `chat {model}`, `execute_tool {tool}`;
  `attributes` uses `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.agent.id`.
- Rationale: cheap and makes a later OTLP exporter a mapping, not a redesign.

## Timestamps
- Decision: epoch seconds as float (`time.time()`).
- Rationale: trivial waterfall math in the browser; ms precision is enough.

## Calculator
- Decision: tokenizer + recursive-descent parser with Python's precedence (`**` right-assoc and
  binds tighter than unary minus).
- Rationale: no `eval`, no `ast` node allow-listing pitfalls; the limits make CPU/memory bounded.

## WebSocket security
- Decision: check `Origin` on the WS handshake against the same allow-list as CORS; trusted-host
  middleware for `Host`.
- Rationale: browsers do not apply CORS to WebSockets (cross-site WS hijacking), and loopback
  services are reachable via DNS rebinding.

## Type checking
- Decision: pyright `strict` mode over `src` and `tests` (raised from `standard` on 2026-10-30,
  owner's call).
- Rationale: cheaper to adopt while the codebase is small. JSON from the model and SQLite rows
  get explicit types at the boundary (`cast` only where the JSON spec guarantees the shape).
  Tool functions take `object` because model arguments are untrusted; their `isinstance` checks
  are the validation.

## Frontend tests
- Decision: vitest (approved by the owner on 2026-10-30) over the pure view logic in
  `lib/run-state.ts`: event upserts, span tree, active node, taken edges. Rendering is checked
  manually (quickstart) since it depends on React Flow layout in a real browser.
- Rationale: the bugs found so far (path for parallel tool calls) live in that logic; no DOM
  test environment (jsdom) needed.
