# WebSocket stream: `WS /runs/{run_id}/stream`

Server → client JSON messages:

```json
{"type": "span_started", "span": Span}
{"type": "span_ended",   "span": Span}
{"type": "run_ended",    "run": Run}
{"type": "error",        "message": "unknown run"}
```

Sequence:
1. Handshake with a disallowed `Origin` → closed with code 1008 before accept.
2. Unknown run → `error`, then close (1008).
3. Server subscribes to the run, then sends every stored span as `span_started` (if
   `ended_at` is null) or `span_ended`.
4. If the run is already terminal → `run_ended`, close (1000).
5. Otherwise forwards live events until `run_ended`, then closes (1000).

Clients MUST treat events as idempotent upserts keyed by `span_id`.
The client sends nothing; messages it sends are ignored.
