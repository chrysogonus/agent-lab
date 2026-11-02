# Data Model: M15 — Daily Happenings and Boat Trips

The village stays one JSON row; `VERSION = 8`.

## World (new fields)

| Field | Type | Notes |
|---|---|---|
| `happenings` | `[happening]` | today's, set when the day record opens; replaced each day |
| `boat` | `{rowers, invited, left, back, at, state} \| null` | null while the boat is at the pier unused (or not built) |
| `harvest.lake` | int | the lake's harvest counter, as for the pier |

## Happening

| Field | Type | Notes |
|---|---|---|
| `kind` | `letter \| visitor \| animal \| repair \| peddler` | at most one of each a day |
| `place` | place key or null | null for letters and visitors (at the concerned villager's door) |
| `cell` | `[x, y]` | where it is drawn and noticed; moves for a followed animal or visitor |
| `start`, `end` | minute of the day | the window; outside it, not here |
| `concerns` | villager name or null | the letter's addressee, the host, the animal's owner |
| `details` | `{text, name?, goods?}` | the news, the visitor ("Anna, Greta's sister"), the animal ("Greta's goat"), the broken thing, the curiosity |
| `state` | `coming → here → dealt \| passed` | |
| `by` | villager or null | who dealt with it |
| `seen_by` | `[name]` | who was told they saw it (once each) |
| `leader` | name or null | animal: who leads it; visitor: the host once met |
| `work` | int | repair: steps of work so far (6 mend it) |
| `with_host` | int | visitor: steps spent next to the host (6 is an hour) |

State transitions:

```text
coming --start minute--> here (concerned villager told; postman figure for 30 min for letters)
here --dealt (read at home / led to owner / 6 steps of work / traded / an hour with host)--> dealt
here --end minute (or the day ends)--> passed
```

## Villager (new fields)

| Field | Type | Notes |
|---|---|---|
| `keepsakes` | `[{name, day}]` | traded from the peddler; not carried |
| `whispers` | `[{text, tick, heard}]` | `heard`: the tick it reached the villager, or null while it sleeps; today's count limits new ones (3) |

The `intention` kinds gain `lead` (to the owner's door, with the animal) and `row` (in the boat
until `until`).

## Boat trip

```text
null --row answer at the pier (boat built, not out, no storm)--> {state: boarding, rowers: [a], invited: b?}
boarding --b answers row within 2 steps--> rowers [a, b]
boarding --2 steps pass (or nobody invited)--> {state: out, left, back}
out --each step--> at = next lake cell; work fishes the lake
out --back tick, or bedtime--> rowers at the pier; null (notes, memories)
```

## Memory

| Kind | Importance |
|---|---|
| `happening` (new) | 3: "You led Greta's goat home." |
| `keepsake` (new) | 3 |
| `boat` (new) | 4: "A boat trip on the lake with Greta." |

## Upgrade from version 7

`upgrade()` 7 → 8 adds:
- `happenings: []` and `boat: null`;
- `harvest.lake: 0`;
- per villager `keepsakes: []` and `whispers: []`.

Reset clears all of them. A world upgraded mid-day gets happenings from its next new day.

## Agents refreshed on load

The villager rules: `OLD_RULES` gains the M14 text.
