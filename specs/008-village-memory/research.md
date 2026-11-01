# Research: M8 — Villager Memory

## 1. What becomes a memory

- **Decision**: memories are written where M7 already writes events: when a conversation ends
  (both villagers, with its transcript: "Hilde: … / Lina: …", cut to 400 characters; the
  conversation record keeps the transcript as lines are added), on `found` and `missed`, and
  on the first `met` with a villager each day. Importance by kind: conversation 3, found 2,
  missed 2, met 1, reflection 5. Each memory: `{tick, kind, about, place, text, importance}`.
- **Why**: these are the moments that carry information about others; walking and waiting do
  not. Fixed importance keeps the cost at zero model calls and the behavior testable.
- **Limit**: 60 per villager; when full, the memory with the lowest `importance + recency`
  (no relevance) goes, so old small talk leaves first and reflections stay longest.

## 2. Recall without embeddings

- **Decision**: score = relevance + importance + recency, with relevance 4 when the memory is
  about a villager who matters now (next to it, being looked for, talking with it) and 2 when
  it is about its current place; recency = 3 × 0.85^(hours since). The top 5 are shown oldest
  first, with day and time.
- **Why**: the questions a villager faces are about the people around it; names and places are
  exact keys in this world, so words are enough. An embedding model would be a new dependency
  and a second local model (the constitution and the owner's rule ask before adding one).
- **Alternatives**: model-rated importance (an extra call per memory); embedding similarity
  (dependency, nondeterministic tests).

## 3. Reflection

- **Decision**: when a villager falls asleep and has at least one non-reflection memory from
  the day it went to bed in, the runner starts `_reflect(name)`: one run of the shared
  reflection agent, tagged with the villager and the step, prompt =

  ```text
  You are Hilde. <persona>
  Day 1 is over and you are going to bed.
  What you remember from today:
  - 12:30 Talked with Lina: Hilde: … / Lina: …
  What you learned before:
  - Day 0 … (or "- nothing yet")
  What you think of the others:
  - Jonas: … (or "no view yet")
  Look back on your day. Answer with one JSON object.
  ```

  The agent (`Village reflection`, created with the villagers' agents) is a model block
  `reflect` whose system prompt asks for `{"learnings": [...], "views": {...}}` (up to 3 new
  learnings in the villager's own words; one sentence per villager it dealt with), then a
  `valid_json` check. The answer is validated with pydantic: `learnings` a list of at most 3
  non-empty strings, `views` an object keyed by the other villagers' first names; texts cut to
  200 characters. Valid → learnings appended (12 kept), views replaced, a reflection memory
  (importance 5, about the villagers in `views`). Invalid or failed → nothing changes; the run's
  `village_action` records `{"action": "reflect", "reason": …}`.
- **Scheduling**: reflections live in their own task map, one per villager; a new one for a
  villager whose previous reflection still runs awaits it first. They never count as decisions
  (no failure self-pause, no "deciding" state). Step awaits decisions and reflections, so
  scripted tests are deterministic; the running loop never waits for them. Reset waits for
  both and discards results.
- **Why bedtime**: one call per villager per day keeps the cost small, and "sleeping on it" makes
  the change visible the next morning.

## 4. Using learnings and views

- **Decision**: the observation gains, after the beliefs, "What you have learned:" (all
  learnings, oldest first) and "What you remember:" (recall); each belief line gets "; you think:
  <view>" when a view exists. Personas stay unchanged.

## 5. Shape and migration

- **Decision**: `version: 3`; a version-2 world gets `memories: []`, `learnings: []`,
  `views: {}` per villager and `reflection_agent_id: null`, then keeps running (FR-008); older
  shapes start fresh as in M7.
