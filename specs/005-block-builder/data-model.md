# Data Model: M5 — Composable Block Builder

## Block agent (stored as an M3 custom agent, table unchanged)

| Field | Value |
|---|---|
| `template_id` | `"blocks"` |
| `name`, `description`, `sample_prompt` | as M3 (1–60, 0–200, 1–4000 characters) |
| `config` | `BlocksConfig` without `model`/`provider`, plus both when the model is pinned (M4) |

## BlocksConfig (`blocks/model.py`)

| Field | Rule |
|---|---|
| `model`, `provider` | as every M4 config (filled from the default when not pinned) |
| `reasoning` | bool, default `false`; applies to every model call |
| `blocks` | `list[Block]`, 1 or more |

Default (new block agent): one model block `answer`, system prompt "Answer the user's question
briefly.", message `{previous}`.

## Block (discriminated on `kind`)

Common: `kind`, `name` (`^[a-z0-9-]{1,30}$`; not `start`, `end`, `input`, `previous`,
`feedback`, `item`; unique in the agent).

| Kind | Fields |
|---|---|
| `model` | `system`: 1–4000 characters; `message`: 1–4000 characters, default `{previous}`; `tools`: known tool names, unique, 0–2; `max_iterations`: 1–10, default 4 (used only with tools) |
| `tool` | `tool`: a known tool; `arguments`: one template (1–4000 characters) per parameter of that tool, exactly its parameter names |
| `check` | `rule`: `min_bullets` \| `max_words` \| `contains` \| `valid_json`; `value`: integer 1–1000 for `min_bullets`/`max_words`, text 1–300 characters for `contains`, absent for `valid_json` |
| `router` | `prompt`: 1–4000 characters; `routes`: 2–6 of `{name (block-name pattern, unique among the routes), description: 1–300 characters, blocks: 1 or more}`; `fallback`: one of the route names |
| `parallel` | `mode`: `branches` \| `per_item`. `branches`: 1–6 of `{name (unique among the branches), blocks: 1 or more}` (branches mode). `planner`: 1–4000 characters, `max_items`: 1–6, `body`: 1 or more blocks (per-item mode). Fields of the other mode are absent |
| `loop` | `body`: 1 or more blocks; `exit`: `judge` \| `check`; `judge`: 1–4000 characters (judge exit); `check`: `{rule, value}` as the check block (check exit); `max_rounds`: 1–5, default 3 |

## Layout rules (`layout_errors`, checked on save, preview and run start)

- At most 30 blocks in the whole tree (routes and branches are not blocks).
- Nesting at most 3 levels: top-level blocks are level 1; a container at level 3 is rejected.
- Block names unique across the tree.
- References (`{token}` matching the name pattern) must be `input`, `previous`, a visible earlier
  block, `feedback` inside a loop body, or `item` inside a per-item body
  ([research.md](research.md) §4).
- Every error has the loc of its field under `config`, e.g.
  `["blocks", 1, "routes", 0, "blocks", 0, "message"]`.

## Outputs (what `{name}` and `{previous}` read)

| Block | Output |
|---|---|
| model | final answer text |
| tool | tool result text (`error: …` when the tool rejects its arguments) |
| check | its input, unchanged |
| router | the chosen route's last output |
| parallel (branches) | `"<branch>:\n<output>"` per branch, joined by a blank line |
| parallel (per item) | `"<item>:\n<output>"` per item, joined by a blank line |
| loop | the last round's body output |

## Graph (derived, never stored by the client)

- Node per block except parallel groups in branches mode; `tool:<name>` nodes for model calls
  with tools; `start`, `end`. Kinds: model/router/per-item/judge → `llm`, tool → `tool`,
  check/check-exit → `code`.
- Edges as in research.md §6.

## Run (unchanged)

The run stores the redacted `BlocksConfig` dump (`config`), the derived graph, `agent_name`,
`template_id = "blocks"` and `config_version` = hash of the config.

## States

| Event | Run status |
|---|---|
| last block finished | `completed`, answer = last output |
| check fails (block) | `error`, end span from the check node, message names the check |
| model call reaches `max_iterations` with tools still requested | `max_iterations`, answer `null` |
| loop reaches `max_rounds` without exit | `max_iterations`, answer = last body output |
| model, tool transport, decision (router, planner, judge) error | `error` |
