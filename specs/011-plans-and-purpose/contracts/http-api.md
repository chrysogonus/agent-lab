# Interface changes in M11

## HTTP API

No new endpoints.

`VillageState` gains:

```text
stalls: {fish: int, vegetables: int, flowers: int}
```

Each villager gains:

```text
plan: {entries: [{time: "HH:MM", place: str | null, villager: str | null, purpose: str}],
       current: int | null, next: int | null, revisions: int} | null   # today's plan only;
                                                                       # place is the label
basket: "fish" | "vegetables" | "flowers" | null
working: "fields" | "flower_garden" | "pier" | null
state: … | "working"                                                   # new state value
```

Internal fields (`said`, `harvest`, `planner_agent_id`) are not sent.

Plan runs are ordinary runs of the "Village planner" agent tagged with the villager and
`village_tick`; their `village_action` is `{"action": "plan", "revision": 0|1|2, "entries":
["07:30 town hall: …", …]}` or `{"action": "plan", "revision": n, "reason": …}`. They are listed
among the villager's turns.

New decision `village_action`s: `{"action": "work", "place": "fields"}` and `{"action":
"give", "to": "Hilde" | null, "goods": "fish"}`; refusals are `{"action": "wait", "reason": …}`
as before.

New event kinds: `planned`, `worked`, `basket`, `gave`, `received`.

## Villager agent answers (the rules contract)

Added to the actions a villager may answer:

```text
{"action": "work"}                    work where you stand until you walk off
{"action": "give", "to": "Hilde"}     hand your basket to someone next to you
{"action": "give"}                    on the square: set your basket out on the festival stalls
```

## Planner agent answer

```text
{"plan": [{"time": "07:30", "place": "town hall", "purpose": "Go through the festival list"},
          {"time": "11:00", "villager": "Jonas", "purpose": "Ask him for fish for the stalls"}]}
```

2–6 entries; each a time and a place or a villager, and a purpose of at most 120 characters.
