# Agent Lab

Learn agent fundamentals by building them by hand, and watch every step live. M1 shipped a
traced ReAct agent with two tools (`calculator`, `get_weather`), an API, and a one-page UI
with the agent graph, a span waterfall, span details and replay of past runs. M2 adds the
five workflow patterns: prompt chaining, routing, parallelization, orchestrator-workers and
evaluator-optimizer. M3 adds a builder: the six agents are templates, and custom agents made
from them can be edited, saved and run.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 22 and pnpm
- make
- For real runs (tests don't need them): an NVIDIA GPU with ~11 GiB free VRAM, Docker with the
  NVIDIA container runtime, and the `vllm/vllm-openai:v0.31.0` image

## Run

```bash
make install
cp .env.example .env      # point LLM_BASE_URL / LLM_MODEL elsewhere if you like
make dev-llm              # vLLM on http://127.0.0.1:8001, detached (first start downloads ~11 GB)
make dev                  # backend on http://127.0.0.1:8000 and frontend on http://127.0.0.1:3000
```

Open http://127.0.0.1:3000, pick a template (its graph, settings and a sample prompt appear),
press Run, and click spans for their input, output, tokens and latency.

To build your own agent, pick a template and press Customize. Click a node to edit its prompt
and settings; add, remove or reorder chain steps, routes and parallel aspects, pick ReAct's
tools and change limits in the agent settings. The graph redraws as you edit. Save stores the
agent under "My agents"; Run saves first. Duplicate and Delete work on saved agents; past runs
keep the name, config and graph they ran with.

For more freedom, build a block agent: press "New block agent", or "Open as blocks" on any
template or customized agent. A block agent is a list of blocks that run top to bottom, edited
in the outline in the settings panel (+ adds a block after another; ↑ ↓ move it; ✕ removes it):

- **Model call**: a system prompt and a message; optionally tools and a limit on model calls
  (the ReAct loop as one block).
- **Tool call**: one tool with its arguments.
- **Check**: at least N bullet lines, at most N words, contains a text, or valid JSON; failing
  ends the run.
- **Router**: a model decision picks one of 2–6 routes, each a list of blocks.
- **Parallel group**: fixed branches, or the same blocks once per item a model plans, all at the
  same time.
- **Loop**: repeats its blocks until a judge approves or a check passes, up to 5 rounds.

Prompts refer to `{input}` (the user's prompt), `{previous}` (the previous block's output),
`{name}` (an earlier block's output), and inside loops and per-item groups to `{feedback}` and
`{item}`. Up to 30 blocks, nested 3 levels deep; the server checks the layout on every save.

### The village

Switch the header to "Village" to watch four villagers live on a small map: Mayor Hilde (town
hall), Jonas the fisher (pier), Greta the farmer (fields) and Lina the flower girl (flower
garden). Each tick is 10 minutes of village time: every villager reads what it sees and hears
and picks one action (walk to a place, say something, optionally to one villager, or wait).
Start, Pause, Step and Reset control the clock; the interval sets the seconds between ticks.
The village pauses itself 60 seconds after the last Village tab closes, and after three ticks in
which every turn failed (e.g. the model server is down).

Each villager is a block agent under "My agents", created on the first Start; "Edit its agent"
opens it in the builder, and an edit applies from the next tick. Click a villager for what it
remembers and every turn it took; a turn opens in the usual run view (graph, prompt, answer).
Village turns stay out of the past-runs list.
The run header and the past-runs list show model calls, tool calls, tokens and wall time. Past
runs replay from the database (`backend/data/agent_lab.db`).

`make dev-llm` serves `RedHatAI/Qwen3.5-9B-quantized.w4a16` (4-bit Qwen3.5 9B) as `qwen3.5-9b`.
It keeps running in the background and comes back with Docker; follow it with
`docker logs -f agent-lab-vllm`, remove it with `make stop-llm`. `make dev-backend` and
`make dev-frontend` start the two servers separately.
vLLM batches concurrent requests, so parallel branches and workers really run at the same
time. Any OpenAI-compatible endpoint works instead (Ollama: `LLM_BASE_URL=http://localhost:11434/v1`,
`LLM_MODEL=qwen3:8b`): set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.

### Models

A custom agent runs on "Default" or on a model you pick in its agent settings; templates always
run on the default. The run header, past runs and span details show which model answered.
Configure the list in `.env` (see `.env.example`) and restart the backend after changes:

- `LLM_MODELS`: further model ids served by the local endpoint, comma-separated.
- `OPENAI_MODELS` and `OPENAI_API_KEY`: OpenAI models, e.g. `OPENAI_MODELS=gpt-6-luna`. Without
  the key they are listed but can't be picked. An agent on an OpenAI model sends its prompts and
  tool results to OpenAI. The key stays in `.env` and is redacted from every span.
- `OPENAI_REASONING_OFF`: the `reasoning_effort` sent when an agent's thinking is off (default
  `none`). If a model rejects it, the run fails with OpenAI's message on the span; set the value
  that model accepts, or leave it empty to send nothing.
  Some models refuse tools while thinking on Chat Completions (`gpt-6-luna`: "Function tools
  with reasoning_effort are not supported"); turn "Model thinking" off for tool-calling agents on
  them.
- `DEFAULT_MODEL`: `provider/model`, e.g. `openai/gpt-6-luna` (default: the local `LLM_MODEL`).
  The backend refuses to start when it names a model that isn't configured or has no key.

## Check

```bash
make check   # ruff, ruff format --check, pyright, pytest, eslint, tsc, vitest
```

## API

| | |
|---|---|
| `GET /agents` | templates, then custom agents, with config, sample prompt and graph |
| `GET /tools` | tools an agent can be given, with their parameter schema |
| `GET /village`, `POST /village/start`, `/pause`, `/step`, `/reset`, `PUT /village/interval` | the village and its controls; `WS /village/stream` sends the state after every tick |
| `GET /village/villagers/{name}/turns` | a villager's turns, newest first |
| `GET /blocks/new`, `GET /agents/{id}/blocks` | an unsaved block agent: new, or converted from a template or customized agent |
| `GET /models` | configured models: provider, id, external, available, default (never keys) |
| `POST /agents`, `PUT /agents/{id}`, `DELETE /agents/{id}` | create, update, delete a custom agent (`model`: `{"provider", "model"}` or `null` for Default) |
| `POST /graph` `{"template_id", "config"}` | the graph for an unsaved config (validation errors as `422`) |
| `POST /runs` `{"prompt": "...", "agent_id": "react"}` | start a run of a template or custom agent (`202`) |
| `GET /runs` | past runs with totals, newest first |
| `GET /runs/{id}` | run and its spans |
| `WS /runs/{id}/stream` | stored spans, then live span events, then `run_ended` |

Design and requirements: `specs/001-react-walking-skeleton/` (M1),
`specs/002-workflow-patterns/` (M2), `specs/003-agent-builder/` (M3).
