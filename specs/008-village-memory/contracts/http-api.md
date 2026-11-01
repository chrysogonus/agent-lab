# HTTP API changes in M8

No new endpoints. `VillageState` villagers gain:

```text
learnings: [{day, text}],                       # oldest first
views: [{villager, text, day}],
memories: [{day, time, kind, text}],            # newest first, at most 60
beliefs: [{villager, text, view}]               # view: text or null
```

`GET /village/villagers/{name}/turns` also lists the villager's reflections (runs of the
reflection agent tagged with the villager); their `village_action.action` is `"reflect"`.
The stream sends `decision_started` for reflections too, so an open panel lists them live.
