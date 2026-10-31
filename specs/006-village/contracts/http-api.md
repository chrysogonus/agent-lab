# HTTP API changes in M6

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/village` | – | `200` `VillageState` |
| POST | `/village/start` | – | `200` `VillageState` (running); creates the villagers' agents on first start |
| POST | `/village/pause` | – | `200` `VillageState`; the current tick finishes |
| POST | `/village/step` | – | `200` `VillageState` after one tick; `409` while running or while a tick is in progress |
| PUT | `/village/interval` | `{"seconds": int}` (1–30) | `200` `VillageState`; `422` out of range |
| POST | `/village/reset` | – | `200` `VillageState` (paused, tick 0) after the active tick, if any, finishes; recreates deleted villager agents; past turns stay |
| GET | `/village/villagers/{name}/turns` | – | `200` `[Turn]` newest first: every run with this `villager`, whichever agent played it; `404` unknown name |
| WS | `/village/stream` | – | `{"type": "state", "state"}` on connect and after every tick or control change; `{"type": "tick_started", "tick"}` |
| GET | `/runs` | – | as before, without village turns |

```text
VillageState = {
  tick, day, time ("07:20"), period ("morning"), running, ticking, interval, paused_reason,
  map: {width, height, rows: [str], places: [{key, label, x, y}]},   # x, y: label position
  villagers: [{name, title, color, initial, agent_id, x, y, place, destination,
               last_action, speech, events}]
}
```

Turn = Run + {village_tick, villager, village_action}  # the action applied and any wait reason

Rules: same Host, CORS and WebSocket Origin checks as the rest of the API; `Run` gains
`village_tick`, `villager` and `village_action` (null for non-village runs). Templates, custom agents and block agents are
unchanged.
