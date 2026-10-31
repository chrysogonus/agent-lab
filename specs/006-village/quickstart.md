# Quickstart / validation: M6

Prerequisites: as M5 (`make dev-llm`, `make dev`).

## Automated

```bash
make check
```

Expected: all gates pass with no real model. Notable tests: map and path finding; clock;
observations; every action and invalid answers; simultaneous application of a tick; speech
reaching only nearby villagers with the addressee; 100 scripted ticks with valid positions
(SC-002); persistence, restart and reset (SC-005); self-pause after failed ticks and without a
viewer; village turns traced with their tick and absent from `GET /runs` (SC-003).

## Manual (real model)

1. Open the Village view: map with six places, four villagers at home, day 1, 06:00 (US1-1).
2. Press Step: all four act once; the clock shows 06:10. Press Start: ticks every 5 s; the first
   tick finishes within 30 s of opening the view (SC-001).
3. Watch for 36 ticks: villagers walk between places, talk ("Hilde → Jonas: …"), and the mayor
   mentions the festival (SC-006).
4. Click Lina: persona, place, last 10 events, turns; open a turn: graph, spans, observation and
   answer (US3-1, US3-2).
5. Edit Jonas's agent in the builder (e.g. "always talk about the weather"), save: his next turn
   has a new config version and follows it (US3-3).
6. Close the tab while running, reopen after more than a minute: paused, "no viewer for 60 s".
7. Stop the model server while running: after 3 failed ticks the village pauses and says why.
8. Restart the backend: same tick and positions, paused (SC-005). Reset: everyone at home,
   tick 0.
