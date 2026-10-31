# Quickstart / validation: M7

Prerequisites: as M6 (`make dev-llm`, `make dev`).

## Automated

```bash
make check
```

Expected: all gates pass with no real model. Notable tests: the bigger map, homes and doors;
wake-up and bedtimes over a scripted day; no turns while asleep; the fast night; staggered moves
(one move per published state); decisions only on triggers; a slow decision not blocking others;
speech only between neighbours; conversations starting, ending (goodbye, walking away, bedtime,
silence, 10 lines); finding a villager (found and missed); beliefs (seen, heard, routine);
persistence, reset and a fresh start from an M6 world; the auto-pauses.

## Manual (real model)

1. Open the Village view: the bigger map with four houses, everyone asleep, day 1, 04:30
   (US1-1). Start.
2. Jonas leaves his hut at about 05:00, Greta at 05:30, Lina at 06:30, Hilde at 07:30 (SC-001);
   walkers move at different moments (US2-1).
3. Watch the dialog box: two villagers talk only when standing together; a conversation of 3+
   lines happens; Hilde looks for someone on purpose and raises the festival (SC-006).
4. Click a villager: sleeping hours and where it thinks the others are (FR-020).
5. Around 21:00–23:00 villagers walk home one by one and their houses show "Zz"; the night
   passes in seconds (SC-004).
6. Restart the backend: same time and positions, paused. Reset: everyone asleep, 04:30.
