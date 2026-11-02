# Interface changes in M14

## Villager agent answers (the rules contract)

New, or extended:

```text
{"action": "work", "place": "fields", "until": "12:00"}   walk there if needed, work until 12:00
                                                          (both optional: work here, until you stop)
{"action": "build", "until": "15:00"}                     go to the building site and build
{"action": "bring"}                                       take your load to the building site, set it down
{"action": "find", "villager": "Greta", "say": "Any fish?"}
                                                          find Greta and say this when next to her
```

Unchanged: move, say, goodbye, give, buy, wait.

Changed behaviour:

- **Talking villagers**: move, find, work elsewhere, build and bring while talking become a
  goodbye and setting off, never the refusal "say goodbye first".
- **Saying from afar**: a say to someone awake and in sight but not next to you becomes a find
  with that line.
- **Giving to a villager**: refused unless they are the one you set out to see, or asked you for
  those goods in the last hour.

## The observation

- New section **"What you can do here:"**: up to 6 actions that would be accepted now, each as
  JSON with why.
- New line **"You are set on: build at the building site until 15:00 (to plant the trees). Next:
  walk there."**, or "You are not set on anything."
- The hint lines of M11 and M12 leave the observation ("Take your basket…", "set down your load
  now…", "Nothing can be built until…", "The building site holds… go and build").
- "Next to you" and "In sight" give names.

## HTTP API

- Each villager in `GET /village` gains `intention: {kind, place, villager, until: "HH:MM" |
  null, purpose, since: "HH:MM"} | null`.
- A turn's `village_action` for a decision that started an intention carries `"intention": {…}`.
- New event kinds: `intended` and `intention_ended`.
