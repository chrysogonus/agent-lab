# HTTP API changes in M7

Endpoints are unchanged from M6 (`specs/006-village/contracts/http-api.md`); their meaning
shifts from ticks to steps:

| Method | Path | Change |
|---|---|---|
| POST | `/village/step` | one step (10 village minutes, staggered moves) plus the decisions it starts, awaited; `409` while running or while a step is in progress |
| PUT | `/village/interval` | seconds between steps (1–30) |
| POST | `/village/reset` | waits for the step and the decisions in flight, discards their results; everyone asleep at home, 04:30 |
| WS | `/village/stream` | `{"type": "state", "state"}` on connect and after every move, step, applied decision and control change; `{"type": "decision_started", "villager", "run_id"}` (was `turn_started`); `tick_started` is gone |

```text
VillageState = {
  tick, day, time ("04:30"), period, running, ticking, interval, paused_reason,
  log: [{tick, time, from, to, text}],                       # newest last, at most 8
  map: {width, height, rows: [str], places: [{key, label, x, y}],
        homes: [{villager, letter, door: [x, y]}]},
  villagers: [{name, title, color, initial, agent_id, x, y, place, destination,
               last_action, speech, events,
               state: "asleep" | "bedtime" | "deciding" | "talking" | "walking" | "idle",
               wake ("05:00"), bed ("21:00"), goal (text or null),
               talking_with: [name], beliefs: [{villager, text}]}]
}
```

`destination` stays (the place key of a `place` goal, else null) so M6 views keep working.
Rules: same Host, CORS and WebSocket Origin checks. Turns are listed as in M6.
