# Interface changes in M15

## Villager agent answers (the rules contract)

New:

```text
{"action": "lead"}                                      lead the lost animal next to you home
{"action": "row", "with": "Greta", "until": "15:00"}    take the boat out from the pier ("with",
                                                        "until" optional); the one asked joins
                                                        with its own {"action": "row"}
```

Extended:

- **work**: at a place with a broken thing, the work mends it first. In the boat, it fishes the
  lake.
- **buy**: at the square while the peddler is there, `{"action": "buy", "goods": "lantern"}`
  trades a basket for the curiosity.

Unchanged: move, find, say, goodbye, give, build, bring, wait.

## The observation

- **Facts**:
  - "Happening here: Greta's goat wandered to the market." (seen);
  - "A letter waits for you at home." / "Anna, your sister, visits you this afternoon"
    (concerned);
  - "The boat is out on the lake with Jonas" / "The boat lies at the pier".
- **Claims**: "Said to you since your last turn" also lists `- a voice: "…"` for whispers.
- **What you can do here**: lead, mend (work), trade for the curiosity, row (with someone next
  to you), when each is possible.

## HTTP API

| Endpoint | Change |
|---|---|
| `GET /village` | adds `happenings` (kind, label, cell, state, by, concerns, start/end as "HH:MM") and `boat` (state, rowers, cell). Each villager adds `keepsakes`; whispers are not sent |
| `POST /village/villagers/{name}/whisper` | new. Body `{"text": "…"}`. Answers `{"heard": true}`, or `{"heard": false}` when the villager is asleep and will hear it on waking. 404 for an unknown villager; 422 for empty or over 200 characters; 409 "Greta already heard 3 whispers today" |
| `GET /village/health` | each day adds `happenings: {count, dealt}`, `boat_trips`, `whispers: {count, followed}` |

A decision answering a whisper carries `"after_whisper": true` in its `village_action`.

New event kinds: `happening`, `invited`, `whispered`, `rowed`.
