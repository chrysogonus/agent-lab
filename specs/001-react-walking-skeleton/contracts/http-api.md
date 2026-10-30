# HTTP API (backend, `http://127.0.0.1:8000`)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/runs` | `{"prompt": str (1..4000)}` | `202` `Run` (status `running`) |
| GET | `/runs` | – | `200` `[Run]` newest first (max 100) |
| GET | `/runs/{run_id}` | – | `200` `{"run": Run, "spans": [Span]}` ordered by `started_at`; `404` if unknown |
| WS | `/runs/{run_id}/stream` | – | see `stream-events.md` |

`Run` and `Span` shapes: see `../data-model.md`.

Cross-cutting:
- Allowed browser origins: `http://127.0.0.1:3000`, `http://localhost:3000` (CORS and WS `Origin`).
- Allowed `Host`: `127.0.0.1`, `localhost` (any port); others get `400`.
