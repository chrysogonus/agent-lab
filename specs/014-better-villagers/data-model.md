# Data Model: M14 — Better Villagers

The village stays one JSON row; `VERSION = 7`.

## Villager (new fields)

| Field | Type | Notes |
|---|---|---|
| `intention` | `{kind, place, villager, until, purpose, since, say} \| null` | at most one. `kind`: go, work, build, bring or see. `place` is a place key or "site" or "home". `villager` is set for see. `until` is a minute of the day, or null. `purpose` is up to 120 characters. `since` is a tick. `say` is a line to say on reaching the villager |
| `requests` | `[{from, goods, tick}]` | goods asked of this villager in the last 6 steps (an hour), so it may give |

## Memory

| Kind | Importance | Notes |
|---|---|---|
| `summary` (new) | 4 | replaces reflections older than 3 days once there are more than 5 of them |

`score(memory, tick, names, place, season)`: as M8, minus 3 when the memory's season is not the
current one and it is not about anyone in `names`.

## Intention steps (`intention.py`)

```text
next_step(world, v) ->
  {"kind": "walk", "cells": [...]}       go, or the way to the work place, site or villager
  {"kind": "start_work", "place": key}   arrived at the work place or site; becomes `working`
  {"kind": "set_down", "goods": g}       at the site carrying a needed load
  {"kind": "say", "to": name, "text": t} next to the villager sought, with a stored line
  {"kind": "done", "why": str}           arrived (go); `until` came; set down; found (no line)
  {"kind": "given_up", "why": str}       project finished; no loads left and none on the way;
                                         the villager is asleep; lost sight; bedtime
  {"kind": "none"}                       keep at it (working, walking)
```

## State transitions

```text
intention: null --move/work/build/bring/find answer (valid)--> {kind, …}
           any --another such answer--> the new one (the old one ends "replaced")
           any --next_step done/given_up--> null (event, note)
           any --bedtime--> null ("the day is over")
talk:      talking + an intention elsewhere --answer--> goodbye, then the first step
           walking with an intention while talking --apart--> the talk ends ("you walked apart")
```

## Upgrade from version 6

`upgrade()` 6 → 7: per villager `intention: null` and `requests: []`. Reset clears both.

## Agents refreshed on load

- the villager rules (`OLD_RULES` gains the M12 text);
- the reflection agent's system text (`OLD_REFLECT` holds the M8 text).
