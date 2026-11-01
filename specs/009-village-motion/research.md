# Research: M9 — Village Motion and Look

## 1. Three cells per step, in rounds

- **Decision**: each step runs up to 3 rounds; every villager owns one fixed slot per round (in
  villager order), and a walker moves one cell in its slot, then `_look()` and a publish run.
  Empty slots keep their time, so a walker's rhythm stays the same across steps whoever else
  starts or stops walking; a villager who starts walking mid-step moves in its own slot.
- **Why**: crossing the map takes a third of the steps (SC-001); interleaving keeps "one move per
  published state" (SC-002) and lets meetings happen mid-step.
- **Gap**: `interval / (3 × villagers)` in the running loop, so each walker moves every
  `interval / 3` seconds (≈ 1.7 s at 5 s); 0.1 s in Step; tests pass 0. The view glides each move
  linearly for exactly that long (`glideMs`), so walking is continuous; the walk animation plays
  while a figure is gliding, including into its last cell (the state already says it arrived) (a fixed order replaced M7's rotation, which jittered the rhythm
  at step boundaries).

## 2. Leaving a conversation

- **Decision**: while `partners(world, name)` is not empty, `move` and `find` parse to `wait`
  with "you are talking with Lina; say goodbye first". `goodbye` gains optional `place` (as
  move) and `villager` (as find); after ending the conversations, `_apply` sets the goal as move
  or find would. An unusable destination (unknown, already there, already next to them) keeps the
  goodbye and records "You said goodbye but stayed: <reason>." in the events.
- **Why**: conversations end deliberately and the other villager always hears goodbye; silence,
  the 10-line limit and bedtime still end conversations, so nobody gets stuck.

## 3. Updating stored villager agents

- **Decision**: on load, each villager agent whose model block's system prompt contains the M7
  rules text verbatim gets it replaced by the new rules; prompts the owner edited in the rules
  part are left alone (the owner's edits win).
- **Why**: without the new rules the model would keep trying to walk away mid-conversation.

## 4. Idle animations

- **Decision**: the activity comes from the state: `walking` (walking, bedtime), `talking`,
  `thinking` (deciding), `working` (idle at its work place), `idle`. Each figure gets a negative
  animation delay from a stable hash of its name, so rhythms differ.
  - Walk: two leg frames (left foot up, right foot up) toggled at 0.25 s plus a 1 px bob.
  - Idle: breathe (1 px every 2.6 s), blink (eyes covered for 0.15 s every ~4 s), glance (eyes
    1 px left, back, 1 px right over ~7 s).
  - Work props: Jonas a rod with a line and bobbing float, Greta a hoe that swings, Lina a
    watering can with falling drops, Hilde a sheet of paper she lifts and lowers.
- **Why**: small, cheap CSS animations on SVG groups; front-facing sprites stay as they are.

## 5. World decorations

- **Decision** (all drawn in SVG, CSS-animated, `pointer-events: none`):
  - Shadows: a translucent strip under each building's front and to its right; trees have one.
  - Chimney smoke: three puffs rising and fading from a house whose owner stands awake at its door.
  - Butterflies: three over the flower garden, morning to afternoon.
  - Lake rings: three spots, rings expanding and fading at different delays.
  - Fireflies: eight dots near the water and trees, evening and night, drifting and pulsing.
  - Sky light: a vertical gradient over the map per period: morning peach at the top, midday
    clear, afternoon light gold, evening orange to violet, night deep blue.
