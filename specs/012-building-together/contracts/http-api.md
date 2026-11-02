# Interface changes in M12

## HTTP API

No new endpoints.

`VillageState` gains:

```text
trader: {stock: {wood: int, paint: int, saplings: int}, leaves: "14:00"} | null
meeting: {day: int, kind: "vote" | "review",
          proposals: [{key, name, reason, run_id}],
          votes: [{villager, key: str | null, name: str | null, reason, run_id}],
          present: [str],
          decision: {key, name, reason, against: bool, by: "hilde" | "vote", run_id} | null,
          outcome: str | null} | null
project: {key, name, kind, needs: {goods: int}, site: {goods: int}, used: {goods: int},
          done: int, total: int,   # done = sum(used), total = sum(needs)
          tasks: [{task: "buy" | "bring" | "build", goods: str | null, villagers: [str]}],
          day: int} | null
built: [{key, name, kind, day}]
next_meeting: int                     # the day of the next town hall meeting
map.catalogue: [{key, name, kind, site: [[x, y]], at: [[x, y]]}]
map.rows                              # gains the plot letters "b" and "r"
```

Each villager:

```text
basket: "fish" | "vegetables" | "flowers" | "wood" | "paint" | "saplings" | null
working: … | "site"
```

`meeting_agent_id` is internal.

### Runs

Meeting runs are ordinary runs of the "Village meeting" agent. Each is tagged with `village_tick`
and with a villager: Hilde for proposals, decisions and work plans, the voter for a vote. They
are listed among that villager's turns. Their `village_action`:

```text
{"action": "propose", "proposals": ["A market stand: …", …]}   | {"action": "propose", "reason": …}
{"action": "vote", "project": "A market stand", "reason": …}   | {"action": "vote", "reason": why invalid}
{"action": "decide", "project": "…", "reason": …, "against": bool, "by": "hilde" | "vote"}
                                                               | {"action": "decide", "reason": why none}
{"action": "assign", "tasks": ["buy paint: Jonas", "build: Greta, Lina"]}
                                                               | {"action": "assign", "reason": …}
```

A new decision `village_action`, `{"action": "buy", "goods": "wood", "paid": "fish"}`; refusals
are `{"action": "wait", "reason": …}` as before. `give` gains loads: `{"action": "give", "to":
null, "goods": "paint"}` at the site.

New event kinds: `traded`, `proposed`, `meeting`, `task`, `built`.

## Villager agent answers (the rules contract)

Added to the actions a villager may answer:

```text
{"action": "buy", "goods": "wood"}    at the market while the trader is there: your basket for a load
{"action": "give"}                    at the building site: set down the load you carry
{"action": "work"}                    at the building site: build with the loads lying there
{"action": "move", "place": "building site"}   walk to the current project's site
```

## Village meeting agent answers

One agent, four shapes; each prompt ends by naming the one it wants:

```text
{"proposals": [{"project": "A market stand", "reason": "Greta needs a place to sell"}]}   1–3
{"vote": "A market stand", "reason": "I sell there every day"}
{"decision": "A market stand", "reason": "Most of you want it, and it is quick to build"}
{"tasks": [{"task": "buy", "goods": "wood", "villagers": ["Jonas"]},
           {"task": "bring", "goods": "wood", "villagers": ["Jonas"]},
           {"task": "build", "villagers": ["Greta", "Lina"]}]}                                 1–6
```

Reasons are at most 120 characters; projects are named as in the catalogue (key or name).
