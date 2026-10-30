# Data Model: M3

M2 entities (Run, Span, Graph, decisions) are unchanged except where noted. No new node kinds.

## Shared field rules
| Rule | Definition |
|---|---|
| Prompt | string, 1–4000 characters after trimming |
| Item name (chain step, route, aspect) | `^[a-z0-9-]{1,30}$`, unique within the list, not `start`, `end`, `gate`, `router`, `merge`; used as the node id |
| Short text (route description, aspect focus) | 1–300 characters after trimming |
| Tool name | a key of `TOOLS` in `tools/catalog.py` (`calculator`, `get_weather`) |

## Template configs (pydantic; defaults = the template; hashed into `config_version`)
Every config also has `model: str` (injected by the server, never stored with a custom agent)
and `reasoning: bool` (ReAct default True, workflows False).

| Template | Fields (default) | Limits |
|---|---|---|
| ReAct | `system_prompt` (M2 text), `tools: list[str]` (`["calculator", "get_weather"]`), `max_iterations: int` (6) | tools ⊆ `TOOLS`, unique, 0–2; iterations 1–10 |
| Chain | `steps: list[ChainStep]` (outline; draft with `include_input`; polish), `gate: bool` (true), `gate_min_bullets: int` (3) | 1–6 steps; bullets 1–10 |
| Routing | `router_prompt`, `routes: list[RouteSpec]` (math+calculator, general, weather+get_weather), `fallback: str` ("general") | 2–6 routes; `fallback` is one of the route names |
| Parallel | `aspects: dict[str, str]` name → focus (clarity, tone, claims), `review_prompt` (with `{aspect}`, `{focus}`), `merge_prompt` | 1–6 aspects |
| Orchestrator | `orchestrator_prompt` (with `{max_subtasks}`), `worker_prompt`, `synthesizer_prompt`, `max_subtasks: int` (4) | subtasks 1–6 |
| Evaluator | `generator_prompt`, `evaluator_prompt`, `max_rounds: int` (3) | rounds 1–5 |

- **ChainStep**: `name`, `prompt`, `include_input: bool` (false; ignored for the first step,
  which always gets the input).
- **RouteSpec**: `name`, `description`, `prompt`, `tool: str | None`.

## Decision models built per config
| Decision | Change from M2 |
|---|---|
| Route | `label` enum = the agent's route names; invalid → the `fallback` route |
| Plan | `subtasks` max length = `max_subtasks` |
| GateResult | minimum = `gate_min_bullets` |
| Verdict | unchanged |

## CustomAgent (table `agents`)
| Field | Type | Rule |
|---|---|---|
| agent_id | text PK | `custom-` + 12 hex characters; never a template id |
| template_id | text | one of the six template ids; fixed for life |
| name | text | 1–60 characters after trimming |
| name_key | text UNIQUE | `lower(trim(name))` |
| description | text | 0–200 characters |
| sample_prompt | text | 1–4000 characters |
| config | JSON text | the template's config without `model` |
| created_at, updated_at | real | epoch seconds |

Lifecycle: created (from a template or by duplicating), updated any number of times, deleted
(hard delete after confirmation). Runs never reference the row; they carry their own snapshot.

## Run (changes)
| Field | Type | Meaning |
|---|---|---|
| agent_name | text, null for M1/M2 runs | the agent's name when the run started |
| template_id | text, null for M1/M2 runs | template of the agent; equals `agent_id` for template runs |
| config | JSON | redacted snapshot of the resolved config (including `model`) |

## AgentInfo (API, changed)
`id, kind ("template" | "custom"), template_id, name, description, sample_prompt, config
(editable fields, without model), graph`

## ToolInfo (API, new)
`name, description`
