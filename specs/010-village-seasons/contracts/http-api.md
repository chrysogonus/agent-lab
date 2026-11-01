# HTTP API changes in M10

No new endpoints. `PUT /village/interval` keeps accepting 1–30 seconds; the view only sends 15,
5 or 2.

`VillageState` gains:

```text
calendar: {year, season, day_of_season, festival_in}   # season: spring|summer|autumn|winter;
                                                        # festival_in: days until it, 0 today, null
weather: "sun" | "clouds" | "rain" | "storm" | "fog" | "snow"
snow_cover: bool
sky: "morning" | "midday" | "afternoon" | "evening" | "night"   # light shifted by the season
dark: bool                                              # lamps and windows lit
growth: {fields: {stage, neglected}, flower_garden: {stage}}
chronicle: [{day, year, season, day_of_season, weather, title, text, run_id}]   # newest first, ≤ 28
```

`period` stays (the villagers' time of day). Internal fields (`tended`, `day_record`, `festival`,
`chronicler_agent_id`, growth counters) are not sent.

Chronicle runs are ordinary runs of the "Village chronicler" agent tagged with `village_tick`
and no villager; their `village_action` is `{"action": "chronicle", "title": …}` or
`{"action": "chronicle", "reason": …}`. The stream sends `decision_started` with `villager: null`
when one starts.
