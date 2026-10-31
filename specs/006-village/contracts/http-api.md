# HTTP API changes in M6

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/village` | – | `200` `VillageState` |
| POST | `/village/start` | – | `200` `VillageState` (running); creates the villagers' agents on first start |
| POST | `/village/pause` | – | `200` `VillageState`; the current tick finishes |
| POST | `/village/step` | – | `200` `VillageState` after one tick; `409` while running |
| PUT | `/village/interval` | `{"seconds": int}` (1–30) | `200` `VillageState`; `422` out of range |
| POST | `/village/reset` | – | `200` `VillageState` (paused, tick 0); recreates deleted villager agents |
| GET | `/village/villagers/{name}/turns` | – | `200` `[Run]` newest first (runs with this villager's agent and a `village_tick`); `404` unknown name |
| WS | `/village/stream` | – | `{"type": "state", "state"}` on connect and after every tick or control change; `{"type": "tick_started", "tick"}` |
| GET | `/runs` | – | as before, without village turns |

```text
VillageState = {
  tick, day, time ("07:20"), period ("morning"), running, interval, paused_reason,
  map: {width, height, rows: [str], places: [{key, label, x, y}]},   # x, y: label position
  villagers: [{name, title, color, initial, agent_id, x, y, place, destination,
               last_action, speech, events}]
}
```

Rules: same Host, CORS and WebSocket Origin checks as the rest of the API; `Run` gains
`village_tick` (null for non-village runs). Templates, custom agents and block agents are
unchanged.
