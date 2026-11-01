# Data Model: M10 — Village Seasons

The village stays one JSON row; `VERSION = 4`.

## World (new fields)

| Field | Type | Notes |
|---|---|---|
| `growth.fields` | `{stage, progress, untended}` | stage: `resting`, `tilled`, `sown`, `sprouting`, `growing`, `ripe`, `harvested`; progress 0–5; untended: days in a row |
| `growth.flower_garden` | `{stage, watered, dry}` | stage: `resting`, `budding`, `blooming`, `wilting`; counters in days |
| `tended` | `{fields: int, flower_garden: int}` | steps with an awake villager on the place since the last growth update; reset each morning |
| `day_record` | `{day, items: [{tick, text}]} \| null` | open from the first waking until everyone sleeps; items ≤ 120, text ≤ 300 |
| `festival` | `{day, present: [name]} \| null` | the festival evening's guests |
| `chronicle` | `[{day, year, season, day_of_season, weather, title, text, run_id}]` | oldest first, ≤ 28; title ≤ 60, text ≤ 800 |
| `chronicler_agent_id` | `str \| null` | the shared "Village chronicler" agent, kept across Reset |

Derived, not stored (`seasons.py`): `date(day)`, `festival_in(day)`, `weather(day)`,
`snow_cover(day)`, `sky(day, minute)`, `dark(day, minute)`.

## Villager memory

New memory kind `festival`, importance 5.

## State transitions

Fields, at the end of each day outside winter:

```text
resting --tended--> tilled --tended--> sown --3 pts--> sprouting --5 pts--> growing --6 pts--> ripe
ripe --tended, autumn--> harvested
any stage --first day of winter--> resting   (ripe: lost)
points per tended day: 2 with rain or storm, else 1; untended days add nothing
```

Flower garden, at the end of each day outside winter:

```text
budding --2 watered days--> blooming --2 dry days in a row--> wilting --watered day--> blooming
any --first day of winter--> resting --first day of spring--> budding
watered: tended (≥ 6 steps) or rain or storm
```

## Upgrade from version 3

`upgrade()` chains: version 2 → 3 (M8, unchanged) → 4. Version 4 adds the fields above with
`day_record`, `festival` = null, `chronicle` = [], `tended` = 0s, and growth from the current
season: spring fields `resting`, summer `growing`, autumn `ripe`, winter `resting`; the garden
`budding` in spring, `blooming` in summer and autumn, `resting` in winter; all counters 0.

## Reset

`new_world()`: day 1 of spring, fields `resting`, garden `budding`, empty chronicle; Reset keeps
`reflection_agent_id` and `chronicler_agent_id`.
