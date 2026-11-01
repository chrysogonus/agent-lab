# Data Model: M8 — Villager Memory

## World (table `village`, JSON) — changes

| Field | Rule |
|---|---|
| `version` | `3`; a `2` is upgraded in place, anything else starts fresh |
| `reflection_agent_id` | the shared reflection agent (null until first start) |
| `conversations[].transcript` | `["Hilde: …", "Lina: …"]`, the lines so far |

## Villager — new fields

| Field | Rule |
|---|---|
| `memories` | at most 60 `{tick, kind: conversation|found|missed|met|reflection, about: [name], place, text, importance: 1–5}` |
| `learnings` | at most 12 `{tick, text}` (text ≤ 200 characters), oldest first |
| `views` | `{other: {tick, text}}` (text ≤ 200 characters) |

## Reflection answer

```json
{"learnings": ["Jonas is at the market around midday."], "views": {"Jonas": "Quiet, but fair."}}
```

`learnings`: list of ≤ 3 non-empty strings (default `[]`); `views`: object keyed by other
villagers' first names (default `{}`). Anything else is invalid.

## Run (existing) — reflections

`village_tick` = the step it started in, `villager` = the reflecting villager,
`village_action` = `{"action": "reflect", "learnings": [...], "views": {...}}` or
`{"action": "reflect", "reason": "…"}`.
